# server/ide_server/session_ops.py
from __future__ import annotations
import io
import json
import re
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable
from ide_server.config import sessions_config
from ide_server.repos_fs import add_repo, rm_repo, worktree_path, require_session
from ide_server.prompts import load_prompt
from ide_server.sessions_fs import (
    SessionError, create_session_dir, new_id, normalize_id, read_session, render_template,
    require_plain_name, session_path, sessions_dir, update_session_toml, read_toml,
)
from ide_server.workspace import discover_repos
from ide_server.worktrees import has_uncommitted_changes

Runner = Callable[[list[str]], subprocess.CompletedProcess]
_PR_RE = re.compile(r"^https://github\.com/[^/]+/([^/]+)/pull/(\d+)")


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]} no está instalado")


def parse_pr_url(url: str) -> tuple[str, int]:
    m = _PR_RE.match(url.strip())
    if not m:
        raise SessionError("bad_pr_url", f"URL de PR inválida: {url!r} "
                                         "(esperado https://github.com/<owner>/<repo>/pull/<n>)")
    return m.group(1), int(m.group(2))


def load_template(root: Path, name: str) -> str:
    require_plain_name(name, "plantilla")
    path = sessions_dir(root) / "templates" / f"{name}.md"
    if not path.is_file():
        raise SessionError("unknown_template", f"no existe la plantilla {name} ({path})")
    return path.read_text(encoding="utf-8")


def _gh_pr(url: str, runner: Runner) -> dict:
    out = runner(["gh", "pr", "view", url, "--json", "title,author,headRefOid,state"])
    if out.returncode != 0:
        raise SessionError("gh_failed", f"gh pr view falló: {out.stderr.strip() or out.returncode}")
    return json.loads(out.stdout)


def _fetch_pr(root: Path, repo: str, number: int, runner: Runner) -> None:
    out = runner(["git", "-C", str(root / repo), "fetch", "origin", f"pull/{number}/head"])
    if out.returncode != 0:
        raise SessionError("fetch_failed", f"git fetch del PR falló: {out.stderr.strip()}")


def _resolve_permissions(root: Path, req: dict) -> str:
    """Permisos de la sesión nueva. Si la pide otra sesión (`caller`, vía `ide session new`
    desde adentro de claude), sólo la principal puede, y nunca con `full` (sin escalada)."""
    caller = req.get("caller")
    requested = req.get("permissions")
    if not caller:
        return requested or sessions_config(root)["default_permissions"]
    try:
        kind = read_toml(session_path(root, normalize_id(caller)) / ".session.toml").get("kind")
    except (SessionError, OSError, ValueError):
        kind = None
    if kind != "main":
        raise SessionError("forbidden", "solo la sesión principal puede crear sesiones")
    if requested == "full":
        raise SessionError("forbidden", "una sesión no puede lanzar otra con permisos full; "
                                        "hazlo desde la UI o la terminal")
    permissions = requested or sessions_config(root)["default_permissions"]
    return "analyze" if permissions == "full" else permissions


_NOTION_ID_RE = re.compile(r"([0-9a-f]{32})(?:[?#/]|$)")


def notion_session_id(url: str) -> str:
    """Id de sesión derivado del page id de una URL de Notion (n-<últimos 10 hex>)."""
    m = _NOTION_ID_RE.search(url.strip().lower().replace("-", ""))
    if not m:
        raise SessionError("bad_notion_url", f"no encuentro el page id en la URL de Notion: {url!r}")
    return f"n-{m.group(1)[-10:]}"           # el final es la parte aleatoria (el prefijo se repite)


