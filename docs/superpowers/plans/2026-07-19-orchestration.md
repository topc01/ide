# Orquestación entre sesiones (meta-agente Fase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) o superpowers:executing-plans para implementar tarea por tarea. Los steps usan
> checkbox (`- [ ]`).

**Goal:** Que una sesión coordinadora comande a sus hijas (request-reply bloqueante) y las cree,
vía tools MCP in-process, y que el intercambio se vea como mensajes en ambos chats.

**Architecture:** Un `SessionHub` (nuevo) es dueño del ciclo de vida de los drivers y de los
primitivos de orquestación (`ask`, `list_children`, `spawn`), con lock por sesión. La capability
`chat` pasa a delegar en el hub. A los drivers de sesiones **coordinadoras** (`worktreePath is
None`) se les monta un SDK MCP server `orq` con 4 tools que delegan al hub. Cada `ask` emite
eventos `RelayMessage` a los canales de chat de ambas sesiones.

**Tech Stack:** Python/FastAPI + `claude_agent_sdk` (`create_sdk_mcp_server`, `tool`,
`ClaudeAgentOptions.mcp_servers`); React + TS + vitest. Tests: `cd server && uv run pytest`,
`cd ui && npm test`.

## Global Constraints

- **Sin fallos silenciosos.** Errores de transporte → envelope; errores de una tool MCP → resultado
  de tool con `isError: True` (el agente lo ve); nunca se tragan.
- **Detección de coordinadora = `node.get("worktreePath") is None`** (el nodo NO guarda `kind`;
  las hijas de trabajo tienen `worktreePath`, la coordinadora no).
- **Hijas permisivas:** las sesiones arrancadas/comandadas por el hub para orquestación usan
  `permission_mode="bypassPermissions"`.
- **El refactor de `chat.py` debe mantener verdes los tests existentes** (`test_chat_capability.py`,
  `test_chat_driver*.py`): firma `chatmod.register(reg, root, manager, driver_factory=None)`,
  `_load_session_context` importable desde `chatmod`, handlers `chat.start/send/interrupt/permission`
  con el mismo comportamiento observable, y el `FakeDriver` de los tests (sin `mcp_servers`) sigue
  funcionando (no se le pasa `mcp_servers` a sesiones no-coordinadoras).
- **Commits atómicos, en español, conventional commits.** Un commit por tarea.

---

### Task 1: Evento `RelayMessage`

**Files:**
- Modify: `server/ide_server/chat/events.py`
- Test: `server/tests/test_chat_events.py`

**Interfaces:**
- Produces: `RelayMessage(direction: str, peer: str, peer_id: str, text: str)` dataclass;
  `to_payload` mapea a `{"kind":"relay","direction","peer","peerId","text"}`.

- [ ] **Step 1: Test que falla**

Agregar a `server/tests/test_chat_events.py`:

```python
def test_relay_message_payload():
    from ide_server.chat.events import RelayMessage, to_payload
    p = to_payload(RelayMessage(direction="out", peer="Hija A", peer_id="c2", text="compila"))
    assert p == {"kind": "relay", "direction": "out", "peer": "Hija A", "peerId": "c2", "text": "compila"}
```

- [ ] **Step 2: Correr, verificar que falla**

Run: `cd server && uv run pytest tests/test_chat_events.py::test_relay_message_payload -q`
Expected: FAIL (`ImportError: cannot import name 'RelayMessage'`).

- [ ] **Step 3: Implementar**

En `server/ide_server/chat/events.py`, agregar la dataclass (junto a las otras) y una rama en
`to_payload` (antes del `raise TypeError`):

```python
@dataclass
class RelayMessage:
    direction: str   # "in" | "out"
    peer: str        # nombre de la otra sesión
    peer_id: str
    text: str
```

```python
    if isinstance(event, RelayMessage):
        return {"kind": "relay", "direction": event.direction, "peer": event.peer,
                "peerId": event.peer_id, "text": event.text}
```

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd server && uv run pytest tests/test_chat_events.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/chat/events.py server/tests/test_chat_events.py
git commit -m "feat(chat): evento RelayMessage (mensaje relay entre sesiones)"
```

---

### Task 2: `ClaudeDriver` — `send` devuelve el texto y acepta `mcp_servers`

**Files:**
- Modify: `server/ide_server/chat/driver.py`
- Test: `server/tests/test_chat_driver.py`

**Interfaces:**
- Consumes: `TextDelta` (ya en events).
- Produces: `ClaudeDriver(..., mcp_servers: dict | None = None)`; `send(text) -> str` (texto
  asistente acumulado de esa respuesta, además de emitir eventos como hoy).

- [ ] **Step 1: Test que falla**

Mira el patrón de fake client de `test_chat_driver.py` y reutilízalo. Agregar:

```python
@pytest.mark.asyncio
async def test_send_returns_accumulated_assistant_text():
    # fake client que al recibir query emite dos AssistantMessage(TextBlock) + ResultMessage(Done)
    from ide_server.chat.driver import ClaudeDriver
    from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage

    class FakeClient:
        def __init__(self, options): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def query(self, prompt): self._prompt = prompt
        async def receive_response(self):
            yield AssistantMessage(content=[TextBlock(text="hola ")])
            yield AssistantMessage(content=[TextBlock(text="mundo")])
            yield ResultMessage(session_id="s", is_error=False, usage={})

    events = []
    d = ClaudeDriver(cwd=".", system_prompt="s", permission_mode="default",
                     allowed_tools=None, on_event=events.append, on_permission=None,
                     client_factory=FakeClient)
    await d.start()
    text = await d.send("go")
    assert text == "hola mundo"


