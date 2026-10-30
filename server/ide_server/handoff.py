# server/ide_server/handoff.py
"""`ide handoff`: traspasa un desarrollo de otra herramienta (un workspace de Conductor) al IDE.

Mueve el worktree entero (`git worktree move`) a `.ide/worktrees/<sesión>/<repo>`: viajan los
cambios sin commitear, `node_modules`, los `.env*` (y con ellos la base y el proyecto docker de la
api, pineados ahí). La sesión que lo recibe es la del mismo ticket de Notion si existe (queda
fullstack), si no una de ticket nueva. Al SESSION.md se le agrega el resumen de traspaso y la ruta
de los transcripts de la sesión anterior. La sesión queda creada, sin lanzar `claude`."""
from __future__ import annotations
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from ide_server.db import Db
from ide_server.devs import STATUSES, normalize, set_status, sync_from_disk
from ide_server.repos_fs import allocate_port, worktree_path
from ide_server.session_ops import create_session, notion_session_id
from ide_server.sessions_fs import (
    SessionError, list_sessions, parse_frontmatter, require_plain_name, session_path, update_session_toml,
    workspace_lock, write_frontmatter,
)
from ide_server.workspace import discover_repos

_NOTION_HEX = re.compile(r"[0-9a-f]{32}")


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SessionError("git_failed", f"git {' '.join(args)} en {cwd}: {out.stderr.strip() or out.returncode}")
    return out.stdout.strip()


def _source(root: Path, src: Path) -> tuple[str, Path, str | None]:
    """(repo, repo principal, rama) del worktree a traspasar; tiene que ser de un repo del workspace."""
    if not src.is_dir():
        raise SessionError("bad_path", f"no existe {src}")
    top = Path(_git(src, "rev-parse", "--show-toplevel")).resolve()
    if top != src:
        raise SessionError("bad_path", f"{src} no es la raíz de un worktree (la raíz es {top})")
    common = Path(_git(src, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    repo_path = common.parent
    repos = {(root / r["id"]).resolve(): r["id"] for r in discover_repos(root)}
    if repo_path not in repos:
        raise SessionError("unknown_repo", f"{src} es un worktree de {repo_path}, que no es un repo del workspace {root}")
    if src == repo_path:
        raise SessionError("bad_path", f"{src} es el checkout principal del repo, no un worktree")
    branch = _git(src, "rev-parse", "--abbrev-ref", "HEAD")
    return repos[repo_path], repo_path, None if branch == "HEAD" else branch


def _busy(src: Path) -> list[str]:
    """Procesos con la ruta del worktree en su comando (vite, scripts…): moverlo los rompería."""
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    me = {os.getpid(), os.getppid()}
    hits = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if f"{src}/" in cmd or cmd.endswith(str(src)):
            if pid.isdigit() and int(pid) not in me:
                hits.append(f"{pid} {cmd[:120]}")
    return hits


def transcripts(src: Path, home: Path) -> list[Path]:
    """Transcripts de Claude Code de las sesiones que corrieron en esa carpeta (más nuevo primero)."""
    d = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(src))
    if not d.is_dir():
        return []
    return sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]


def _session_for(root: Path, notion: str | None, explicit: str | None, title: str | None) -> tuple[str, bool]:
    if explicit:
        sid = require_plain_name(explicit, "sesión")
        if not (session_path(root, sid) / ".session.toml").is_file():
            raise SessionError("unknown_session", f"no existe la sesión {sid}")
        return sid, False
    if notion:
        target = notion_session_id(notion)
        for s in list_sessions(root):                   # la del mismo ticket (aunque tenga otro id)
            stored = (s.get("meta") or {}).get("notion_url") or ""
            if s["id"] == target or (stored and notion_session_id(stored) == target):
                return s["id"], False
    res = create_session(root, {**{k: v for k, v in {"notion": notion, "title": title}.items() if v}, "handoff": True})
    return res["session"]["id"], True


def _append_ticket(root: Path, sid: str, text: str) -> None:
    f = session_path(root, sid) / "SESSION.md"
    meta, body = parse_frontmatter(f.read_text(encoding="utf-8")) if f.is_file() else ({}, "")
    f.write_text(write_frontmatter(meta, body.rstrip() + ("\n\n" if body.strip() else "") + text), encoding="utf-8")


def handoff(root: Path, src: Path, *, summary: str, home: Path, notion: str | None = None,
            title: str | None = None, session: str | None = None, status: str | None = None,
            force: bool = False) -> dict:
    src = src.expanduser().resolve()
    if notion:                                  # URL o id: se queda solo el id (32 hex)
        found_id = _NOTION_HEX.findall(notion.strip().replace("-", "").lower())
        if not found_id:
            raise SessionError("bad_notion_url", f"--notion: no encuentro el id de la página (32 hex) en {notion!r}")
        notion = found_id[-1]
    status = normalize("ticket", status)
    if status and status not in STATUSES["ticket"]:
        raise SessionError("bad_status", f"estado inválido: {status!r} ({' | '.join(STATUSES['ticket'])})")
    if not summary.strip():
        raise SessionError("bad_request", "falta el resumen de traspaso (--summary-file)")
    # título: --title o la primera línea "# …" del resumen (así el texto no pasa por la shell)
    m = re.match(r"\s*#\s+(.+)", summary)
    if m and not title:
        title = m.group(1).strip()
        summary = summary[m.end():].lstrip("\n")
    repo, repo_path, branch = _source(root, src)
    busy = _busy(src)
    if busy and not force:
        raise SessionError("busy", "hay procesos corriendo desde ese worktree (páralos antes; moverlo los "
                                   "rompería):\n  " + "\n  ".join(busy))
    found = transcripts(src, home)
    sid, created = _session_for(root, notion, session, title)
    wt = worktree_path(root, sid, repo)
    link = session_path(root, sid) / repo
    with workspace_lock(root):
        if link.is_symlink() or wt.exists():
            raise SessionError("repo_exists", f"{repo} ya está en la sesión {sid}")
        wt.parent.mkdir(parents=True, exist_ok=True)
        _git(repo_path, "worktree", "move", str(src), str(wt))
        link.symlink_to(os.path.relpath(wt, link.parent))
        port = allocate_port(root)
        update_session_toml(root, sid, lambda d: d.setdefault("ports", {}).update({repo: port}))
    when = datetime.now().isoformat(timespec="minutes")
    lines = [f"## Traspaso desde Conductor ({repo}, {when})", "",
             f"- Workspace anterior: `{src}` (movido a `{wt}`)",
             f"- Rama: `{branch or '(detach)'}`"]
    if found:
        lines.append(f"- Transcript de la sesión anterior (léelo si necesitas detalle): `{found[0]}`")
        lines += [f"  - otro anterior: `{p}`" for p in found[1:]]
    _append_ticket(root, sid, "\n".join(lines) + "\n\n" + summary.strip() + "\n")
    db = Db(root)
    sync_from_disk(root, db)
    db.event(datetime.now().isoformat(timespec="seconds"), "handoff", "handoff", dev=sid,
             data={"repo": repo, "from": str(src), "branch": branch, "created": created})
    if status:
        set_status(root, db, sid, status, actor="handoff")
    return {"session": sid, "created": created, "repo": repo, "branch": branch, "path": str(wt),
            "port": port, "transcripts": [str(p) for p in found]}