def _existing(root: Path, sid: str, req: dict) -> dict | None:
    """Si la sesión ya existe: con if_missing/dry_run la devuelve; si no, error."""
    if archive_path(root, sid).exists():
        raise SessionError("session_archived", f"la sesión {sid} está archivada "
                                               f"(.ide/archive/sessions/{sid}); usa otro id")
    if not session_path(root, sid).exists():
        return None
    if req.get("if_missing"):
        current = read_session(root, sid)
        stored = current["meta"].get("notion_url")
        same = lambda a, b: (_NOTION_ID_RE.search(a.lower().replace("-", "")) or [None])[0] == \
            (_NOTION_ID_RE.search(b.lower().replace("-", "")) or [None])[0]   # URL o id pelado
        if req.get("notion") and stored and not same(stored, req["notion"]):
            raise SessionError("id_collision",
                               f"el id {sid} ya es de otro ticket ({stored}); pasa --id explícito")
        return {"session": current, "log": "", "existed": True}
    if req.get("dry_run"):
        return None
    raise SessionError("session_exists", f"ya existe la sesión {sid}")


def create_session(root: Path, req: dict, *, runner: Runner = _run) -> dict:
    permissions = _resolve_permissions(root, req)
    if req.get("review"):
        return _create_review(root, req, permissions, runner)
    kind = "main" if req.get("main") else "ticket"
    if req.get("id"):
        sid = normalize_id(req["id"])
    elif req.get("notion"):
        sid = notion_session_id(req["notion"])
    else:
        sid = new_id(lambda s: session_path(root, s).exists() or archive_path(root, s).exists())
    if (found := _existing(root, sid, req)) is not None:
        return found
    variables = {"id": sid, **(req.get("vars") or {})}
    if req.get("notion"):
        # `--notion <id>` (los 32 hex, p.ej. desde /backlog): se guarda como URL completa
        raw = req["notion"].strip().replace("-", "").lower()
        notion = f"https://app.notion.com/p/{raw}" if re.fullmatch(r"[0-9a-f]{32}", raw) else req["notion"]
        variables.setdefault("notion_url", notion)
    prompt = (render_template(load_template(root, req["template"]), variables)
              if req.get("template") else req.get("prompt") or "")
    meta = None
    if kind == "ticket":
        meta = {"title": req.get("title") or variables.get("title"),
                "notion_url": variables.get("notion_url")}
    if req.get("dry_run"):
        return {"session": {"id": sid, "kind": kind, "permissions": permissions,
                            "title": (meta or {}).get("title")},
                "prompt": prompt, "log": "", "dryRun": True,
                "existed": session_path(root, sid).exists()}
    create_session_dir(root, sid=sid, kind=kind, permissions=permissions, prompt=prompt, meta=meta)
    return {"session": read_session(root, sid), "log": ""}


def _create_review(root: Path, req: dict, permissions: str, runner: Runner) -> dict:
    url = req["review"]
    repo, number = parse_pr_url(url)
    if repo not in {r["id"] for r in discover_repos(root)}:
        raise SessionError("unknown_repo", f"el PR es de {repo}, que no está en el workspace")
    sid = normalize_id(f"pr-{repo}-{number}")
    if (found := _existing(root, sid, req)) is not None:
        return found
    if req.get("dry_run"):
        return {"session": {"id": sid, "kind": "review", "permissions": permissions,
                            "title": None},
                "prompt": "", "log": "", "dryRun": True,
                "existed": session_path(root, sid).exists()}
    pr = _gh_pr(url, runner)
    author = "@" + pr["author"]["login"]
    variables = {"id": sid, "title": pr["title"], "pr_url": url, "author": author, "repo": repo}
    # `prompt_file`: prompt de `.ide/prompts/` (p.ej. el botón de revisión) en vez de la plantilla
    text = (load_prompt(root, req["prompt_file"]) if req.get("prompt_file")
            else load_template(root, "review"))
    prompt = render_template(text, variables)
    create_session_dir(root, sid=sid, kind="review", permissions=permissions, prompt=prompt,
                       meta={"title": pr["title"], "author": author, "pr_url": url})
    log = io.StringIO()
    try:
        update_session_toml(root, sid, lambda d: d.update(pr_url=url, reviewed_sha=pr["headRefOid"]))
        _fetch_pr(root, repo, number, runner)
        try:
            add_repo(root, sid, repo, detach_at=pr["headRefOid"], out=log)
        except SessionError as exc:
            if exc.code != "setup_failed":
                raise
            log.write(f"\n{exc}\n")              # setup fallido: la sesión queda, marcada
    except Exception:
        wt = worktree_path(root, sid, repo)
        if wt.exists():
            subprocess.run(["git", "-C", str(root / repo), "worktree", "remove", "--force", str(wt)],
                           capture_output=True)
        shutil.rmtree(session_path(root, sid), ignore_errors=True)
        raise
    return {"session": read_session(root, sid), "log": log.getvalue()}


