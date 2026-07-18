from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server import git
from ide_server.workspace import resolve_cwd


def register(registry: Registry, root: Path) -> None:
    async def list_(payload: dict) -> dict:
        return {"status": git.repo_status(resolve_cwd(root, payload))}

    async def diff_(payload: dict) -> dict:
        cwd = resolve_cwd(root, payload)
        return {"lines": git.file_diff_full(cwd, payload["path"], payload.get("status") or "M")}

    registry.register("changes.list", list_)
    registry.register("changes.diff", diff_)
