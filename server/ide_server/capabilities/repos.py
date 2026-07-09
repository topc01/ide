from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.workspace import discover_repos


def register(registry: Registry, root: Path) -> None:
    async def handle(_payload: dict) -> dict:
        return {"repos": discover_repos(root)}
    registry.register("repos.list", handle)