def check_delete(root: Path, sid: str, *, force: bool = False) -> list[str]:
    """Valida que la sesión se puede borrar (sin cambios sin commitear salvo force)."""
    spath = require_session(root, sid)
    repos = [p.name for p in spath.iterdir() if p.is_symlink()]
    if not force:
        dirty = [r for r in repos if worktree_path(root, sid, r).exists()
                 and has_uncommitted_changes(worktree_path(root, sid, r))]
        if dirty:
            raise SessionError("uncommitted_changes",
                               f"cambios sin commitear en {', '.join(dirty)} (usa --force)")
    return repos


def remove_session(root: Path, sid: str, *, force: bool = False) -> None:
    """Quita worktrees y carpeta (el proceso ya debe estar parado)."""
    spath = require_session(root, sid)
    for repo in [p.name for p in spath.iterdir() if p.is_symlink()]:
        rm_repo(root, sid, repo, force=force, out=io.StringIO())
    shutil.rmtree(spath)
    try:
        (root / ".ide" / "worktrees" / sid).rmdir()
    except OSError:
        pass


def delete_session(root: Path, sid: str, *, force: bool = False,
                   stop: Callable[[str], None] | None = None) -> None:
    check_delete(root, sid, force=force)
    if stop is not None:
        stop(sid)
    remove_session(root, sid, force=force)


def refresh_review(root: Path, sid: str, *, runner: Runner = _run) -> dict:
    data = read_toml(require_session(root, sid) / ".session.toml")
    url = data.get("pr_url")
    if data.get("kind") != "review" or not url:
        raise SessionError("not_a_review", f"{sid} no es una revisión de PR")
    repo, number = parse_pr_url(url)
    wt = worktree_path(root, sid, repo)
    if has_uncommitted_changes(wt):
        raise SessionError("uncommitted_changes", f"{repo} en {sid} tiene cambios sin commitear")
    sha = _gh_pr(url, runner)["headRefOid"]
    _fetch_pr(root, repo, number, runner)
    out = runner(["git", "-C", str(wt), "checkout", "--detach", sha])
    if out.returncode != 0:
        raise SessionError("checkout_failed", f"checkout del head nuevo falló: {out.stderr.strip()}")
    update_session_toml(root, sid, lambda d: d.update(reviewed_sha=sha))
    return read_session(root, sid)


def archive_path(root: Path, sid: str) -> Path:
    return root / ".ide" / "archive" / "sessions" / sid


def archived_worktree_path(root: Path, sid: str, repo: str) -> Path:
    return root / ".ide" / "archive" / "worktrees" / sid / repo


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SessionError("archive_failed",
                           f"git {' '.join(args)} en {cwd} falló: {out.stderr.strip() or out.returncode}")
    return out