def test_driver_passes_mcp_servers_to_options():
    from ide_server.chat.driver import ClaudeDriver
    captured = {}

    class FakeClient:
        def __init__(self, options): captured["options"] = options

    d = ClaudeDriver(cwd=".", system_prompt="s", permission_mode="default",
                     allowed_tools=["mcp__orq__ask_session"], on_event=lambda e: None,
                     on_permission=None, mcp_servers={"orq": object()}, client_factory=FakeClient)
    assert captured["options"].mcp_servers == d._mcp_servers_debug  # ver nota
```

> Nota al implementador: `ResultMessage`/`AssistantMessage`/`TextBlock` puede requerir kwargs
> distintos según la versión del SDK; ajusta la construcción del fake a la firma real (mira cómo
> los usa `translate.py`). Para el segundo test, en vez de `d._mcp_servers_debug`, aserta que
> `captured["options"].mcp_servers == {"orq": <el mismo object>}` guardando la referencia del
> `object()` en una variable local y comparando contra ella. Ajusta el assert a esa forma.

- [ ] **Step 2: Correr, verificar que falla**

Run: `cd server && uv run pytest tests/test_chat_driver.py -q`
Expected: FAIL (`send` retorna None / `mcp_servers` no es kwarg).

- [ ] **Step 3: Implementar**

En `server/ide_server/chat/driver.py`:
- Agregar `mcp_servers: dict | None = None` al `__init__` (después de `model`), y:

```python
        if mcp_servers is not None:
            opts["mcp_servers"] = mcp_servers
```

- Cambiar `send` para acumular y devolver el texto:

```python
    async def send(self, text: str) -> str:
        await self._client.query(prompt=text)
        parts: list[str] = []
        async for message in self._client.receive_response():
            for event in translate(message):
                if isinstance(event, TextDelta):
                    parts.append(event.text)
                if isinstance(event, Done):
                    self.session_id = event.session_id
                self._on_event(event)
        return "".join(parts)
```

Agregar `TextDelta` al import de `ide_server.chat.events` en el módulo.

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd server && uv run pytest tests/test_chat_driver.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/chat/driver.py server/tests/test_chat_driver.py
git commit -m "feat(chat): driver.send devuelve el texto asistente y acepta mcp_servers"
```

---

### Task 3: `SessionHub` + rewire de `capabilities/chat.py`

**Files:**
- Create: `server/ide_server/chat/session_hub.py`
- Modify: `server/ide_server/capabilities/chat.py`
- Test: `server/tests/test_session_hub.py` (nuevo)
- Preserve: `server/tests/test_chat_capability.py` (debe seguir verde sin cambios)

**Interfaces:**
- Produces: `SessionHub(root, manager, driver_factory)` con:
  - `async ensure_started(session_id, *, override=None) -> driver` — si ya está, lo devuelve; si
    no, carga contexto, resuelve permiso, construye el driver (con `mcp_servers` si la sesión es
    coordinadora — se cablea en Task 6, aquí el hook queda como `self._mcp_for(session_id)` que
    por ahora devuelve `None`), lo arranca, lo registra. `override` se pasa a `resolve_permission`.
  - `async send_human(session_id, text) -> None` — bajo lock, `driver.send(text)`.
  - `async interrupt(session_id) -> None`.
  - `resolve_permission_future(request_id, allow)` / `_await_permission(session_id, request_id)`.
  - `get(session_id)`, `has(session_id)`, `lock_for(session_id)`.
  - `async emit(session_id, event)` — `await manager.broadcast(f"chat.event.{session_id}", to_payload(event))`.
- `_load_session_context(root, session_id)` (queda en `chat.py`, importable) gana la clave
  `is_coordinator: bool` (= `node.get("worktreePath") is None`).

- [ ] **Step 1: Tests que fallan (hub lifecycle)**

Crear `server/tests/test_session_hub.py`:

```python
import asyncio
import pytest
from ide_server.chat.session_hub import SessionHub
from ide_server.chat.events import TextDelta


class FakeManager:
    def __init__(self): self.events = []
    async def broadcast(self, channel, payload): self.events.append((channel, payload))


class FakeDriver:
    def __init__(self, *, cwd, system_prompt, permission_mode, allowed_tools,
                 on_event, on_permission, resume=None, model=None, mcp_servers=None,
                 client_factory=None):
        self.permission_mode = permission_mode; self.mcp_servers = mcp_servers
        self.on_event = on_event; self.started = False; self.sent = []
    async def start(self): self.started = True
    async def send(self, text):
        self.sent.append(text); self.on_event(TextDelta(text="ok")); return "ok"
    async def interrupt(self): pass


def _hub(tmp_path, ctx=None):
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir(exist_ok=True)
    hub = SessionHub(tmp_path, FakeManager(), FakeDriver)
    if ctx is not None:
        hub._load_ctx = lambda sid: ctx   # inyección de contexto para el test
    return hub


@pytest.mark.asyncio
async def test_ensure_started_builds_and_registers(tmp_path):
    hub = _hub(tmp_path, ctx={"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                              "model": None, "is_coordinator": False})
    d = await hub.ensure_started("s1")
    assert d.started is True and hub.has("s1")
    # segunda vez no re-crea
    assert await hub.ensure_started("s1") is d


@pytest.mark.asyncio
async def test_send_human_broadcasts(tmp_path):
    hub = _hub(tmp_path, ctx={"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                              "model": None, "is_coordinator": False})
    await hub.ensure_started("s1")
    await hub.send_human("s1", "hola")
    assert ("chat.event.s1", {"kind": "text_delta", "text": "ok"}) in hub.manager.events


@pytest.mark.asyncio
async def test_override_skip_is_permissive(tmp_path):
    hub = _hub(tmp_path, ctx={"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                              "model": None, "is_coordinator": False})
    d = await hub.ensure_started("s1", override="skip")
    assert d.permission_mode == "bypassPermissions"
```

- [ ] **Step 2: Correr, verificar que falla**

Run: `cd server && uv run pytest tests/test_session_hub.py -q`
Expected: FAIL (`No module named 'ide_server.chat.session_hub'`).

- [ ] **Step 3: Implementar el hub**

Crear `server/ide_server/chat/session_hub.py`:

```python
from __future__ import annotations
import asyncio
import uuid
from pathlib import Path
from ide_server.chat.driver import ClaudeDriver
from ide_server.chat.permissions import resolve_permission
from ide_server.chat.events import to_payload, PermissionRequest
from ide_server.chat.translate import _tool_detail


class SessionHub:
    def __init__(self, root: Path, manager, driver_factory=None) -> None:
        self.root = root
        self.manager = manager
        self._factory = driver_factory or ClaudeDriver
        self._drivers: dict[str, object] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: dict[str, asyncio.Future] = {}

    # --- contexto (inyectable en tests) ---
    def _load_ctx(self, session_id: str) -> dict:
        from ide_server.capabilities.chat import _load_session_context
        return _load_session_context(self.root, session_id)

    def _mcp_for(self, session_id: str, is_coordinator: bool):
        return None   # cableado en Task 6 (build_orq_server para coordinadoras)

    # --- accesores ---
    def has(self, session_id: str) -> bool:
        return session_id in self._drivers

    def get(self, session_id: str):
        return self._drivers[session_id]

    def lock_for(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    async def emit(self, session_id: str, event: object) -> None:
        await self.manager.broadcast(f"chat.event.{session_id}", to_payload(event))

    # --- ciclo de vida ---
    async def ensure_started(self, session_id: str, *, override: str | None = None):
        if session_id in self._drivers:
            return self._drivers[session_id]
        ctx = self._load_ctx(session_id)
        mode, allowed = resolve_permission(ctx.get("role"), override)
        mcp = self._mcp_for(session_id, bool(ctx.get("is_coordinator")))
        if mcp is not None:
            allowed = list(allowed or []) + ["mcp__orq__list_children", "mcp__orq__ask_session",
                                             "mcp__orq__ask_sessions", "mcp__orq__spawn_session"]
        driver = self._factory(
            cwd=ctx["cwd"], system_prompt=ctx["system_prompt"], permission_mode=mode,
            allowed_tools=allowed, model=ctx.get("model"), mcp_servers=mcp,
            on_event=lambda e, s=session_id: asyncio.create_task(self.emit(s, e)),
            on_permission=(lambda req_id, s=session_id: self._await_permission(s, req_id))
            if mode != "bypassPermissions" else None,
        )
        await driver.start()
        self._drivers[session_id] = driver
        return driver

    async def send_human(self, session_id: str, text: str) -> None:
        async with self.lock_for(session_id):
            await self._drivers[session_id].send(text)

    async def interrupt(self, session_id: str) -> None:
        await self._drivers[session_id].interrupt()

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
```

