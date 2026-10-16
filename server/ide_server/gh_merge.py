# server/ide_server/gh_merge.py
"""Merge de PRs (solo la de abajo de un stack) con restack de las de arriba, sin Graphite.

1. `merge`: en un worktree propio por repo (`.ide/worktrees/_merge/<repo>`, detached) rebasea la
   rama de la PR sobre su base, la empuja (`--force-with-lease`) y arma `gh pr merge --squash
   --auto`: GitHub mergea cuando pasa el CI (nunca se mergea directo).
2. El vigilante (`run`) consulta las PRs con merge pendiente; cuando GitHub la mergea, restackea
   las de arriba: cada una se rebasea (`--onto`) sobre su nueva madre — las hijas directas sobre
   la base, con la base de la PR cambiada a esa — y al final se borra la rama mergeada.
   Los trabajos viven en `.ide/merges.json` (sobreviven reinicios del server)."""
from __future__ import annotations
import asyncio
import json
import logging
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable
from ide_server.sessions_fs import SessionError
from ide_server.workspace import discover_repos

log = logging.getLogger(__name__)
WATCH_INTERVAL = 30


def jobs_file(root: Path) -> Path:
    return root / ".ide" / "merges.json"


def merge_worktree(root: Path, repo: str) -> Path:
    return root / ".ide" / "worktrees" / "_merge" / repo


def _run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=600)


def _check(out: subprocess.CompletedProcess, what: str, code: str = "merge_failed") -> str:
    if out.returncode != 0:
        raise SessionError(code, f"{what}: {(out.stderr or out.stdout).strip() or out.returncode}")
    return out.stdout.strip()


