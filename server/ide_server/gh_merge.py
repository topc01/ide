# server/ide_server/gh_merge.py
"""Merge de PRs (solo la de abajo de un stack) con restack de las de arriba, sin Graphite.

1. `merge`: si hace falta (GitHub exige la rama al día, hay conflicto o arrastra commits de una madre
   squasheada), en un worktree propio por repo (`.ide/worktrees/_merge/<repo>`, detached) rebasea la
   rama de la PR sobre su base y la empuja (`--force-with-lease`); si no, la deja como está (sin
   volver a correr el CI). Después arma el auto-merge de GitHub (`gh pr merge --auto --squash`):
   GitHub mergea al pasar el CI y la aprobación (se puede armar antes de aprobar). En stacks nativos
   (GitHub solo acepta `merge-async`) el IDE espera el CI y la aprobación y lo pide él.
2. El vigilante (`run`) consulta las PRs con merge pendiente; cuando GitHub la mergea, restackea
   las de arriba: cada una se rebasea (`--onto`) sobre su nueva madre — las hijas directas sobre
   la base, con la base de la PR cambiada a esa — y al final se borra la rama mergeada.
   Los trabajos viven en la base (`.ide/ide.db`, tabla `merges`): sobreviven reinicios."""
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
from ide_server.db import Db
from ide_server.pr_changes import stack_parent
from ide_server.sessions_fs import SessionError
from ide_server.workspace import discover_repos

log = logging.getLogger(__name__)
WATCH_INTERVAL = 30
ACTIVE = ("rebasing", "waiting", "waiting_ci", "merging", "restacking")


def merge_worktree(root: Path, repo: str) -> Path:
    return root / ".ide" / "worktrees" / "_merge" / repo


def _run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=600)


def _check(out: subprocess.CompletedProcess, what: str, code: str = "merge_failed") -> str:
    if out.returncode != 0:
        raise SessionError(code, f"{what}: {(out.stderr or out.stdout).strip() or out.returncode}")
    return out.stdout.strip()


def squashed_parent(wt: Path, branch: str, base: str, full_repo: str | None, number: int | None) -> str | None:
    """Si la rama arrastra commits de una PR madre que ya se mergeó con squash (estaba apilada y GitHub la
    re-apuntó a la base), el último commit de esa madre: hay que rebasear con `--onto` desde ahí, o se
    re-aplican commits que la base ya tiene (squasheados) y chocan."""
    if not full_repo:
        return None
    out = _run(["git", "rev-list", "--max-count=60", f"origin/{base}..origin/{branch}"], wt)
    if out.returncode != 0:                 # la rama ya no está (p.ej. GitHub la mergeó y la borró)
        return None
    shas = out.stdout.split()
    for sha in shas[1:]:                    # el primero es el head de esta misma PR
        out = _run(["gh", "api", f"repos/{full_repo}/commits/{sha}/pulls"])
        try:
            prs = json.loads(out.stdout or "[]") if out.returncode == 0 else []
        except ValueError:
            prs = []
        if any(p.get("merged_at") and p.get("number") != number and p.get("head", {}).get("sha") == sha
               for p in prs):
            return sha
    return None