def archive_session(root: Path, sid: str, *, force: bool = False, out=None) -> None:
    """Archiva (solo de ida): corre `archive` de cada repo, deja cada worktree en detach (la rama
    queda libre; los cambios sin commitear se conservan), borra los ignorados (`git clean -fdX`) y
    mueve worktrees y carpeta a `.ide/archive/`. El proceso ya debe estar parado."""
    from ide_server.scripts import has_script, run_script
    spath = require_session(root, sid)
    dest = archive_path(root, sid)
    if dest.exists():
        raise SessionError("session_archived", f"ya hay una sesión archivada {sid} ({dest})")
    repos = [p.name for p in spath.iterdir() if p.is_symlink()]
    branches: dict[str, str] = {}
    for repo in repos:
        wt = worktree_path(root, sid, repo)
        if not wt.exists():
            continue
        if has_script(root, repo, "archive"):
            code = run_script(root, sid, repo, "archive", out=out or io.StringIO())
            if code != 0 and not force:
                raise SessionError("archive_failed",
                                   f"archive de {repo} falló (exit {code}); archiva igual con force")
        branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch != "HEAD":
            branches[repo] = branch
            _git(wt, "checkout", "--detach")
        _git(wt, "clean", "-fdX")
        target = archived_worktree_path(root, sid, repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        _git(root / repo, "worktree", "move", str(wt), str(target))

    def _mark(d: dict) -> None:
        d.pop("ports", None)                    # el archivo no ocupa puertos
        d["archived"] = {"at": datetime.now().isoformat(timespec="seconds"), "branches": branches}
    update_session_toml(root, sid, _mark)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(spath), str(dest))
    for repo in repos:                          # symlinks → worktrees archivados
        link = dest / repo
        link.unlink(missing_ok=True)
        target = archived_worktree_path(root, sid, repo)
        if target.exists():
            link.symlink_to(os.path.relpath(target, dest))
    try:
        (root / ".ide" / "worktrees" / sid).rmdir()
    except OSError:
        pass


def create_pr_session(root: Path, url: str, *, runner: Runner = _run) -> dict:
    """Sesión para seguir trabajando una PR propia: sesión de ticket `dev-<repo>-<n>` con el
    worktree en la rama de la PR (la local sigue a `origin/<rama>`; si no existía, se crea así y
    no desde HEAD). Si ya existe, se devuelve. Ver spec 2026-10-16-desarrollos."""
    repo, number = parse_pr_url(url)
    if repo not in {r["id"] for r in discover_repos(root)}:
        raise SessionError("unknown_repo", f"la PR es de {repo}, que no está en el workspace")
    sid = normalize_id(f"dev-{repo}-{number}")
    if archive_path(root, sid).exists():
        raise SessionError("session_archived", f"la sesión {sid} está archivada")
    if session_path(root, sid).exists():
        return {"session": read_session(root, sid), "log": "", "existed": True}
    out = runner(["gh", "pr", "view", url, "--json", "title,headRefName,isCrossRepository,state"])
    if out.returncode != 0:
        raise SessionError("gh_failed", f"gh pr view falló: {out.stderr.strip() or out.returncode}")
    pr = json.loads(out.stdout)
    if pr.get("isCrossRepository"):
        raise SessionError("fork_pr", "la PR viene de un fork: su rama no está en el repo")
    if pr.get("state") != "OPEN":
        raise SessionError("pr_closed", "la PR ya no está abierta")
    branch, repo_path = pr["headRefName"], root / repo
    fetched = runner(["git", "-C", str(repo_path), "fetch", "origin",
                      f"+refs/heads/{branch}:refs/remotes/origin/{branch}"])
    if fetched.returncode != 0:
        raise SessionError("fetch_failed", f"git fetch de {branch}: {fetched.stderr.strip()}")
    local = runner(["git", "-C", str(repo_path), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"])
    if local.returncode != 0:                   # sin rama local: crearla siguiendo a origin
        made = runner(["git", "-C", str(repo_path), "branch", "--track", branch, f"origin/{branch}"])
        if made.returncode != 0:
            raise SessionError("checkout_failed", f"no pude crear la rama {branch}: {made.stderr.strip()}")
    create_session_dir(root, sid=sid, kind="ticket", permissions=_resolve_permissions(root, {}),
                       prompt="", meta={"title": pr["title"], "notion_url": None})
    log = io.StringIO()
    try:
        add_repo(root, sid, repo, branch=branch, out=log)
    except SessionError as exc:
        if exc.code != "setup_failed":
            shutil.rmtree(session_path(root, sid), ignore_errors=True)
            raise
        log.write(f"\n{exc}\n")                 # setup fallido: la sesión queda, marcada
    except Exception:
        shutil.rmtree(session_path(root, sid), ignore_errors=True)
        raise
    return {"session": read_session(root, sid), "log": log.getvalue()}
