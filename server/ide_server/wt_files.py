# server/ide_server/wt_files.py
"""Archivos de un worktree (módulo Archivos): listar, leer y guardar, confinado al worktree.

`lugar` = id de la sesión o `wt-<repo>-<n>` (ver `pr_worktrees`). Las rutas son relativas al
worktree; se resuelven (symlinks incluidos) y lo que cae afuera se rechaza."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from ide_server.repos_fs import worktree_path
from ide_server.sessions_fs import SessionError, require_plain_name

MAX_BYTES = 2 * 1024 * 1024
HIDDEN = {".git"}


def _base(root: Path, place: str, repo: str) -> Path:
    require_plain_name(place, "lugar")
    require_plain_name(repo, "repo")
    wt = worktree_path(root, place, repo)
    if not wt.is_dir():
        raise SessionError("unknown_worktree", f"no hay worktree de {repo} en {place}")
    return wt.resolve()


def _target(base: Path, rel: str) -> Path:
    if not isinstance(rel, str) or rel.startswith("/") or "\0" in rel:
        raise SessionError("bad_path", f"ruta inválida: {rel!r}")
    p = (base / rel).resolve() if rel else base
    if p != base and base not in p.parents:
        raise SessionError("bad_path", f"{rel} queda fuera del worktree")
    if any(part in HIDDEN for part in p.relative_to(base).parts):
        raise SessionError("bad_path", f"{rel}: .git no se edita desde acá")
    return p


def list_dir(root: Path, place: str, repo: str, rel: str = "") -> dict:
    base = _base(root, place, repo)
    d = _target(base, rel)
    if not d.is_dir():
        raise SessionError("not_a_dir", f"{rel} no es una carpeta")
    entries = []
    for e in d.iterdir():
        if e.name in HIDDEN:
            continue
        try:
            is_dir = e.is_dir()
            size = None if is_dir else e.stat().st_size
        except OSError:                         # symlink roto
            is_dir, size = False, None
        entries.append({"name": e.name, "type": "dir" if is_dir else "file", "size": size})
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    return {"entries": entries}


def env_files(root: Path, place: str, repo: str) -> list[str]:
    """Los `.env*` de la raíz del worktree (acceso directo)."""
    base = _base(root, place, repo)
    return sorted(p.name for p in base.iterdir() if p.name.startswith(".env") and p.is_file())


def read(root: Path, place: str, repo: str, rel: str) -> dict:
    p = _target(_base(root, place, repo), rel)
    if not p.is_file():
        raise SessionError("not_found", f"no existe {rel}")
    size = p.stat().st_size
    if size > MAX_BYTES:
        raise SessionError("too_large", f"{rel} pesa {size // 1024} KB (máx. {MAX_BYTES // 1024 // 1024} MB)")
    raw = p.read_bytes()
    if b"\0" in raw[:8192]:
        raise SessionError("binary", f"{rel} es binario")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SessionError("binary", f"{rel} no es UTF-8")
    return {"text": text, "mtime": p.stat().st_mtime_ns}


def write(root: Path, place: str, repo: str, rel: str, text: str, mtime: int | None) -> dict:
    """Guarda. Si el archivo cambió en disco desde que se leyó (`mtime`), no pisa: `changed_on_disk`."""
    if not isinstance(text, str):
        raise SessionError("bad_request", "text debe ser texto")
    p = _target(_base(root, place, repo), rel)
    if p.is_dir():
        raise SessionError("bad_path", f"{rel} es una carpeta")
    if p.exists() and mtime is not None and p.stat().st_mtime_ns != mtime:
        raise SessionError("changed_on_disk", f"{rel} cambió en disco desde que lo abriste: recárgalo")
    if not p.parent.is_dir():
        raise SessionError("bad_path", f"no existe la carpeta de {rel}")
    # temporal con nombre aleatorio y creado en exclusiva (O_EXCL): un nombre fijo podría venir en el
    # repo como symlink (p.ej. en una PR ajena) y la escritura saldría del worktree
    fd, tmp_name = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".ide-tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if p.exists():
            os.chmod(tmp, p.stat().st_mode)
        os.replace(tmp, p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return {"mtime": p.stat().st_mtime_ns}