class Merger:
    def __init__(self, root: Path, *, stacks: Callable[[], dict], db: Db,
                 on_change: Callable[[], None] | None = None) -> None:
        """`stacks()`: estado actual de GitHubReviews (para saber quién está arriba de quién)."""
        self._root, self._stacks, self._db = root, stacks, db
        self._notify_cb = on_change or (lambda: None)
        # un problema que el IDE no puede resolver solo (conflicto al rebasear, migraciones): se le avisa
        # a la sesión del desarrollo (lo conecta folder_sessions)
        self.on_problem: Callable[[dict, str], None] = lambda _job, _msg: None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._locks: dict[str, threading.Lock] = {}
        self._jobs_lock = threading.RLock()     # los trabajos se tocan desde varios threads
        self.jobs: dict[str, dict] = self._load()
        for url, j in list(self.jobs.items()):  # un rebase que corría cuando se cortó el server
            if j.get("state") == "rebasing":
                self._update(url, state="error", error="se interrumpió (reinicio del server): reintenta")

    def _on_change(self) -> None:
        """Se llama desde threads (git/gh corren fuera del loop): se agenda en el loop."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._notify_cb)

    # -- persistencia ------------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        return self._db.merges()

    def _update(self, url: str, **fields) -> None:
        with self._jobs_lock:
            prev = self.jobs.get(url, {}).get("state")
            self.jobs[url] = {**self.jobs.get(url, {}), **fields}
            self._db.put_merge(url, self.jobs[url])
            if fields.get("state") and fields["state"] != prev:      # historial del merge
                self._db.event(datetime.now().isoformat(timespec="seconds"), "ide", "merge",
                               pr_url=url, data={"state": fields["state"], **(
                                   {"error": fields["error"]} if fields.get("error") else {})})

    def public(self) -> dict[str, dict]:
        keys = ("state", "error", "restacked", "repo", "number", "title", "above", "native", "merged_at")
        return {u: {**{k: j.get(k) for k in keys}, "url": u} for u, j in self.jobs.items()}

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

    def _squashed_parent(self, wt: Path, branch: str, base: str, full_repo: str | None,
                         number: int | None) -> str | None:
        return squashed_parent(wt, branch, base, full_repo, number)

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

    def merge(self, url: str, *, renumber: bool = False, patient: bool = False) -> dict:
        """Valida y arranca el merge en segundo plano (no bloquea: la card muestra el progreso). Una PR en
        conflicto no se rechaza: se pone al día al mergear (si choca, se avisa a su sesión). `renumber`:
        si sus migraciones chocan con la base, las renumera (commit + push) en vez de frenar."""
        pr, stack = self._find(url)
        me = self._stacks().get("me")
        if not me or pr.get("author") != f"@{me}":
            raise SessionError("not_yours", "solo se mergean tus PRs")
        if pr.get("fork") or any(p.get("fork") for p in stack):
            raise SessionError("fork_pr", "PRs desde forks no se mergean ni restackean desde el IDE")
        if pr.get("stack") and pr["stack"]["position"] != 1:
            raise SessionError("not_bottom", "solo se mergea la PR de abajo del stack")
        if pr.get("ci") == "failure" and not patient:
            raise SessionError("ci_failed", "el CI falló: no se arma el merge")
        if self.jobs.get(url, {}).get("state") in ACTIVE:
            raise SessionError("merge_pending", "ya hay un merge en curso para esta PR")
        native = bool(pr.get("stack") and pr["stack"].get("native"))
        # stack nativo: GitHub rebasea y re-apunta sus miembros solo; el IDE restackea el resto (las
        # que se le apilaron por base, fuera del stack nativo) y todo el stack si no es nativo
        in_native = lambda p: native and (p["stack"].get("inNative") is not False)   # noqa: E731
        above = [
            {"url": p["url"], "head": p["head"], "base": p["base"], "number": p["number"],
             "author": p.get("author"), "fork": bool(p.get("fork"))}
            for p in stack if p["stack"]["position"] > 1 and not in_native(p)]
        native_heads = [p["head"] for p in stack if p["stack"]["position"] > 1 and in_native(p)]
        self._update(url, state="rebasing", error=None, merged=False, native=native, native_heads=native_heads,
                     native_old=None, restack_since=None,
                     repo=pr["repo"], full_repo=pr.get("fullRepo"), head=pr["head"], base=pr["base"],
                     number=pr["number"], title=pr["title"], above=above, restacked=[], moved=None, renumber=renumber,
                     patient=patient,
                     uuid=None, me=me, at=datetime.now().isoformat(timespec="seconds"))
        self._on_change()
        threading.Thread(target=self._start, args=(url,), daemon=True).start()
        return self.public()[url]

    def _start(self, url: str) -> None:
        """Rebase + push; después el vigilante espera el CI y pide el merge."""
        j = self.jobs[url]
        try:
            with self._lock(j["repo"]):
                wt = self._wt(j["repo"], j.get("full_repo"))
                _check(_run(["git", "fetch", "origin", "--prune"], wt), "git fetch")
                if json.loads(_check(_run(["gh", "pr", "view", url, "--json", "state"]), "gh pr view"))["state"] == "MERGED":
                    self._merged(url)           # ya se mergeó (p.ej. GitHub la mergeó con su stack): sigue el restack
                    return
                cut = self._squashed_parent(wt, j["head"], j["base"], j.get("full_repo"), j.get("number"))
                st = self._merge_state(url)
                # rebasear solo si hace falta: GitHub exige la rama al día (BEHIND), hay conflicto
                # (DIRTY) o arrastra commits de una madre squasheada. Si no, se mergea tal cual: un
                # rebase innecesario cambia los commits y vuelve a correr todo el CI.
                if cut is None and st.get("mergeStateStatus") not in ("BEHIND", "DIRTY") \
                        and st.get("mergeable") != "CONFLICTING":
                    head = st.get("headRefOid") or _check(_run(["git", "rev-parse", f"origin/{j['head']}"], wt), "git rev-parse")
                    old, new = head, head
                    self._update(url, rebased=False)
                else:
                    old, new = self._rebase(wt, j["head"], f"origin/{j['base']}", upstream=cut)
                    self._update(url, rebased=new != old)
                new = self._check_migrations(url, j, wt, new)
            self._update(url, old_sha=old, head_sha=new)
            if j.get("native") and j.get("above"):
                # dónde están hoy las ramas que GitHub va a mover: desde ahí se re-aplican las de encima
                self._update(url, native_old={h: _check(_run(["git", "rev-parse", f"origin/{h}"], wt), f"origin/{h}")
                                              for h in j.get("native_heads") or []})
            if j.get("native"):
                # stack nativo: GitHub solo acepta `merge-async`: el IDE espera CI y aprobación
                self._update(url, state="waiting_ci")
            else:
                self._enable_auto(url, j, pushed=new != old)
        except SessionError as exc:
            self._update(url, state="error", error=str(exc))
            if exc.code in ("conflict", "migrations"):
                try:
                    self.on_problem(self.jobs[url], str(exc))
                except Exception:  # noqa: BLE001
                    log.exception("aviso a la sesión de %s", url)
        except Exception as exc:  # noqa: BLE001 — queda en la card, nunca silencioso
            log.exception("merge de %s", url)
            self._update(url, state="error", error=str(exc) or type(exc).__name__)
        self._on_change()

    def _check_migrations(self, url: str, j: dict, wt: Path, head: str) -> str:
        """Las migraciones de la PR contra la base: si chocan, renumera (con `renumber`: commit + push y
        devuelve el sha nuevo) o falla con lo que hay que renumerar."""
        from ide_server import migrations
        try:
            plan = migrations.plan(wt, f"origin/{j['base']}", head)
        except RuntimeError as exc:
            raise SessionError("migrations", f"no pude revisar las migraciones: {exc}")
        if plan["ok"]:
            return head
        what = migrations.describe(plan)
        if not j.get("renumber") or not all(a["renames"] for a in plan["apps"]):
            raise SessionError("migrations", "las migraciones chocan con la base (no mergeo):\n" + what
                               + "\nLa sesión lo arregla con `ide migrations renumber`, o mergea con `ide merge <pr> --renumber`.")
        _check(_run(["git", "checkout", "--detach", "--force", head], wt), "git checkout")
        try:
            migrations.renumber(wt, plan)
        except RuntimeError as exc:
            raise SessionError("migrations", f"no pude renumerar: {exc}")
        new = _check(_run(["git", "rev-parse", "HEAD"], wt), "git rev-parse")
        _check(_run(["git", "push", f"--force-with-lease={j['head']}:{head}", "origin",
                     f"HEAD:refs/heads/{j['head']}"], wt), f"git push de {j['head']}")
        self._update(url, rebased=True, renumbered=what)
        return new

    def _enable_auto(self, url: str, j: dict, *, pushed: bool) -> None:
        """Auto-merge de GitHub (squash): mergea solo cuando pasan el CI y la aprobación, aunque el IDE
        esté apagado. Justo después de un push GitHub todavía calcula si es mergeable: se reintenta.
        Si ya está lista para mergear (`clean status`), se mergea directo."""
        import time
        last = ""
        for attempt in range(6 if pushed else 2):
            out = _run(["gh", "pr", "merge", url, "--auto", "--squash"])
            if out.returncode == 0:
                self._update(url, state="waiting", auto=True)
                return
            last = (out.stderr or out.stdout).strip()
            if "auto merge is not allowed" in last.lower() or "auto-merge is not allowed" in last.lower() \
                    or "not supported for stacked pull requests" in last.lower():
                # el repo no tiene habilitado el auto-merge, o la PR es de un stack de GitHub (ahí no se
                # puede armar): lo hace el IDE (espera CI y aprobación)
                self._update(url, state="waiting_ci", auto=False)
                return
            if "clean status" in last.lower():
                now = _run(["gh", "pr", "merge", url, "--squash"])
                if now.returncode == 0:
                    self._merged(url)
                    return
                last = (now.stderr or now.stdout).strip()
            time.sleep(5 * (attempt + 1))
        self._update(url, state="error", error=f"no pude armar el auto-merge en GitHub: {last}")

    def cancel(self, url: str) -> None:
        """Desarmar: quita el auto-merge en GitHub (o deja de esperar, en stacks nativos) y sale de la lista."""
        j = self.jobs.get(url)
        if not j or j.get("state") not in ("waiting", "waiting_ci"):
            raise SessionError("no_merge", "no hay un auto-merge armado para desarmar")
        if j.get("state") == "waiting":
            out = _run(["gh", "pr", "merge", url, "--disable-auto"])
            if out.returncode != 0 and "not enabled" not in (out.stderr or "").lower():
                raise SessionError("gh_failed", f"gh pr merge --disable-auto: {(out.stderr or out.stdout).strip()}")
        with self._jobs_lock:
            self.jobs.pop(url, None)
            self._db.delete_merge(url)
        self._on_change()

    def _merge_state(self, url: str) -> dict:
        """mergeStateStatus / mergeable de GitHub (UNKNOWN mientras lo calcula: se reintenta unos segundos)."""
        import time
        data: dict = {}
        for _ in range(5):
            out = _run(["gh", "pr", "view", url, "--json", "mergeStateStatus,mergeable,headRefOid"])
            data = json.loads(_check(out, "gh pr view"))
            if data.get("mergeStateStatus") != "UNKNOWN" and data.get("mergeable") != "UNKNOWN":
                break
            time.sleep(2)
        return data

    def _pr_status(self, url: str) -> dict:
        out = _run(["gh", "pr", "view", url, "--json", "state,mergeable,headRefOid,statusCheckRollup,reviewDecision"])
        data = json.loads(_check(out, "gh pr view"))
        bad = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
        # sin ningún check todavía (recién salida de draft o recién pusheada) = el CI no partió: no es verde
        ci = "success" if data.get("statusCheckRollup") else "pending"
        for c in data.get("statusCheckRollup") or []:
            concl, state = c.get("conclusion") or "", c.get("state") or ""
            if concl in bad or state in ("FAILURE", "ERROR"):
                ci = "failure"
                break
            if (c.get("__typename") == "CheckRun" and c.get("status") != "COMPLETED") or state in ("PENDING", "EXPECTED"):
                ci = "pending"
        return {**data, "ci": ci}

    def _merge_async(self, url: str, j: dict, head_sha: str) -> None:
        """`PUT .../merge-async` (squash) con el CI ya en verde (obligatorio para stacks nativos)."""
        out = _run(["gh", "api", "-X", "PUT", f"repos/{j['full_repo']}/pulls/{j['number']}/merge-async",
                    "-f", "merge_method=squash", "-f", f"sha={head_sha}"])
        try:
            res = json.loads(out.stdout or "{}")
        except ValueError:
            res = {}
        status, details = res.get("status"), res.get("details") or {}
        if status == "merged":
            self._merged(url)
        elif status in ("pending", "enqueued") or details.get("uuid"):
            self._update(url, state="merging", uuid=details.get("uuid"))
        else:
            msg = details.get("message") or res.get("message") or (out.stderr or out.stdout).strip()
            if "is expected" in str(msg) or "status check" in str(msg).lower():
                return                          # falta un check obligatorio: sigue en waiting_ci, se reintenta
            self._update(url, state="error", error=f"merge-async: {msg or out.returncode}")

    # -- vigilante    # -- vigilante ---------------------------------------------------------------------------
    # -- restack a pedido (módulo Stack) ------------------------------------------------------------
    def _own_commits_base(self, full_repo: str, number: int, branch: str, wt: Path) -> str:
        """El padre del primer commit propio de la PR: desde ahí se re-aplica (`rebase --onto`), así
        no se arrastran commits viejos de la madre aunque ella se haya reescrito."""
        out = _run(["gh", "api", f"repos/{full_repo}/pulls/{number}/commits?per_page=250", "--jq", ".[0].sha"])
        first = out.stdout.strip() if out.returncode == 0 else ""
        if not first:
            raise SessionError("gh_failed", f"no pude leer los commits de #{number}: {out.stderr.strip()}")
        return _check(_run(["git", "rev-parse", f"{first}^"], wt), f"padre del primer commit de #{number}")

    @staticmethod
    def _local_guard(repo: Path, branches: list[str]) -> list[tuple[Path, str]]:
        """Worktrees donde están checkouteadas esas ramas: tienen que estar limpios y al día con
        origin (si no, el push forzado les dejaría la rama divergida). Devuelve (worktree, rama)."""
        out = _run(["git", "-C", str(repo), "worktree", "list", "--porcelain"]).stdout
        found, path = [], None
        for line in out.splitlines():
            if line.startswith("worktree "):
                path = Path(line[9:])
            elif line.startswith("branch refs/heads/") and path and line[18:] in branches:
                found.append((path, line[18:]))
        for wt, b in found:
            if _run(["git", "-C", str(wt), "status", "--porcelain", "--untracked-files=no"]).stdout.strip():
                raise SessionError("uncommitted_changes", f"{b} tiene cambios sin commitear en {wt}: commitéalos y púshealos antes")
            _run(["git", "-C", str(wt), "fetch", "origin", "--quiet"])
            ahead = _run(["git", "-C", str(wt), "rev-list", "--count", f"origin/{b}..HEAD"]).stdout.strip()
            if ahead not in ("", "0"):
                raise SessionError("unpushed", f"{b} tiene {ahead} commit(s) sin pushear en {wt}: púshealos antes")
        return found

    def restack(self, url: str, *, update_base: bool = False) -> dict:
        """Rebasea cada PR del stack de `url` sobre su madre (y la de abajo sobre su base si
        `update_base`), empuja con --force-with-lease y deja al día los worktrees que las tienen."""
        pr, stack = self._find(url)
        prs = sorted(stack, key=lambda p: p["stack"]["position"]) if stack else [pr]
        me = self._stacks().get("me")
        bad = [f"#{p['number']}" for p in prs if p.get("fork") or not me or p.get("author") != f"@{me}"]
        if bad:
            raise SessionError("not_yours", "solo se restackean stacks enteros tuyos (no: " + ", ".join(bad) + ")")
        if any(self.jobs.get(p["url"], {}).get("state") in ACTIVE for p in prs):
            raise SessionError("merge_pending", "hay un merge en curso en este stack")
        repo = self._root / pr["repo"]
        moved: list[str] = []
        with self._lock(pr["repo"]):
            wt = self._wt(pr["repo"], pr.get("fullRepo"))
            guarded = self._local_guard(repo, [p["head"] for p in prs])
            _check(_run(["git", "fetch", "origin", "--prune"], wt), "git fetch")
            # cada una sobre SU base (la rama de su madre; hermanas sobre la misma madre, nunca una
            # sobre otra), madres antes que hijas (el orden del stack es en profundidad)
            for p in prs:
                if not update_base and stack_parent(prs, p) is None:
                    continue
                onto = f"origin/{p['base']}"
                upstream = self._own_commits_base(pr["fullRepo"], p["number"], p["head"], wt)
                old, new = self._rebase(wt, p["head"], onto, upstream=upstream)
                if new != old:
                    moved.append(f"#{p['number']}")
            for path, b in guarded:              # estaban limpios y al día: los dejo en el nuevo head
                _run(["git", "-C", str(path), "fetch", "origin", "--quiet"])
                _run(["git", "-C", str(path), "reset", "--hard", f"origin/{b}"])
        if self._db is not None:
            self._db.event(datetime.now().isoformat(timespec="seconds"), "ide", "restack", pr_url=url,
                           data={"moved": moved, "updateBase": update_base})
        return {"moved": moved}

    def _restack(self, url: str) -> None:
        """La PR ya está mergeada: rebasear las de arriba sobre su nueva madre, en orden."""
        j = self.jobs[url]
        self._update(url, state="restacking", merged=True, error=None)
        with self._lock(j["repo"]):
            wt = self._wt(j["repo"], j.get("full_repo"))
            # rama -> [sha viejo, a dónde va ahora, nueva base]; la mergeada "se convierte" en su
            # base. Se persiste: si falla a la mitad, el reintento sigue desde ahí.
            moved = j.get("moved") or {j["head"]: [j["old_sha"], f"origin/{j['base']}", j["base"]]}
            if j.get("native") and not j.get("moved"):
                # stack nativo: GitHub mueve sus miembros por su cuenta; las de encima se re-aplican
                # cuando ya los movió (si no, se espera al próximo ciclo, hasta 10 min)
                _check(_run(["git", "fetch", "origin", "--prune"], wt), "git fetch")
                waiting = []
                for h, old in (j.get("native_old") or {}).items():
                    now = _run(["git", "rev-parse", f"origin/{h}"], wt).stdout.strip()
                    if now == old:
                        waiting.append(h)
                    moved[h] = [old, f"origin/{h}", h]
                if waiting:
                    since = j.get("restack_since") or datetime.now().isoformat(timespec="seconds")
                    if (datetime.now() - datetime.fromisoformat(since)).total_seconds() < 600:
                        self._update(url, restack_since=since)
                        return
                    self._update(url, state="error", error="mergeada, pero GitHub no movió " + ", ".join(waiting)
                                 + " en 10 min: no restackeé las de encima (reintenta o muévelas a mano)")
                    return
                self._update(url, moved=moved)
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
            # (en un stack nativo la rama la maneja GitHub)
            if not skipped and not j.get("native"):
                out = _run(["git", "push", "origin", "--delete", j["head"]], wt)   # ya pudo borrarla GitHub
                if out.returncode != 0 and "remote ref does not exist" not in out.stderr:
                    log.warning("no se pudo borrar la rama %s: %s", j["head"], out.stderr.strip())
        if skipped:
            self._update(url, state="error", error="mergeada, pero no restackeé "
                         + ", ".join(skipped) + ": muévelas a mano o avísale a su autor (no borré "
                         + j["head"] + " para que GitHub no las cierre)")
            return
        self._update(url, state="done", merged_at=datetime.now().isoformat(timespec="seconds"))

    def _merged(self, url: str) -> None:
        """GitHub ya la mergeó: las de arriba que no mueve GitHub (todas si no es nativo; en uno nativo,
        las que se le apilaron por base) las restackea el IDE."""
        if not self.jobs[url].get("above"):
            self._update(url, state="done", merged=True,
                         merged_at=datetime.now().isoformat(timespec="seconds"))
        else:
            self._restack(url)

    def _step(self, url: str, j: dict) -> bool:
        """Avanza un trabajo un paso. Devuelve si cambió algo."""
        state = j.get("state")
        if state == "waiting":                  # no nativo: auto-merge de GitHub
            out = _run(["gh", "pr", "view", url, "--json", "state,autoMergeRequest"])
            data = json.loads(_check(out, "gh pr view"))
            if data["state"] == "CLOSED":
                self._update(url, state="error", error="la PR se cerró sin mergear")
            elif data["state"] == "OPEN" and not data.get("autoMergeRequest"):
                self._update(url, state="error", error="se desarmó el auto-merge en GitHub")
            elif data["state"] == "MERGED":
                self._merged(url)
            else:
                return False
            return True
        if state == "waiting_ci":               # nativo: el IDE espera el CI y pide el merge
            st = self._pr_status(url)
            if st["state"] == "MERGED":
                self._merged(url)
            elif st["state"] == "CLOSED":
                self._update(url, state="error", error="la PR se cerró sin mergear")
            elif st.get("mergeable") == "CONFLICTING":
                self._update(url, state="error", error=f"conflicto con {j['base']}: resuélvelo y reintenta")
            elif st["ci"] == "failure":
                if j.get("patient"):            # «Mergear todo»: la sesión lo arregla y se sigue esperando
                    return False
                self._update(url, state="error", error="el CI falló: arréglalo y reintenta")
            elif st["ci"] == "success" and st.get("mergeable") == "MERGEABLE" and st.get("reviewDecision") in ("APPROVED", None, ""):
                self._merge_async(url, j, st["headRefOid"])
            else:
                return False
            return True
        if state == "merging":                  # nativo: merge-async en curso
            if j.get("uuid"):
                out = _run(["gh", "api", f"repos/{j['full_repo']}/pulls/{j['number']}/merge-async/{j['uuid']}"])
                res = json.loads(out.stdout or "{}") if out.returncode == 0 else {}
                if res.get("status") == "failed":
                    msg = (res.get("details") or {}).get("message") or "GitHub no pudo mergear"
                    if "is expected" in msg or "status check" in msg.lower():
                        # falta un check obligatorio (el CI todavía no lo reporta): se sigue esperando
                        self._update(url, state="waiting_ci", uuid=None)
                        return True
                    self._update(url, state="error", error=f"merge-async: {msg}")
                    return True
            st = self._pr_status(url)
            if st["state"] == "MERGED":
                self._merged(url)
                return True
            return False
        if state == "restacking":               # no nativo, quedó a medias: seguir
            self._restack(url)
            return True
        return False

    def poll_once(self) -> None:
        changed = False
        for url, j in list(self.jobs.items()):
            if j.get("state") not in ("waiting", "waiting_ci", "merging", "restacking"):
                continue
            try:
                changed = self._step(url, dict(j)) or changed
            except SessionError as exc:
                self._update(url, state="error", error=str(exc))
                changed = True
            except Exception as exc:  # noqa: BLE001 — queda en la card, nunca silencioso
                log.exception("merge de %s", url)
                self._update(url, state="error", error=str(exc) or type(exc).__name__)
                changed = True
        if changed:
            self._on_change()

    def dismiss(self, url: str) -> None:
        """Archivar un merge terminado (mergeado o con error): sale de la lista. No toca GitHub."""
        j = self.jobs.get(url)
        if not j:
            raise SessionError("no_merge", "no hay un merge para archivar")
        if j.get("state") in ACTIVE:
            raise SessionError("merge_pending", "el merge sigue en curso: no se puede archivar todavía")
        with self._jobs_lock:
            self.jobs.pop(url, None)
            self._db.delete_merge(url)
        self._on_change()

    def retry(self, url: str) -> None:
        """Reintenta un merge con error: si ya se mergeó sigue el restack; si no, desde el rebase."""
        j = self.jobs.get(url)
        if not j or j.get("state") != "error":
            raise SessionError("no_merge", "no hay un merge con error para reintentar")
        if j.get("merged"):
            self._update(url, state="restacking", error=None, restack_since=None)
        else:
            self._update(url, state="rebasing", error=None)
            threading.Thread(target=self._start, args=(url,), daemon=True).start()
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
