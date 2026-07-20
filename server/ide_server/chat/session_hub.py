from __future__ import annotations
import asyncio
import uuid
from pathlib import Path
from ide_server.chat.driver import ClaudeDriver
from ide_server.chat.permissions import resolve_permission
from ide_server.chat.events import to_payload
from ide_server.sessions_store import load_sessions, save_sessions, slugify, insert_node
from ide_server.worktrees import add_worktree
from ide_server.workspace import discover_repos


def repo_path(root: Path, repo_id: str) -> Path:
    for repo in discover_repos(root):
        if repo["id"] == repo_id:
            return root / repo["id"]
    raise KeyError(repo_id)


class SessionHub:
    """Dueño del ciclo de vida de los drivers de chat (uno por sesión).

    `capabilities/chat.py` delega acá el arranque, el envío de mensajes humanos,
    la interrupción y la resolución de permisos. Se mantiene desacoplado del
    transporte (Registry/WS): solo conoce `manager.broadcast` para emitir eventos.
    """

    def __init__(self, root: Path, manager, driver_factory=None) -> None:
        self.root = root
        self.manager = manager
        self._factory = driver_factory or ClaudeDriver
        self._drivers: dict[str, object] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: dict[str, asyncio.Future] = {}
        # Los `on_event` de los drivers son síncronos; acumulamos las tareas de
        # broadcast acá y las flusheamos (await) al final de cada operación
        # pública para que el efecto sea determinístico ante quien llama.
        self._broadcast_tasks: list[asyncio.Task] = []

    # --- contexto (inyectable en tests) ---
    def _load_ctx(self, session_id: str) -> dict:
        from ide_server.capabilities.chat import _load_session_context
        return _load_session_context(self.root, session_id)

    def _mcp_for(self, session_id: str, is_coordinator: bool):
        return None  # cableado en Task 6 (build_orq_server para coordinadoras)

    # --- accesores ---
    def has(self, session_id: str) -> bool:
        return session_id in self._drivers

    def get(self, session_id: str):
        return self._drivers[session_id]

    def lock_for(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    async def emit(self, session_id: str, event: object) -> None:
        await self.manager.broadcast(f"chat.event.{session_id}", to_payload(event))

    def _make_on_event(self, session_id: str):
        def on_event(event: object) -> None:
            self._broadcast_tasks.append(asyncio.create_task(self.emit(session_id, event)))
        return on_event

    async def _flush_broadcasts(self) -> None:
        if not self._broadcast_tasks:
            return
        tasks, self._broadcast_tasks[:] = list(self._broadcast_tasks), []
        # return_exceptions: un socket muerto en un broadcast (posiblemente de otra
        # sesión, ya que la lista es compartida) no debe tumbar la respuesta de este
        # handler. La caída de conexión la maneja la capa WS ("desconectado" + resume).
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- ciclo de vida ---
    async def ensure_started(self, session_id: str, *, override: str | None = None):
        if session_id in self._drivers:
            return self._drivers[session_id]
        # Double-checked locking: dos corutinas concurrentes para la misma sesión
        # (fan-out del coordinador vía ask_sessions, o el humano abriendo el chat
        # de una hija mientras el coordinador la comanda) podrían pasar el `if`
        # de arriba a la vez. El lock por sesión serializa la creación; el
        # re-check adentro evita construir/arrancar un segundo driver huérfano.
        async with self.lock_for(session_id):
            if session_id in self._drivers:
                return self._drivers[session_id]
            ctx = self._load_ctx(session_id)
            mode, allowed = resolve_permission(ctx.get("role"), override)
            mcp = self._mcp_for(session_id, bool(ctx.get("is_coordinator")))
            if mcp is not None:
                allowed = list(allowed or []) + [
                    "mcp__orq__list_children", "mcp__orq__ask_session",
                    "mcp__orq__ask_sessions", "mcp__orq__spawn_session",
                ]
            opts: dict = dict(
                cwd=ctx["cwd"], system_prompt=ctx["system_prompt"], permission_mode=mode,
                allowed_tools=allowed, model=ctx.get("model"),
                on_event=self._make_on_event(session_id),
                on_permission=(lambda req_id, s=session_id: self._await_permission(s, req_id))
                if mode != "bypassPermissions" else None,
            )
            # Solo pasamos mcp_servers cuando hay algo que pasar: los drivers/fakes que
            # no conocen ese kwarg (sesiones no coordinadoras, tests preexistentes)
            # siguen funcionando sin cambios.
            if mcp is not None:
                opts["mcp_servers"] = mcp
            driver = self._factory(**opts)
            await driver.start()
            self._drivers[session_id] = driver
            await self._flush_broadcasts()
            return driver

    async def send_human(self, session_id: str, text: str) -> None:
        async with self.lock_for(session_id):
            await self._drivers[session_id].send(text)
            await self._flush_broadcasts()

    async def interrupt(self, session_id: str) -> None:
        await self._drivers[session_id].interrupt()
        await self._flush_broadcasts()

    async def _await_permission(self, session_id: str, request_id: str) -> bool:
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending[request_id] = fut
        try:
            return await fut
        finally:
            self._pending.pop(request_id, None)

    def resolve_permission_future(self, request_id: str, allow: bool) -> None:
        fut = self._pending.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(bool(allow))

    # --- orquestación entre sesiones ---
    def _node(self, session_id: str):
        from ide_server.sessions_store import load_sessions, find_node
        return find_node(load_sessions(self.root), session_id)

    def _name(self, session_id: str) -> str:
        node = self._node(session_id)
        return (node or {}).get("name", session_id)

    def list_children(self, coordinator_id: str) -> list[dict]:
        node = self._node(coordinator_id)
        if node is None:
            return []
        return [{"sessionId": c["id"], "name": c.get("name", c["id"]),
                 "status": c.get("status"), "repoId": c.get("repoId")}
                for c in node.get("children", [])]

    async def ask(self, from_id: str, to_id: str, text: str) -> str:
        from ide_server.chat.events import RelayMessage
        await self.ensure_started(to_id, override="skip")   # hija permisiva
        from_name, to_name = self._name(from_id), self._name(to_id)
        await self.emit(to_id, RelayMessage(direction="in", peer=from_name, peer_id=from_id, text=text))
        await self.emit(from_id, RelayMessage(direction="out", peer=to_name, peer_id=to_id, text=text))
        async with self.lock_for(to_id):
            reply = await self._drivers[to_id].send(text)
        # `send` dispara `on_event` de la hija (TextDelta/ToolUse/etc.) de forma
        # síncrona; esos broadcasts se encolan en `_broadcast_tasks` (ver
        # `_make_on_event`) y hay que flushearlos acá para cumplir el invariante
        # del hub: al retornar, ningún broadcast queda pendiente como task huérfana.
        await self._flush_broadcasts()
        await self.emit(from_id, RelayMessage(direction="in", peer=to_name, peer_id=to_id, text=reply))
        return reply

    async def spawn(self, coordinator_id: str, repo: str, name: str,
                    role: str | None = None, branch: str | None = None) -> dict:
        """Crea una sesión hija (worktree + branch + rol) bajo `coordinator_id`,
        la persiste en el árbol y la arranca permisiva (`override="skip"`).
        Reusa la misma forma de nodo que `capabilities/sessions.py::create`
        (kind="work") para no divergir del resto del sistema."""
        slug = slugify(name)
        node = {"id": str(uuid.uuid4()), "name": name, "slug": slug, "description": None,
                "role": role, "status": "idle", "repoId": repo, "access": "rw",
                "branch": branch or slug, "worktreePath": None,
                "expanded": True, "terminals": [], "children": []}
        wt = self.root / ".ide" / "worktrees" / slug
        add_worktree(repo_path(self.root, repo), wt, node["branch"], access="rw")
        node["worktreePath"] = str(wt)
        tree = load_sessions(self.root)
        insert_node(tree, coordinator_id, node)
        save_sessions(self.root, tree)
        await self.ensure_started(node["id"], override="skip")
        return {"sessionId": node["id"], "name": name}
