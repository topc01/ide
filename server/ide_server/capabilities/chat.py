from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.chat.events import Routed, TextDelta, Done, ChatError
from ide_server.mlx.server import MlxUnavailable

_LANG = "Responde siempre en español."

REGEX_AGENT_PROMPT = (
    "Eres un asistente experto en expresiones regulares. Tu tarea es ayudar al usuario a "
    "construir el regex que necesita para buscar en su código.\n"
    "- Usa SIEMPRE la sintaxis de regex de ripgrep (motor Rust `regex`), NO PCRE (sin "
    "lookbehind, sin backreferences).\n"
    "- Cuando propongas el regex final, escríbelo en un bloque de código marcado como "
    "```regex``` (una sola línea con el patrón), para que la app lo pueda extraer.\n"
    "- Explica brevemente qué hace el patrón. Puedes pedir aclaraciones y ofrecer variantes."
)


def _load_session_context(root: Path, session_id: str) -> dict:
    # Devuelve {cwd, system_prompt, role, model, is_coordinator} de la sesión.
    # Resuelve el rol real (preset de .ide/config.toml) para que permisos y
    # modelo se apliquen. `is_coordinator` marca sesiones sin worktree propio
    # (comandan hijas multi-repo) — lo usa el SessionHub para decidir si cablea
    # el servidor MCP de orquestación.
    from ide_server.sessions_store import load_sessions, find_node
    from ide_server.roles import resolve_role
    # Sesión efímera del asistente de regex: NO está en sessions.json. Corre en el
    # worktree de la sesión real (`airegex:<real>`) con un prompt especializado.
    if session_id.startswith("airegex:"):
        real = session_id[len("airegex:"):]
        node = find_node(load_sessions(root), real)
        cwd = (node or {}).get("worktreePath") or str(root)
        return {"cwd": cwd, "system_prompt": _LANG + "\n\n" + REGEX_AGENT_PROMPT,
                "role": None, "model": None, "is_coordinator": False}
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

        if force == "local":
            # forzar el modelo local, streameado token a token
            if mlx_router is None:
                await hub.emit(sid, ChatError(code="mlx_off",
                                              message="mlx no está configurado en este proyecto"))
                return {"sent": False}
            await hub.emit(sid, Routed(source="local"))

            async def _emit(chunk: str) -> None:
                await hub.emit(sid, TextDelta(text=chunk))

            try:
                await mlx_router.stream_local(text, _emit)
            except MlxUnavailable:
                await hub.emit(sid, ChatError(code="mlx_unavailable",
                                              message="modelo local no disponible, usando Claude"))
                await hub.emit(sid, Routed(source="claude"))
                await hub.send_human(sid, text)
                return {"sent": True, "route": "claude"}
            await hub.emit(sid, Done(session_id=sid, is_error=False))
            return {"sent": True, "route": "local"}

        # auto (force None) o forzar claude
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
