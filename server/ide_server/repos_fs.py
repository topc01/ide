# server/ide_server/repos_fs.py
from __future__ import annotations
import os
import subprocess
import tomllib
from pathlib import Path
from typing import TextIO
from ide_server.sessions_fs import (
    SessionError, session_path, sessions_dir, read_toml, update_session_toml, workspace_lock,
)
from ide_server.workspace import discover_repos
from ide_server.worktrees import add_worktree, remove_worktree, has_uncommitted_changes

PORT_BASE = 8100
PORT_STEP = 10


def worktree_path(root: Path, sid: str, repo: str) -> Path:
    return root / ".ide" / "worktrees" / sid / repo


def require_session(root: Path, sid: str) -> Path:
    path = session_path(root, sid)
    if not (path / ".session.toml").is_file():
        raise SessionError("unknown_session", f"no existe la sesión {sid}")
    return path


def _repo_root(root: Path, repo: str) -> Path:
    names = [r["id"] for r in discover_repos(root)]
    if repo not in names:
        raise SessionError("unknown_repo",
                           f"repo desconocido: {repo} (repos: {', '.join(names) or 'ninguno'})")
    return root / repo


def _used_ports(root: Path) -> set[int]:
    used: set[int] = set()
    d = sessions_dir(root)
    if not d.is_dir():
        return used
    for p in d.iterdir():
        try:
            used.update(int(v) for v in read_toml(p / ".session.toml").get("ports", {}).values())
        except (OSError, tomllib.TOMLDecodeError, ValueError, TypeError, AttributeError):
            continue                            # ports malformado: no bloquea la asignación
    return used


def allocate_port(root: Path) -> int:
    used, port = _used_ports(root), PORT_BASE
    while port in used:
        port += PORT_STEP
    return port


def add_repo(root: Path, sid: str, repo: str, *, branch: str | None = None,
             detach_at: str | None = None, out: TextIO | None = None) -> dict:
    with workspace_lock(root):                  # worktree + puerto + toml, atómico
        branch_name, wt, port = _add_worktree_locked(root, sid, repo, branch, detach_at)
    from ide_server.scripts import has_script, run_script
    if has_script(root, repo, "setup"):
        code = run_script(root, sid, repo, "setup", out=out)
        if code != 0:
            raise SessionError("setup_failed",
                               f"setup de {repo} falló (exit {code}); reintenta con "
                               f"`ide script setup {repo}`")
    return {"name": repo, "branch": branch_name, "path": str(wt), "port": port}


def _add_worktree_locked(root: Path, sid: str, repo: str, branch: str | None,
                         detach_at: str | None) -> tuple[str | None, Path, int]:
    spath = require_session(root, sid)
    repo_path = _repo_root(root, repo)
    link, wt = spath / repo, worktree_path(root, sid, repo)
    if link.is_symlink() or wt.exists():
        raise SessionError("repo_exists", f"{repo} ya está en la sesión {sid}")
    wt.parent.mkdir(parents=True, exist_ok=True)
    if detach_at:
        add_worktree(repo_path, wt, detach_at, access="ro", base=detach_at)
        branch_name = None
    else:
        if not branch:                              # `<login>/d12-<nombre>`; sin número, el id de la sesión
            from ide_server.devs import dev_env
            branch = dev_env(root, sid).get("IDE_DEV_BRANCH")
        branch_name = branch or sid
        add_worktree(repo_path, wt, branch_name, access="rw")
    try:
        link.symlink_to(os.path.relpath(wt, link.parent))
        port = allocate_port(root)
        update_session_toml(root, sid, lambda d: d.setdefault("ports", {}).update({repo: port}))
    except Exception:
        link.unlink(missing_ok=True)
        remove_worktree(repo_path, wt, force=True)
        raise
    return branch_name, wt, port


def rm_repo(root: Path, sid: str, repo: str, *, force: bool = False,
            out: TextIO | None = None) -> None:
    spath = require_session(root, sid)
    link, wt = spath / repo, worktree_path(root, sid, repo)
    if not link.is_symlink() and not wt.exists():
        raise SessionError("repo_not_in_session", f"{repo} no está en la sesión {sid}")
    repo_path = root / repo
    from ide_server.scripts import has_script, run_script
    if wt.exists() and not force and has_uncommitted_changes(wt):
        raise SessionError("uncommitted_changes",
                           f"{repo} en {sid} tiene cambios sin commitear (usa --force)")
    if wt.exists() and has_script(root, repo, "archive"):
        code = run_script(root, sid, repo, "archive", out=out)
        if code != 0 and not force:
            raise SessionError("archive_failed",
                               f"archive de {repo} falló (exit {code}); usa --force para quitarlo igual")
    if wt.exists():
        remove_worktree(repo_path, wt, force=force)
    else:
        subprocess.run(["git", "-C", str(repo_path), "worktree", "prune"], capture_output=True)
    link.unlink(missing_ok=True)

    def _drop(d: dict) -> None:
        d.get("ports", {}).pop(repo, None)
        d.get("setup", {}).pop(repo, None)
    update_session_toml(root, sid, _drop)
    try:
        wt.parent.rmdir()
    except OSError:
        pass