> Nota: el `mcp_servers=mcp` se pasa siempre al factory; el `FakeDriver` de los tests del hub y de
> Task 6 acepta `mcp_servers`. El `FakeDriver` de `test_chat_capability.py` NO lo acepta — por eso
> ese test se rewirea en el Step 5 para usar el hub con un factory que sí lo acepta, O se mantiene
> el paso condicional (ver Step 5). Elige la opción que deje ese test verde con el mínimo cambio.

- [ ] **Step 4: Correr los tests del hub**

Run: `cd server && uv run pytest tests/test_session_hub.py -q` → PASS.

- [ ] **Step 5: Rewire `capabilities/chat.py` + preservar tests existentes**

Reescribir `server/ide_server/capabilities/chat.py` para delegar en el hub, manteniendo la firma
y el comportamiento observable. `_load_session_context` se queda en este módulo y gana
`is_coordinator`:

```python
def _load_session_context(root: Path, session_id: str) -> dict:
    from ide_server.sessions_store import load_sessions, find_node
    from ide_server.roles import resolve_role
    tree = load_sessions(root)
    node = find_node(tree, session_id)
    if node is None:
        raise KeyError(session_id)
    cwd = node.get("worktreePath") or str(root)
    r = resolve_role(root, node.get("role"))
    desc = node.get("description") or ""
    system_prompt = "\n\n".join([_LANG] + [p for p in [desc, r.system_prompt if r else None] if p]) or _LANG
    role = {"read_only": r.read_only} if r is not None else None
    model = r.model if r else None
    return {"cwd": cwd, "system_prompt": system_prompt, "role": role, "model": model,
            "is_coordinator": node.get("worktreePath") is None}
```

`register` crea (o recibe) el hub y define los handlers como wrappers:

```python
def register(registry: Registry, root: Path, manager, driver_factory=None, hub=None) -> None:
    from ide_server.chat.session_hub import SessionHub
    hub = hub or SessionHub(root, manager, driver_factory)

    async def start(payload: dict) -> dict:
        sid = payload["sessionId"]
        resumed = hub.has(sid)
        await hub.ensure_started(sid, override=payload.get("override"))
        return {"started": True, "resumed": resumed}

    async def send(payload: dict) -> dict:
        await hub.send_human(payload["sessionId"], payload["text"])
        return {"sent": True}

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
```

> El `on_event` del hub usa `asyncio.create_task(self.emit(...))` (dispara el broadcast). Los tests
> de `test_chat_capability.py` esperan que el broadcast ocurra tras `chat.send`: como el fake
> `send` del test llama `on_event` sincrónicamente y `emit` crea una task, agrega un `await
> asyncio.sleep(0)` NO — en cambio, esos tests ya existen y usan `driver_factory=FakeDriver` sin
> `mcp_servers`. PARA MANTENERLOS VERDES: (a) el `FakeDriver` de ese archivo no acepta
> `mcp_servers`; como esas sesiones no son coordinadoras, `mcp` es `None`, pero el hub igual pasa
> `mcp_servers=None` al factory → el `FakeDriver` lo rechazaría. Solución mínima: en el hub, armar
> un dict `opts` y hacer `if mcp is not None: opts["mcp_servers"] = mcp` (no pasar la clave cuando
> es None), y pasar `**opts` al factory. Así el `FakeDriver` viejo (sin `mcp_servers`) sigue
> andando. Ajusta `ensure_started` a esa forma (dict opts + `**opts`).
>
> Para el broadcast tras `chat.send`: el test asertaba el evento en `mgr.events` inmediatamente
> tras `await reg.dispatch("chat.send", ...)`. Con `emit` como task, haz que `send_human` haga
> `await self.emit(...)` de los eventos capturados NO — mejor: que el `on_event` del driver, en el
> hub, NO cree task sino que agende el broadcast y `send_human`/`ensure_started` lo flusheen. Para
> mantener el test simple y determinístico, implementa `on_event` así: acumula los eventos en una
> lista y `send_human`/`ensure_started` hacen `await` de los broadcasts pendientes al terminar
> (patrón `_flush_broadcasts` que ya existía en el chat original). Copia ese patrón del `git show`
> del `chat.py` original si hace falta. Lo importante: tras `chat.send`, el evento ya está en
> `mgr.events`.

- [ ] **Step 6: Wire en `app.py`**

En `server/ide_server/app.py`, `chat_cap.register(registry, root, manager)` puede seguir igual
(crea el hub internamente y lo devuelve). Guarda el hub devuelto para Task 6:
`hub = chat_cap.register(registry, root, manager)`.

