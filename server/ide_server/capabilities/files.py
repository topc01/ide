from __future__ import annotations
import os
import shlex
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.workspace import resolve_cwd


def _safe_join(root: Path, rel: str) -> Path:
    root = root.resolve()
    target = (root / (rel or "")).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path fuera de la raíz")
    return target


def register(registry: Registry, root: Path) -> None:
    async def list_(payload: dict) -> dict:
        base = resolve_cwd(root, payload)
        target = _safe_join(base, payload.get("path") or "")
        if not target.is_dir():
            raise ValueError(f"no es un directorio: {payload.get('path')!r}")
        entries = [
            {"name": p.name, "type": "dir" if p.is_dir() else "file"}
            for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        ]
        return {"entries": entries}

    async def open_(payload: dict) -> dict:
        base = resolve_cwd(root, payload)
        target = _safe_join(base, payload.get("path") or "")
        editor = shlex.split(os.environ.get("EDITOR") or "vim")
        line = payload.get("line")
        cmd = editor + ([f"+{int(line)}"] if line else []) + [str(target)]
        return await registry.dispatch(
            "terminal.open",
            {"sessionId": payload.get("sessionId"), "cmd": cmd},
        )

    registry.register("files.list", list_)
    registry.register("files.open", open_)