class Merger:
    def __init__(self, root: Path, *, stacks: Callable[[], dict],
                 on_change: Callable[[], None] | None = None) -> None:
        """`stacks()`: estado actual de GitHubReviews (para saber quién está arriba de quién)."""
        self._root, self._stacks = root, stacks
        self._notify_cb = on_change or (lambda: None)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._locks: dict[str, threading.Lock] = {}
        self.jobs: dict[str, dict] = self._load()

    def _on_change(self) -> None:
        """Se llama desde threads (git/gh corren fuera del loop): se agenda en el loop."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._notify_cb)

    # -- persistencia ------------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        f = jobs_file(self._root)
        try:
            return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        except (OSError, ValueError) as exc:
            log.error("no se pudo leer %s: %s", f, exc)
            return {}

    def _save(self) -> None:
        jobs_file(self._root).write_text(json.dumps(self.jobs, indent=2) + "\n", encoding="utf-8")

    def _update(self, url: str, **fields) -> None:
        self.jobs[url] = {**self.jobs.get(url, {}), **fields}
        self._save()

    def public(self) -> dict[str, dict]:
        keys = ("state", "error", "restacked", "repo", "number", "title", "above")
        return {u: {k: j.get(k) for k in keys} for u, j in self.jobs.items()}

    # -- git ---------------------------------------------------------------------------------
    def _lock(self, repo: str) -> threading.Lock:
        return self._locks.setdefault(repo, threading.Lock())

    def _wt(self, repo: str, full_repo: str | None) -> Path:
        if repo not in {r["id"] for r in discover_repos(self._root)}:
            raise SessionError("unknown_repo", f"{repo} no está en el workspace: no puedo rebasear")
        # el repo local tiene que ser el mismo de GitHub (no otro con el mismo nombre)
        url = _check(_run(["git", "-C", str(self._root / repo), "remote", "get-url", "origin"]),
                     f"{repo} no tiene remote origin")
        slug = re.sub(r"\.git$", "", re.split(r"github\.com[:/]", url)[-1]) if "github.com" in url else ""
        if not full_repo or slug.lower() != full_repo.lower():
            raise SessionError("repo_mismatch", f"el origin de {repo} ({url}) no es {full_repo}")
        wt = merge_worktree(self._root, repo)
        if not wt.exists():
            wt.parent.mkdir(parents=True, exist_ok=True)
            _check(_run(["git", "-C", str(self._root / repo), "worktree", "add", "--detach", str(wt)]),
                   "no pude crear el worktree de merge")
        return wt

    def _rebase(self, wt: Path, branch: str, onto: str, upstream: str | None = None) -> tuple[str, str]:
        """Rebasea `origin/<branch>` sobre `onto` (con `--onto`/`upstream` si se pasa) y lo empuja.
        Devuelve (sha viejo, sha nuevo). Ante conflicto aborta y falla con `conflict`."""
        _check(_run(["git", "fetch", "origin", "--prune"], wt), "git fetch")
        old = _check(_run(["git", "rev-parse", f"origin/{branch}"], wt), f"no existe origin/{branch}")
        _check(_run(["git", "checkout", "--detach", "--force", old], wt), "git checkout")
        args = ["git", "rebase", "--onto", onto, upstream] if upstream else ["git", "rebase", onto]
        out = _run(args, wt)
        if out.returncode != 0:
            _run(["git", "rebase", "--abort"], wt)
            raise SessionError("conflict", f"conflicto al rebasear {branch} sobre {onto}: "
                                           "resuélvelo en una sesión y vuelve a intentar")
        new = _check(_run(["git", "rev-parse", "HEAD"], wt), "git rev-parse")
        if new != old:
            _check(_run(["git", "push", f"--force-with-lease={branch}:{old}", "origin",
                         f"HEAD:refs/heads/{branch}"], wt), f"git push de {branch}")
        return old, new

    # -- merge -------------------------------------------------------------------------------
    def _find(self, url: str) -> tuple[dict, list[dict]]:
        """La PR (card de GithubReviews) y su stack completo ([] si no está en uno)."""
        st = self._stacks()
        cards = [p for lst in [*(st.get("mine") or {}).values(), *(st.get("stacks") or {}).values(),
                               st.get("pending") or [], st.get("changesRequested") or []] for p in lst]
        pr = next((p for p in cards if p["url"] == url), None)
        if pr is None:
            raise SessionError("unknown_pr", f"no conozco la PR {url} (¿está abierta? espera el próximo poll)")
        stack = (st.get("stacks") or {}).get(pr["stack"]["id"], []) if pr.get("stack") else []
        return pr, stack

    def merge(self, url: str) -> dict:
        pr, stack = self._find(url)
        me = self._stacks().get("me")
        if not me or pr.get("author") != f"@{me}":
            raise SessionError("not_yours", "solo se mergean tus PRs")
        if pr.get("fork") or any(p.get("fork") for p in stack):
            raise SessionError("fork_pr", "PRs desde forks no se mergean ni restackean desde el IDE")
        if pr.get("stack") and pr["stack"]["position"] != 1:
            raise SessionError("not_bottom", "solo se mergea la PR de abajo del stack")
        if pr.get("review") != "approved":
            raise SessionError("not_approved", f"{pr['repo']}#{pr['number']} no está aprobada")
        if pr.get("ci") == "failure":
            raise SessionError("ci_failed", "el CI falló (o hay conflicto): no se arma el merge")
        if self.jobs.get(url, {}).get("state") in ("waiting", "restacking"):
            raise SessionError("merge_pending", "ya hay un merge en curso para esta PR")
        with self._lock(pr["repo"]):
            wt = self._wt(pr["repo"], pr.get("fullRepo"))
            old, _new = self._rebase(wt, pr["head"], f"origin/{pr['base']}")
            _check(_run(["gh", "pr", "merge", url, "--squash", "--auto"], wt), "gh pr merge --auto")
        above = [{"url": p["url"], "head": p["head"], "base": p["base"], "number": p["number"],
                  "author": p.get("author"), "fork": bool(p.get("fork"))}
                 for p in stack if p["stack"]["position"] > 1]
        self._update(url, state="waiting", error=None, repo=pr["repo"], full_repo=pr.get("fullRepo"),
                     head=pr["head"],
                     number=pr["number"], title=pr["title"],
                     base=pr["base"], old_sha=old, above=above, restacked=[], me=me,
                     at=datetime.now().isoformat(timespec="seconds"))
        self._on_change()
        return self.public()[url]

    # -- vigilante ---------------------------------------------------------------------------
    def _restack(self, url: str) -> None:
        """La PR ya está mergeada: rebasear las de arriba sobre su nueva madre, en orden."""
        j = self.jobs[url]
        self._update(url, state="restacking", merged=True, error=None)
        with self._lock(j["repo"]):
            wt = self._wt(j["repo"], j.get("full_repo"))
            # rama -> [sha viejo, a dónde va ahora, nueva base]; la mergeada "se convierte" en su
            # base. Se persiste: si falla a la mitad, el reintento sigue desde ahí.
            moved = j.get("moved") or {j["head"]: [j["old_sha"], f"origin/{j['base']}", j["base"]]}
            skipped = []
            for p in j["above"]:
                if p["url"] in j.get("restacked", []):
                    continue
                # solo se reescriben ramas tuyas y del repo base (el push es forzado)
                if p.get("fork") or not j.get("me") or p.get("author") != f"@{j['me']}":
                    skipped.append(f"#{p['number']} (de {p.get('author') or '?'})")
                    continue
                parent = moved.get(p["base"])
                if parent is None:              # su madre no se movió (ajena o stack ramificado)
                    skipped.append(f"#{p['number']} (encima de una PR que no se movió)")
                    continue
                old_parent, onto, new_base = parent
                old, new = self._rebase(wt, p["head"], onto, upstream=old_parent)
                if new_base != p["base"]:
                    _check(_run(["gh", "pr", "edit", p["url"], "--base", new_base], wt),
                           f"cambiar la base de #{p['number']}")
                moved[p["head"]] = [old, new, p["head"]]
                self._update(url, moved=moved,
                             restacked=[*self.jobs[url].get("restacked", []), p["url"]])
            # si quedó una PR sin mover apuntando a la rama mergeada, borrarla la cerraría en GitHub
            if not skipped:
                out = _run(["git", "push", "origin", "--delete", j["head"]], wt)   # ya pudo borrarla GitHub
                if out.returncode != 0 and "remote ref does not exist" not in out.stderr:
                    log.warning("no se pudo borrar la rama %s: %s", j["head"], out.stderr.strip())
        if skipped:
            self._update(url, state="error", error="mergeada, pero no restackeé "
                         + ", ".join(skipped) + ": muévelas a mano o avísale a su autor (no borré "
                         + j["head"] + " para que GitHub no las cierre)")
            return
        self._update(url, state="done")

    def poll_once(self) -> None:
        changed = False
        for url, j in list(self.jobs.items()):
            if j.get("state") not in ("waiting", "restacking"):
                continue
            try:
                if j["state"] == "waiting":
                    out = _run(["gh", "pr", "view", url, "--json", "state,autoMergeRequest"])
                    data = json.loads(_check(out, "gh pr view"))
                    if data["state"] == "CLOSED":
                        self._update(url, state="error", error="la PR se cerró sin mergear")
                    elif data["state"] == "OPEN" and not data.get("autoMergeRequest"):
                        self._update(url, state="error", error="se desarmó el auto-merge en GitHub")
                    elif data["state"] == "MERGED":
                        self._restack(url)
                    else:
                        continue
                else:                           # quedó a medias (error o reinicio): seguir
                    self._restack(url)
                changed = True
            except SessionError as exc:
                self._update(url, state="error", error=str(exc))
                changed = True
            except Exception as exc:  # noqa: BLE001 — queda en la card, nunca silencioso
                log.exception("merge de %s", url)
                self._update(url, state="error", error=str(exc) or type(exc).__name__)
                changed = True
        if changed:
            self._on_change()

    def retry(self, url: str) -> None:
        """Reintenta un restack que falló (p.ej. tras resolver un conflicto)."""
        j = self.jobs.get(url)
        if not j or j.get("state") != "error":
            raise SessionError("no_merge", "no hay un merge con error para reintentar")
        self._update(url, state="restacking" if j.get("merged") else "waiting", error=None)
        self._on_change()

    async def run(self, stop: asyncio.Event) -> None:
        self._loop = asyncio.get_running_loop()
        while not stop.is_set():
            try:
                await asyncio.to_thread(self.poll_once)
            except Exception:
                log.exception("el vigilante de merges falló; sigue en el próximo")
            try:
                await asyncio.wait_for(stop.wait(), WATCH_INTERVAL)
            except asyncio.TimeoutError:
                pass
