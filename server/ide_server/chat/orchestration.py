"""Server MCP `orq`: tools de orquestación para sesiones coordinadoras.

Cada tool delega en `SessionHub` (interfaz `list_children`, `ask`, `spawn`).
La lógica vive en funciones planas `_t_*` testables contra un hub fake, sin
depender del SDK. `build_orq_server` solo las envuelve con `@tool` /
`create_sdk_mcp_server`.
"""

from __future__ import annotations

import asyncio
import json

from claude_agent_sdk import create_sdk_mcp_server, tool


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _err(msg: str) -> dict:
    text = f"error: {msg}"
    # isError (camelCase) es lo que verifican nuestros tests/consumidores;
    # is_error (snake_case) es la clave que espera el wrapper del SDK real
    # (ver claude_agent_sdk: result.get("is_error", False)). Mandamos ambas
    # para que el error se propague sin fallos silenciosos en los dos casos.
    return {
        "content": [{"type": "text", "text": text}],
        "isError": True,
        "is_error": True,
    }


async def _t_list_children(hub, coord_id, args) -> dict:
    try:
        return _ok(json.dumps(hub.list_children(coord_id), ensure_ascii=False))
    except Exception as e:  # noqa: BLE001 - sin fallos silenciosos: el agente ve el error
        return _err(str(e))


async def _t_ask_session(hub, coord_id, args) -> dict:
    try:
        return _ok(await hub.ask(coord_id, args["session_id"], args["task"]))
    except Exception as e:  # noqa: BLE001
        return _err(str(e))


async def _t_ask_sessions(hub, coord_id, args) -> dict:
    try:
        reqs = args["requests"]
        # return_exceptions: una hija que falla no tumba el batch; se reporta
        # cuál falló (sin fallos silenciosos) y las demás igual devuelven su reply.
        results = await asyncio.gather(
            *[hub.ask(coord_id, r["session_id"], r["task"]) for r in reqs],
            return_exceptions=True,
        )
        out = []
        for r, res in zip(reqs, results):
            if isinstance(res, Exception):
                out.append({"session_id": r["session_id"], "error": str(res)})
            else:
                out.append({"session_id": r["session_id"], "reply": res})
        return _ok(json.dumps(out, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        return _err(str(e))


async def _t_spawn_session(hub, coord_id, args) -> dict:
    try:
        out = await hub.spawn(
            coord_id, args["repo"], args["name"], args.get("role"), args.get("branch")
        )
        return _ok(json.dumps(out, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        return _err(str(e))


def build_orq_server(hub, coordinator_id: str):
    """Arma el server MCP `orq` cableado a `hub` para la coordinadora `coordinator_id`."""

    @tool("list_children", "Lista las sesiones hijas de la coordinadora con su estado.", {})
    async def list_children(args):
        return await _t_list_children(hub, coordinator_id, args)

    @tool(
        "ask_session",
        "Le manda una tarea a una hija y ESPERA su respuesta final.",
        {"session_id": str, "task": str},
    )
    async def ask_session(args):
        return await _t_ask_session(hub, coordinator_id, args)

    @tool(
        "ask_sessions",
        "Fan-out: manda tareas a varias hijas en paralelo y espera todas.",
        {"requests": list},
    )
    async def ask_sessions(args):
        return await _t_ask_sessions(hub, coordinator_id, args)

    @tool(
        "spawn_session",
        "Crea una hija nueva (worktree+branch+rol) bajo la coordinadora.",
        # JSON Schema explícito (el SDK lo pasa tal cual si tiene type+properties):
        # role/branch son OPCIONALES; un dict plano de tipos los haría required y
        # el protocolo mcp rechazaría spawn_session(repo, name) sin ellos.
        {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "name": {"type": "string"},
                "role": {"type": "string"},
                "branch": {"type": "string"},
            },
            "required": ["repo", "name"],
        },
    )
    async def spawn_session(args):
        return await _t_spawn_session(hub, coordinator_id, args)

    return create_sdk_mcp_server(
        name="orq",
        tools=[list_children, ask_session, ask_sessions, spawn_session],
    )
