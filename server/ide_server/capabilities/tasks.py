from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.tasks import store


def register(registry: Registry, root: Path) -> None:
    async def list_(_p: dict) -> dict:
        return {"tasks": store.list_tasks(root)}

    async def read(p: dict) -> dict:
        return store.read_task(root, p["id"])

    async def save(p: dict) -> dict:
        return store.write_task(root, p["id"], p["markdown"])

    async def create(p: dict) -> dict:
        return {"task": store.create_task(root, p["name"])}

    for name, fn in [("list", list_), ("read", read), ("save", save), ("create", create)]:
        registry.register(f"tasks.{name}", fn)
