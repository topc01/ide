# server/ide_server/pr_changes.py
"""Cambios de una PR (módulo Stack): archivos cambiados y el diff de cada uno, con git local.

Se compara contra el punto donde la rama sale de su base (merge-base): en un stack, la base es la
rama de la PR de abajo, así que se ve solo lo de esa PR. Las refs se traen a `refs/ide/…` del repo
principal (no tocan sus ramas). Si la rama está checkouteada en un worktree del IDE, el lado nuevo es
ese worktree (incluye lo no commiteado y los archivos nuevos sin trackear)."""
from __future__ import annotations
import subprocess
import threading
import time
from pathlib import Path
from ide_server.sessions_fs import SessionError
from ide_server.workspace import discover_repos

MAX_BYTES = 1024 * 1024
FETCH_TTL = 30                                   # s: no volver a traer la misma PR en cada click
_fetched: dict[str, float] = {}
_lock = threading.Lock()


def _git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)
    if check and out.returncode != 0:
        raise SessionError("git_failed", f"git {' '.join(args[:3])}: {out.stderr.strip() or out.returncode}")
    return out.stdout


def _repo(root: Path, pr: dict) -> Path:
    if pr.get("repo") not in {r["id"] for r in discover_repos(root)}:
        raise SessionError("unknown_repo", f"{pr.get('repo')} no está en el workspace")
    return root / pr["repo"]


def _refs(root: Path, pr: dict) -> tuple[Path, str, str]:
    """(repo, ref de la base, ref del head) ya traídos."""
    repo = _repo(root, pr)
    head, base = f"refs/ide/pr/{pr['number']}", f"refs/ide/base/{pr['base']}"
    with _lock:
        if time.time() - _fetched.get(pr["url"], 0) > FETCH_TTL:
            _git(repo, "fetch", "--quiet", "--no-tags", "origin",
                 f"+refs/pull/{pr['number']}/head:{head}", f"+refs/heads/{pr['base']}:{base}")
            _fetched[pr["url"]] = time.time()
    return repo, base, head


def _local_worktree(repo: Path, branch: str | None) -> Path | None:
    """El worktree del IDE donde está checkouteada la rama (si hay)."""
    if not branch:
        return None
    path = None
    for line in _git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:])
        elif line == f"branch refs/heads/{branch}" and path and "/.ide/worktrees/" in str(path):
            return path
    return None


_cache: dict[str, tuple[float, dict]] = {}


def changes(root: Path, pr: dict, *, fresh: bool = False) -> dict:
    """Con caché de FETCH_TTL (el fetch a GitHub es lo lento); `fresh` la salta (botón ↻)."""
    hit = _cache.get(pr["url"])
    if hit and not fresh and time.time() - hit[0] < FETCH_TTL:
        return hit[1]
    if fresh:
        _fetched.pop(pr["url"], None)
    data = _changes(root, pr)
    _cache[pr["url"]] = (time.time(), data)
    return data


def _changes(root: Path, pr: dict) -> dict:
    repo, base, head = _refs(root, pr)
    mb = _git(repo, "merge-base", base, head).strip()
    wt = _local_worktree(repo, pr.get("head"))
    where, rng = (wt, [mb]) if wt else (repo, [mb, head])
    files: dict[str, dict] = {}
    for line in _git(where, "diff", "--name-status", "-M", *rng).splitlines():
        parts = line.split("\t")
        st = parts[0][0]
        path = parts[-1]
        files[path] = {"path": path, "oldPath": parts[1] if st == "R" else None, "status": st,
                       "additions": 0, "deletions": 0}
    for line in _git(where, "diff", "--numstat", "-M", *rng).splitlines():
        a, d, path = line.split("\t", 2)
        path = path.split(" => ")[-1].replace("}", "").split("{")[-1] if " => " in path else path
        f = files.get(path)
        if f:
            f["additions"], f["deletions"] = (int(a) if a.isdigit() else 0), (int(d) if d.isdigit() else 0)
    if wt:                                        # archivos nuevos sin trackear
        for path in _git(wt, "ls-files", "--others", "--exclude-standard").splitlines():
            files.setdefault(path, {"path": path, "oldPath": None, "status": "?", "additions": 0, "deletions": 0})
    return {"files": sorted(files.values(), key=lambda f: f["path"]), "base": pr["base"], "mergeBase": mb[:10],
            "local": str(wt) if wt else None}


def _show(repo: Path, rev: str, path: str) -> str | None:
    out = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True, timeout=60)
    return None if out.returncode != 0 else _text(out.stdout, path)


def _text(raw: bytes, path: str) -> str:
    if len(raw) > MAX_BYTES:
        raise SessionError("too_large", f"{path} pesa más de {MAX_BYTES // 1024} KB")
    if b"\0" in raw[:8192]:
        raise SessionError("binary", f"{path} es binario")
    return raw.decode("utf-8", "replace")


def file_diff(root: Path, pr: dict, path: str, old_path: str | None = None) -> dict:
    """Contenido viejo (en el merge-base) y nuevo (head o el worktree local) de un archivo."""
    if not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts:
        raise SessionError("bad_path", f"ruta inválida: {path!r}")
    repo, base, head = _refs(root, pr)
    mb = _git(repo, "merge-base", base, head).strip()
    old = _show(repo, mb, old_path or path)
    wt = _local_worktree(repo, pr.get("head"))
    if wt:
        f = (wt / path).resolve()
        if f != wt.resolve() and wt.resolve() not in f.parents:      # symlink que sale del worktree
            raise SessionError("bad_path", f"{path} queda fuera del worktree")
        new = _text(f.read_bytes(), path) if f.is_file() else None
    else:
        new = _show(repo, head, path)
    return {"old": old, "new": new, "local": bool(wt)}
