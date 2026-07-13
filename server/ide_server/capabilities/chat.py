from __future__ import annotations
import asyncio
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.chat.driver import ClaudeDriver
from ide_server.chat.permissions import resolve_permission
from ide_server.chat.events import to_payload

_LANG = "Respondé siempre en español."

def _load_session_context(root: Path, session_id: str) -> dict:
    # Devuelve {cwd, system_prompt, role, model} de la sesión. Resuelve el rol
    # real (preset de .ide/config.toml) para que permisos y modelo se apliquen.
    from ide_server.sessions_store import load_sessions, find_node
    from ide_server.roles import resolve_role
    tree = load_sessions(root)
    node = find_node(tree, session_id)
    if node is None:
        raise KeyError(session_id)
    cwd = node.get("worktreePath") or str(root)
    role_name = node.get("role")
    r = resolve_role(root, role_name)
    desc = node.get("description") or ""
    system_prompt = "\n\n".join(
        [_LANG] + [p for p in [desc, r.system_prompt if r else None] if p]
    ) or _LANG
    role = {"read_only": r.read_only} if r is not None else None
    model = r.model if r else None
    return {"cwd": cwd, "system_prompt": system_prompt, "role": role, "model": model}

def register(registry: Registry, root: Path, manager, driver_factory=None) -> None:
    factory = driver_factory or ClaudeDriver
    drivers: dict[str, object] = {}
    pending: dict[str, asyncio.Future] = {}
    broadcast_tasks: list[asyncio.Task] = []

    def _emit(session_id: str, event: object) -> None:
        task = asyncio.create_task(manager.broadcast(f"chat.event.{session_id}", to_payload(event)))
        broadcast_tasks.append(task)

    async def _flush_broadcasts() -> None:
        if not broadcast_tasks:
            return
        tasks, broadcast_tasks[:] = list(broadcast_tasks), []
        # return_exceptions: un socket muerto en un broadcast (posiblemente de otra
        # sesión, ya que la lista es compartida) no debe tumbar la respuesta de este
        # handler. La caída de conexión la maneja la capa WS ("desconectado" + resume).
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _await_permission(session_id: str, request_id: str) -> bool:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        pending[request_id] = fut
        try:
            return await fut
        finally:
            pending.pop(request_id, None)

    async def start(payload: dict) -> dict:
        sid = payload["sessionId"]
        if sid in drivers:
            return {"started": True, "resumed": True}
        ctx = _load_session_context(root, sid)
        mode, allowed = resolve_permission(ctx["role"], payload.get("override"))
        driver = factory(
            cwd=ctx["cwd"], system_prompt=ctx["system_prompt"],
            permission_mode=mode, allowed_tools=allowed, model=ctx.get("model"),
            on_event=lambda e, s=sid: _emit(s, e),
            on_permission=lambda req_id, s=sid: _await_permission(s, req_id),
        )
        await driver.start()
        drivers[sid] = driver
        await _flush_broadcasts()
        return {"started": True, "resumed": False}

    async def send(payload: dict) -> dict:
        await drivers[payload["sessionId"]].send(payload["text"])
        await _flush_broadcasts()
        return {"sent": True}

    async def interrupt(payload: dict) -> dict:
        await drivers[payload["sessionId"]].interrupt()
        await _flush_broadcasts()
        return {"interrupted": True}

    async def permission(payload: dict) -> dict:
        fut = pending.get(payload["requestId"])
        if fut is not None and not fut.done():
            fut.set_result(bool(payload["allow"]))
        return {"resolved": True}

    registry.register("chat.start", start)
    registry.register("chat.send", send)
    registry.register("chat.interrupt", interrupt)
    registry.register("chat.permission", permission)