- [ ] **Step 7: Correr TODO chat**

Run: `cd server && uv run pytest tests/test_chat_capability.py tests/test_session_hub.py tests/test_chat_driver.py -q` → PASS.
Luego suite completa: `cd server && uv run pytest -q` → PASS.

- [ ] **Step 8: Commit**

```bash
git add server/ide_server/chat/session_hub.py server/ide_server/capabilities/chat.py server/ide_server/app.py server/tests/test_session_hub.py
git commit -m "refactor(chat): SessionHub dueño del ciclo de vida de drivers; chat delega en él"
```

---

### Task 4: `SessionHub.ask` + `list_children`

**Files:**
- Modify: `server/ide_server/chat/session_hub.py`
- Test: `server/tests/test_session_hub.py`

**Interfaces:**
- Consumes: `ensure_started`, `lock_for`, `emit`, `RelayMessage`.
- Produces:
  - `async ask(from_id, to_id, text) -> str` — arranca la hija permisiva si no está, emite relay
    entrante (a la hija) y saliente (al coordinador), bajo lock de la hija llama `send`, emite el
    relay de respuesta (al coordinador) y devuelve el texto. Usa el nombre de las sesiones para
    el `peer` (helper `_name(session_id) -> str` leyendo el árbol).
  - `list_children(coordinator_id) -> list[dict]` — `[{sessionId, name, status, repoId}]`.

- [ ] **Step 1: Tests que fallan**

Agregar a `server/tests/test_session_hub.py`:

```python
@pytest.mark.asyncio
async def test_ask_returns_child_text_and_emits_relays(tmp_path):
    from ide_server.sessions_store import save_sessions
    save_sessions(tmp_path, [{"id": "coord", "name": "King",
                              "children": [{"id": "c1", "name": "Hija A", "worktreePath": str(tmp_path)}]}])
    hub = SessionHub(tmp_path, FakeManager(), FakeDriver)
    hub._load_ctx = lambda sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                                 "model": None, "is_coordinator": sid == "coord"}
    reply = await hub.ask("coord", "c1", "compila")
    assert reply == "ok"
    kinds = [(ch, p["kind"], p.get("direction"), p.get("text")) for ch, p in hub.manager.events if p["kind"] == "relay"]
    # entrante a la hija, saliente al coord, respuesta entrante al coord
    assert ("chat.event.c1", "relay", "in", "compila") in kinds
    assert ("chat.event.coord", "relay", "out", "compila") in kinds
    assert ("chat.event.coord", "relay", "in", "ok") in kinds


@pytest.mark.asyncio
async def test_ask_serializes_per_session(tmp_path):
    # dos ask concurrentes a la misma hija no se solapan (el driver registra orden)
    from ide_server.sessions_store import save_sessions
    save_sessions(tmp_path, [{"id": "coord", "name": "K",
                              "children": [{"id": "c1", "name": "A", "worktreePath": str(tmp_path)}]}])
    order = []

    class SlowDriver(FakeDriver):
        async def send(self, text):
            order.append(("start", text)); await asyncio.sleep(0.01)
            order.append(("end", text)); return text

    hub = SessionHub(tmp_path, FakeManager(), SlowDriver)
    hub._load_ctx = lambda sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                                 "model": None, "is_coordinator": sid == "coord"}
    await asyncio.gather(hub.ask("coord", "c1", "A"), hub.ask("coord", "c1", "B"))
    # sin solaparse: cada par start/end es contiguo
    assert order in ([("start","A"),("end","A"),("start","B"),("end","B")],
                     [("start","B"),("end","B"),("start","A"),("end","A")])


def test_list_children(tmp_path):
    from ide_server.sessions_store import save_sessions
    save_sessions(tmp_path, [{"id": "coord", "name": "K", "children": [
        {"id": "c1", "name": "A", "status": "idle", "repoId": "repo1", "worktreePath": "/x"},
        {"id": "c2", "name": "B", "status": "running", "repoId": "repo2", "worktreePath": "/y"}]}])
    hub = SessionHub(tmp_path, FakeManager(), FakeDriver)
    kids = hub.list_children("coord")
    assert kids == [{"sessionId": "c1", "name": "A", "status": "idle", "repoId": "repo1"},
                    {"sessionId": "c2", "name": "B", "status": "running", "repoId": "repo2"}]
    assert hub.list_children("desconocido") == []
```

- [ ] **Step 2: Correr, verificar que falla**

Run: `cd server && uv run pytest tests/test_session_hub.py -q` → FAIL (`ask`/`list_children` no existen).

- [ ] **Step 3: Implementar**

Agregar a `SessionHub`:

```python
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
        await self.emit(from_id, RelayMessage(direction="in", peer=to_name, peer_id=to_id, text=reply))
        return reply
```

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd server && uv run pytest tests/test_session_hub.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/chat/session_hub.py server/tests/test_session_hub.py
git commit -m "feat(chat): SessionHub.ask (request-reply + relays en ambos chats) y list_children"
```

---

### Task 5: `SessionHub.spawn`

**Files:**
- Modify: `server/ide_server/chat/session_hub.py`
- Test: `server/tests/test_session_hub.py`

**Interfaces:**
- Consumes: `sessions_store` (slugify/insert/save), `worktrees.add_worktree`, `roles.resolve_role`.
- Produces: `async spawn(coordinator_id, repo, name, role=None, branch=None) -> dict`
  (`{sessionId, name}`) — crea el nodo hija bajo el coordinador (worktree + branch + rol), lo
  persiste, lo arranca permisivo. Reusa la lógica de `sessions.create`.

- [ ] **Step 1: Test que falla**

```python
@pytest.mark.asyncio
async def test_spawn_creates_child_under_coordinator(tmp_path, monkeypatch):
    from ide_server.sessions_store import save_sessions, load_sessions, find_node
    (tmp_path / ".ide").mkdir(exist_ok=True)
    save_sessions(tmp_path, [{"id": "coord", "name": "K", "children": []}])
    # evitar git real: fake de add_worktree y discover_repos
    import ide_server.chat.session_hub as hubmod
    monkeypatch.setattr(hubmod, "add_worktree", lambda *a, **k: None)
    monkeypatch.setattr(hubmod, "repo_path", lambda root, repo_id: tmp_path)
    hub = SessionHub(tmp_path, FakeManager(), FakeDriver)
    hub._load_ctx = lambda sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                                 "model": None, "is_coordinator": False}
    out = await hub.spawn("coord", repo="repo1", name="Constructor")
    assert out["name"] == "Constructor" and "sessionId" in out
    node = find_node(load_sessions(tmp_path), out["sessionId"])
    assert node is not None and node["repoId"] == "repo1"
    coord = find_node(load_sessions(tmp_path), "coord")
    assert any(c["id"] == out["sessionId"] for c in coord["children"])
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL (`spawn` no existe).

- [ ] **Step 3: Implementar**

Imports arriba de `session_hub.py`:

```python
import uuid
from ide_server.sessions_store import load_sessions, save_sessions, slugify, insert_node
from ide_server.worktrees import add_worktree
from ide_server.workspace import discover_repos


def repo_path(root, repo_id):
    for repo in discover_repos(root):
        if repo["id"] == repo_id:
            return root / repo["id"]
    raise KeyError(repo_id)
```

Método:

```python
    async def spawn(self, coordinator_id: str, repo: str, name: str,
                    role: str | None = None, branch: str | None = None) -> dict:
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
```

- [ ] **Step 4: Correr, verificar que pasa** → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/chat/session_hub.py server/tests/test_session_hub.py
git commit -m "feat(chat): SessionHub.spawn (crea hija bajo la coordinadora y la arranca)"
```

---

### Task 6: MCP server `orq` + cableado en el hub

**Files:**
- Create: `server/ide_server/chat/orchestration.py`
- Modify: `server/ide_server/chat/session_hub.py` (`_mcp_for` devuelve el server para coordinadoras)
- Modify: `server/ide_server/app.py` (pasa el hub para que `_mcp_for` lo capture — ya lo tiene)
- Test: `server/tests/test_orchestration.py` (nuevo)

**Interfaces:**
- Produces:
  - Funciones puras testables: `async _t_list_children(hub, coord_id, args)`,
    `_t_ask_session(hub, coord_id, args)`, `_t_ask_sessions(hub, coord_id, args)`,
    `_t_spawn_session(hub, coord_id, args)` — cada una devuelve un dict de resultado MCP
    (`{"content":[{"type":"text","text": ...}]}`, o `isError` en error).
  - `build_orq_server(hub, coordinator_id)` — `create_sdk_mcp_server(name="orq", tools=[...])`.
- `SessionHub._mcp_for(session_id, is_coordinator)` → `build_orq_server(self, session_id)` si
  `is_coordinator` else `None`.

- [ ] **Step 1: Tests que fallan**

Crear `server/tests/test_orchestration.py`:

```python
import pytest
from ide_server.chat import orchestration as orq


class FakeHub:
    def __init__(self):
        self.asked = []
    def list_children(self, coord): return [{"sessionId": "c1", "name": "A", "status": "idle", "repoId": "r"}]
    async def ask(self, frm, to, text): self.asked.append((to, text)); return f"reply:{to}"
    async def spawn(self, coord, repo, name, role=None, branch=None): return {"sessionId": "new", "name": name}


