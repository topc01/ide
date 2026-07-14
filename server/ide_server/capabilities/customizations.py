from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.customizations.items import build_items


def register(registry: Registry, root: Path, home: Path | None = None) -> None:
    base = home or Path.home()

    async def list_(_payload: dict) -> dict:
        return {"items": build_items(base, root)}

    registry.register("customizations.list", list_)
