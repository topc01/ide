# server/ide_server/pr_worktrees.py
"""Worktree de una PR sin sesión, para levantarla en local (módulo Servidores / Archivos).

Vive en `.ide/worktrees/wt-<repo>-<n>/<repo>`, en detach sobre el head de la PR
(`refs/pull/<n>/head`): no ocupa la rama, así que no choca con otro checkout ni con una sesión
que se cree después. Al quitarlo se paran sus servidores y corre `archive` del repo."""
from __future__ import annotations
import io
import shutil
import subprocess
from pathlib import Path
from ide_server.repos_fs import _repo_root, worktree_path
from ide_server.session_ops import parse_pr_url
from ide_server.sessions_fs import SessionError, normalize_id, workspace_lock

PREFIX = "wt-"


def place_for(url: str) -> tuple[str, str, int]:
    repo, number = parse_pr_url(url)
    return normalize_id(f"{PREFIX}{repo}-{number}"), repo, number


def _git(cwd: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise SessionError("git_failed", f"git {' '.join(args)}: {out.stderr.strip() or out.returncode}")
    return out


def list_places(root: Path) -> list[dict]:
    base = root / ".ide" / "worktrees"
    if not base.is_dir():
        return []
    return [{"id": p.name, "repos": sorted(r.name for r in p.iterdir() if r.is_dir())}
            for p in sorted(base.iterdir()) if p.is_dir() and p.name.startswith(PREFIX)]


def ensure(root: Path, url: str) -> dict:
    place, repo, number = place_for(url)
    repo_path = _repo_root(root, repo)
    wt = worktree_path(root, place, repo)
    if wt.is_dir():
        return {"place": place, "repo": repo, "path": str(wt), "created": False}
    _git(repo_path, "fetch", "origin", f"refs/pull/{number}/head")
    with workspace_lock(root):
        wt.parent.mkdir(parents=True, exist_ok=True)
        _git(repo_path, "worktree", "add", "--detach", str(wt), "FETCH_HEAD")
    return {"place": place, "repo": repo, "path": str(wt), "created": True}


def update(root: Path, url: str) -> dict:
    """Mueve el worktree al head actual de la PR (si no tiene cambios sin commitear)."""
    place, repo, number = place_for(url)
    wt = worktree_path(root, place, repo)
    if not wt.is_dir():
        raise SessionError("unknown_worktree", f"no hay worktree para {repo}#{number}")
    if _git(wt, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise SessionError("uncommitted_changes", f"{wt} tiene cambios sin commitear: no lo muevo")
    _git(wt, "fetch", "origin", f"refs/pull/{number}/head")
    _git(wt, "checkout", "--detach", "FETCH_HEAD")
    return {"place": place, "repo": repo, "head": _git(wt, "rev-parse", "--short", "HEAD").stdout.strip()}


def remove(root: Path, place: str, *, force: bool = False) -> None:
    """Corre `archive` de cada repo y quita los worktrees (los servidores ya deben estar parados)."""
    from ide_server.scripts import has_script, run_script
    if not place.startswith(PREFIX):
        raise SessionError("bad_place", f"{place} no es un worktree de PR")
    base = root / ".ide" / "worktrees" / normalize_id(place)
    if not base.is_dir():
        return
    for wt in sorted(p for p in base.iterdir() if p.is_dir()):
        repo = wt.name
        if has_script(root, repo, "archive"):
            code = run_script(root, place, repo, "archive", out=io.StringIO())
            if code != 0 and not force:
                raise SessionError("archive_failed", f"archive de {repo} falló (exit {code}); quítalo igual con force")
        _git(_repo_root(root, repo), "worktree", "remove", "--force", str(wt))
    shutil.rmtree(base, ignore_errors=True)
    shutil.rmtree(root / ".ide" / "runs" / place, ignore_errors=True)