@pytest.mark.asyncio
async def test_t_ask_session_delegates_and_returns_text():
    hub = FakeHub()
    res = await orq._t_ask_session(hub, "coord", {"session_id": "c1", "task": "haz X"})
    assert hub.asked == [("c1", "haz X")]
    assert res["content"][0]["text"] == "reply:c1"


@pytest.mark.asyncio
async def test_t_ask_sessions_fans_out():
    hub = FakeHub()
    res = await orq._t_ask_sessions(hub, "coord",
        {"requests": [{"session_id": "c1", "task": "X"}, {"session_id": "c2", "task": "Y"}]})
    assert set(hub.asked) == {("c1", "X"), ("c2", "Y")}
    assert "c1" in res["content"][0]["text"] and "c2" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_t_list_children():
    res = await orq._t_list_children(FakeHub(), "coord", {})
    assert "c1" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_t_spawn_session():
    res = await orq._t_spawn_session(FakeHub(), "coord", {"repo": "r", "name": "Bob"})
    assert "new" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_tool_error_becomes_iserror():
    class BadHub(FakeHub):
        async def ask(self, *a, **k): raise RuntimeError("boom")
    res = await orq._t_ask_session(BadHub(), "coord", {"session_id": "c1", "task": "X"})
    assert res.get("isError") is True and "boom" in res["content"][0]["text"]


def test_build_orq_server_exposes_four_tools():
    hub = FakeHub()
    server = orq.build_orq_server(hub, "coord")
    assert server is not None
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL (`No module named ...orchestration`).

- [ ] **Step 3: Implementar**

Crear `server/ide_server/chat/orchestration.py`:

```python
from __future__ import annotations
import asyncio
import json
from claude_agent_sdk import create_sdk_mcp_server, tool


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _err(msg: str) -> dict:
    return {"content": [{"type": "text", "text": f"error: {msg}"}], "isError": True}


async def _t_list_children(hub, coord_id, args) -> dict:
    try:
        return _ok(json.dumps(hub.list_children(coord_id), ensure_ascii=False))
    except Exception as e:                                  # noqa: BLE001
        return _err(str(e))


async def _t_ask_session(hub, coord_id, args) -> dict:
    try:
        return _ok(await hub.ask(coord_id, args["session_id"], args["task"]))
    except Exception as e:                                  # noqa: BLE001
        return _err(str(e))


async def _t_ask_sessions(hub, coord_id, args) -> dict:
    try:
        reqs = args["requests"]
        replies = await asyncio.gather(*[hub.ask(coord_id, r["session_id"], r["task"]) for r in reqs])
        out = [{"session_id": r["session_id"], "reply": rep} for r, rep in zip(reqs, replies)]
        return _ok(json.dumps(out, ensure_ascii=False))
    except Exception as e:                                  # noqa: BLE001
        return _err(str(e))


async def _t_spawn_session(hub, coord_id, args) -> dict:
    try:
        out = await hub.spawn(coord_id, args["repo"], args["name"],
                              args.get("role"), args.get("branch"))
        return _ok(json.dumps(out, ensure_ascii=False))
    except Exception as e:                                  # noqa: BLE001
        return _err(str(e))


def build_orq_server(hub, coordinator_id: str):
    @tool("list_children", "Lista las sesiones hijas de la coordinadora con su estado.", {})
    async def list_children(args): return await _t_list_children(hub, coordinator_id, args)

    @tool("ask_session", "Le manda una tarea a una hija y ESPERA su respuesta final.",
          {"session_id": str, "task": str})
    async def ask_session(args): return await _t_ask_session(hub, coordinator_id, args)

    @tool("ask_sessions", "Fan-out: manda tareas a varias hijas en paralelo y espera todas.",
          {"requests": list})
    async def ask_sessions(args): return await _t_ask_sessions(hub, coordinator_id, args)

    @tool("spawn_session", "Crea una hija nueva (worktree+branch+rol) bajo la coordinadora.",
          {"repo": str, "name": str, "role": str, "branch": str})
    async def spawn_session(args): return await _t_spawn_session(hub, coordinator_id, args)

    return create_sdk_mcp_server(name="orq",
        tools=[list_children, ask_session, ask_sessions, spawn_session])
```

> Nota: la firma exacta de `tool(...)` y `create_sdk_mcp_server(...)` puede variar según la versión
> del SDK (el schema puede pedir tipos como `{"type":"string"}` en vez de `str`). Verifica con
> `uv run python -c "from claude_agent_sdk import tool, create_sdk_mcp_server; help(tool)"` y ajusta
> la construcción para que `build_orq_server` devuelva un server válido. Los tests de las funciones
> `_t_*` no dependen del SDK; solo `test_build_orq_server_exposes_four_tools` lo toca (manténlo en
> un assert robusto: `server is not None`).

