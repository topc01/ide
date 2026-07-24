from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.chat.events import Routed, TextDelta, Done, ChatError

_LANG = "Respondé siempre en español."


def _load_session_context(root: Path, session_id: str) -> dict:
    # Devuelve {cwd, system_prompt, role, model, is_coordinator} de la sesión.
    # Resuelve el rol real (preset de .ide/config.toml) para que permisos y
    # modelo se apliquen. `is_coordinator` marca sesiones sin worktree propio
    # (comandan hijas multi-repo) — lo usa el SessionHub para decidir si cablea
    # el servidor MCP de orquestación.
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
    return {"cwd": cwd, "system_prompt": system_prompt, "role": role, "model": model,
            "is_coordinator": node.get("worktreePath") is None}


def register(registry: Registry, root: Path, manager, driver_factory=None, hub=None, mlx_router=None):
    from ide_server.chat.session_hub import SessionHub
    hub = hub or SessionHub(root, manager, driver_factory)

    async def start(payload: dict) -> dict:
        sid = payload["sessionId"]
        resumed = hub.has(sid)
        await hub.ensure_started(sid, override=payload.get("override"))
        return {"started": True, "resumed": resumed}

    async def send(payload: dict) -> dict:
        sid, text = payload["sessionId"], payload["text"]
        force = payload.get("route")                        # None | "local" | "claude" (override manual)
        if force == "local" and mlx_router is None:
            await hub.emit(sid, ChatError(code="mlx_off",
                                          message="mlx no está configurado en este proyecto"))
            return {"sent": False}
        decision = await mlx_router.decide(text, force=force) if mlx_router is not None else None
        if decision is None:
            await hub.send_human(sid, text)                 # mlx off → como hoy
            return {"sent": True}
        if decision.degraded:
            await hub.emit(sid, ChatError(code="mlx_unavailable",
                                          message="modelo local no disponible, usando Claude"))
        if decision.route == "local":
            await hub.emit(sid, Routed(source="local"))
            await hub.emit(sid, TextDelta(text=decision.reply or ""))
            await hub.emit(sid, Done(session_id=sid, is_error=False))
            return {"sent": True, "route": "local"}
        await hub.emit(sid, Routed(source="claude"))
        await hub.send_human(sid, text)
        return {"sent": True, "route": "claude"}

    async def interrupt(payload: dict) -> dict:
        await hub.interrupt(payload["sessionId"])
        return {"interrupted": True}

    async def permission(payload: dict) -> dict:
        hub.resolve_permission_future(payload["requestId"], bool(payload["allow"]))
        return {"resolved": True}

    for ch, fn in {"chat.start": start, "chat.send": send,
                   "chat.interrupt": interrupt, "chat.permission": permission}.items():
        registry.register(ch, fn)
    return hub
