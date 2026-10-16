# server/ide_server/capabilities/runs.py
"""Canales de los módulos Servidores (scripts corriendo en un worktree, worktrees de PR) y Archivos."""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from ide_server import pr_worktrees, wt_files
from ide_server.plugins import Registry
from ide_server.runs import Runner
from ide_server.scripts import has_script

log = logging.getLogger(__name__)
POLL = 2.0


def register(registry: Registry, root: Path, manager, runner: Runner):
    last: dict = {"payload": None}

    def payload() -> dict:
        return {"runs": runner.list(), "places": pr_worktrees.list_places(root)}

    async def broadcast() -> None:
        p = await asyncio.to_thread(payload)
        if p != last["payload"]:
            last["payload"] = p
            await manager.broadcast("runs.changed", p)

    async def watch(stop: asyncio.Event) -> None:
        """Detecta servidores que terminan solos (o que arrancó/paró otro) y avisa."""
        while not stop.is_set():
            try:
                await broadcast()
            except Exception:  # noqa: BLE001
                log.exception("no se pudo emitir runs.changed")
            try:
                await asyncio.wait_for(stop.wait(), POLL)
            except asyncio.TimeoutError:
                pass

    def _args(p: dict) -> tuple[str, str, str]:
        return p["place"], p["repo"], p["name"]

    async def list_(_p: dict) -> dict:
        return await asyncio.to_thread(payload)

    async def start(p: dict) -> dict:
        r = await asyncio.to_thread(runner.start, *_args(p))
        await broadcast()
        return r

    async def stop(p: dict) -> dict:
        r = await asyncio.to_thread(runner.stop, *_args(p))
        await broadcast()
        return r

    async def log_(p: dict) -> dict:
        return await asyncio.to_thread(runner.log, *_args(p), int(p.get("offset", -1)))

    async def wt_ensure(p: dict) -> dict:
        res = await asyncio.to_thread(pr_worktrees.ensure, root, p["url"])
        if res["created"] and has_script(root, res["repo"], "setup"):   # como al agregar un repo a una sesión
            await asyncio.to_thread(runner.start, res["place"], res["repo"], "setup")
        await broadcast()
        return res

    async def wt_update(p: dict) -> dict:
        return await asyncio.to_thread(pr_worktrees.update, root, p["url"])

    async def wt_remove(p: dict) -> dict:
        await asyncio.to_thread(runner.stop_place, p["place"])
        await asyncio.to_thread(pr_worktrees.remove, root, p["place"], force=bool(p.get("force")))
        await broadcast()
        return {"ok": True}

    async def files_list(p: dict) -> dict:
        return await asyncio.to_thread(wt_files.list_dir, root, p["place"], p["repo"], p.get("path", ""))

    async def files_envs(p: dict) -> dict:
        return {"files": await asyncio.to_thread(wt_files.env_files, root, p["place"], p["repo"])}

    async def files_read(p: dict) -> dict:
        return await asyncio.to_thread(wt_files.read, root, p["place"], p["repo"], p["path"])

    async def files_write(p: dict) -> dict:
        return await asyncio.to_thread(wt_files.write, root, p["place"], p["repo"], p["path"],
                                       p["text"], p.get("mtime"))

    for channel, handler in {
        "runs.list": list_, "runs.start": start, "runs.stop": stop, "runs.log": log_,
        "prwt.ensure": wt_ensure, "prwt.update": wt_update, "prwt.remove": wt_remove,
        "wtfiles.list": files_list, "wtfiles.envs": files_envs, "wtfiles.read": files_read,
        "wtfiles.write": files_write,
    }.items():
        registry.register(channel, handler)
    return watch