En `session_hub.py`, cambiar `_mcp_for`:

```python
    def _mcp_for(self, session_id: str, is_coordinator: bool):
        if not is_coordinator:
            return None
        from ide_server.chat.orchestration import build_orq_server
        return build_orq_server(self, session_id)
```

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd server && uv run pytest tests/test_orchestration.py -q` → PASS.
Suite completa: `cd server && uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/chat/orchestration.py server/ide_server/chat/session_hub.py server/tests/test_orchestration.py
git commit -m "feat(chat): MCP server orq (list_children/ask_session/ask_sessions/spawn_session)"
```

---

### Task 7: Frontend — render de `RelayMessage` en el chat

**Files:**
- Modify: `ui/src/state/chat.ts`
- Modify: `ui/src/main/ChatView.tsx`
- Test: `ui/src/state/chat.test.ts`, `ui/src/main/ChatView.test.tsx`

**Interfaces:**
- `Msg` gana `relay?: { direction: "in" | "out"; peer: string }`.
- `applyEvent` maneja `kind: "relay"`.

- [ ] **Step 1: Tests que fallan**

En `ui/src/state/chat.test.ts` agregar:

```ts
it("un evento relay agrega un mensaje con badge sin romper el streaming", () => {
  const { applyEvent } = useChat.getState();
  applyEvent("s1", { kind: "relay", direction: "out", peer: "Hija A", peerId: "c1", text: "compila" });
  const c = useChat.getState().convos["s1"];
  const m = c.messages[c.messages.length - 1];
  expect(m.text).toBe("compila");
  expect(m.relay).toEqual({ direction: "out", peer: "Hija A" });
});
```

En `ui/src/main/ChatView.test.tsx` agregar un test que renderice un `Msg` con `relay` y asere que
aparece el badge (p.ej. el nombre del peer y la flecha). Sigue el patrón de render existente del
archivo (mira cómo monta `ChatView` con un convo del store).

- [ ] **Step 2: Correr, verificar que falla**

Run: `cd ui && npm test -- chat` → FAIL.

- [ ] **Step 3: Implementar**

En `ui/src/state/chat.ts`:
- Extender `Msg`: `export interface Msg { role: "user" | "agent"; text: string; chips: Chip[]; tokens?: number; relay?: { direction: "in" | "out"; peer: string } }`.
- En `applyEvent`, agregar rama:

```ts
    else if (e.kind === "relay") {
      c.messages = [...c.messages, { role: "user", text: e.text, chips: [], relay: { direction: e.direction, peer: e.peer } }];
    }
```

En `ui/src/main/ChatView.tsx`: al renderizar cada `Msg`, si `m.relay`, mostrar un badge antes/junto
al texto: `→ {peer}` si `direction === "out"`, `← {peer}` si `"in"`, con clase de color ámbar
(reutiliza el token de accent existente, p.ej. `text-[#e0863f]`). Sigue el markup de burbuja que ya
usa el componente.

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd ui && npm test -- chat` → PASS. Suite completa: `cd ui && npm test` → PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/state/chat.ts ui/src/main/ChatView.tsx ui/src/state/chat.test.ts ui/src/main/ChatView.test.tsx
git commit -m "feat(chat): render de mensajes relay (badge de sesión cruzada) en el chat"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** `list_children` (T4/T6), `ask_session` (T4/T6), `ask_sessions` (T6),
  `spawn_session` (T5/T6), RelayMessage evento (T1) + emisión ambos canales (T4) + render (T7),
  MCP server solo en coordinadoras (T3 `_mcp_for` hook + T6), hijas permisivas (T3 override skip +
  T4 ask usa `override="skip"`), lock por sesión (T3/T4), driver.send devuelve texto (T2). ✓
- **Consistencia de tipos:** `ask(from_id,to_id,text)->str`, `list_children(coord)->[{sessionId,
  name,status,repoId}]`, `spawn(...)->{sessionId,name}`, RelayMessage `{direction,peer,peer_id,
  text}` ↔ payload `{kind:"relay",direction,peer,peerId,text}` ↔ front `relay:{direction,peer}`.
  Consistente entre T1/T4/T6/T7. ✓
- **Riesgo señalado:** las firmas exactas del SDK (`tool`, `create_sdk_mcp_server`,
  `AssistantMessage`/`ResultMessage`) se verifican en T2 y T6 con notas al implementador; los tests
  de lógica no dependen del SDK. El E2E real (coordinador Claude Code manejando las tools) no es
  testeable con fakes — verificación por unidad/integración, E2E queda para prueba en vivo.
- **Punto de corte:** si la rebanada se agranda, Task 5 (spawn) es cortable → Fase 2, dejando el
  loop de orquestación (list + ask) funcionando.
```
