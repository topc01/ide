# Modelos locales (mlx) + routing Fase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps
> usan checkbox (`- [ ]`).

**Goal:** Un modelo mlx local tría los mensajes del chat — responde los simples y rutea los de
código a Claude Code. Opt-in por-proyecto; router pluggable prompt-based; degrada a Claude con aviso.

**Architecture:** Paquete `mlx/` (config, client OpenAI, server lifecycle, router pluggable) +
un `MlxRouter` orquestador atado en `app.py`, inyectado en la capability `chat`. `chat.send` (path
humano) consulta el router: local → responde y emite eventos (sin tocar Claude); claude → flujo
actual. Evento `Routed` + badge en el front.

**Tech Stack:** Python/FastAPI (+ httpx runtime, `mlx-lm` extra opcional), React/TS/vitest.

## Global Constraints

- **Sin fallos silenciosos:** mlx no disponible → degrada a Claude **con aviso visible** (evento
  `ChatError`), nunca rompe el chat.
- **mlx off = comportamiento actual intacto:** si `mlx_router` es `None` (no configurado), `chat.send`
  hace exactamente `hub.send_human` como hoy; los tests de `test_chat_capability.py` siguen verdes.
- **Config por-proyecto:** `.ide/config.toml [mlx]` del workspace (no global). `enabled` es el switch.
- **`mlx-lm` no se importa** en el proceso FastAPI (se spawnea como subproceso); es extra opcional
  solo-Mac (no rompe instalaciones no-Mac).
- **Triage solo en `chat.send`** (humano), nunca en `hub.ask` (orquestación).
- **Commits atómicos, en español.** Un commit por tarea.

---

### Task 1: `mlx/config.py`

**Files:**
- Create: `server/ide_server/mlx/__init__.py` (vacío), `server/ide_server/mlx/config.py`
- Test: `server/tests/test_mlx_config.py`

**Interfaces:**
- Produces: `MlxConfig` (dataclass `{model:str, router_prompt:str, port:int|None}`),
  `DEFAULT_ROUTER_PROMPT` (str), `mlx_config(root: Path) -> MlxConfig | None`.

- [ ] **Step 1: Test que falla**

Crear `server/tests/test_mlx_config.py`:

```python
from ide_server.mlx.config import mlx_config, DEFAULT_ROUTER_PROMPT


def _write(root, body):
    (root / ".ide").mkdir(parents=True, exist_ok=True)
    (root / ".ide" / "config.toml").write_text(body)


def test_none_when_no_section(tmp_path):
    _write(tmp_path, 'name = "x"\n')
    assert mlx_config(tmp_path) is None


def test_none_when_disabled(tmp_path):
    _write(tmp_path, '[mlx]\nenabled = false\nmodel = "m"\n')
    assert mlx_config(tmp_path) is None


def test_enabled_uses_default_prompt(tmp_path):
    _write(tmp_path, '[mlx]\nenabled = true\nmodel = "mlx-community/Q"\n')
    cfg = mlx_config(tmp_path)
    assert cfg.model == "mlx-community/Q"
    assert cfg.router_prompt == DEFAULT_ROUTER_PROMPT
    assert cfg.port is None


def test_custom_prompt_and_port(tmp_path):
    _write(tmp_path, '[mlx]\nenabled = true\nmodel = "m"\nrouter_prompt = "PROMPT"\nport = 9001\n')
    cfg = mlx_config(tmp_path)
    assert cfg.router_prompt == "PROMPT" and cfg.port == 9001


def test_none_when_no_config_file(tmp_path):
    assert mlx_config(tmp_path) is None
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL (`No module named ...mlx`).

- [ ] **Step 3: Implementar**

Crear `server/ide_server/mlx/__init__.py` (vacío) y `server/ide_server/mlx/config.py`:

```python
from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROUTER_PROMPT = (
    "Eres un router de tareas. Si el mensaje del usuario es una pregunta simple, conceptual o de "
    "conversación que puedes responder con confianza sin leer ni editar código, sin correr comandos "
    "y sin trabajar con el proyecto, RESPÓNDELA directamente. Si en cambio requiere leer/editar "
    "código, correr comandos, o trabajar con los archivos del proyecto, responde EXACTAMENTE con "
    "esta única palabra y nada más: ROUTE_TO_CLAUDE"
)


@dataclass
class MlxConfig:
    model: str
    router_prompt: str
    port: int | None


def mlx_config(root: Path) -> MlxConfig | None:
    path = root / ".ide" / "config.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    mlx = data.get("mlx")
    if not isinstance(mlx, dict) or not mlx.get("enabled") or not mlx.get("model"):
        return None
    return MlxConfig(
        model=str(mlx["model"]),
        router_prompt=str(mlx.get("router_prompt") or DEFAULT_ROUTER_PROMPT),
        port=int(mlx["port"]) if mlx.get("port") is not None else None,
    )
```

- [ ] **Step 4: Correr, verificar que pasa** → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/mlx/__init__.py server/ide_server/mlx/config.py server/tests/test_mlx_config.py
git commit -m "feat(mlx): config por-proyecto [mlx] (switch + model + router_prompt)"
```

---

### Task 2: `mlx/router.py` — router pluggable prompt-based

**Files:**
- Create: `server/ide_server/mlx/router.py`
- Test: `server/tests/test_mlx_router.py`

**Interfaces:**
- Consumes: un client con `async chat(messages) -> str` (interfaz de `MlxClient`, Task 3; en los
  tests se usa un fake).
- Produces: `RouteDecision` (dataclass `{route:str, reply:str|None, degraded:bool=False}`),
  `parse_route(text) -> tuple[str, str|None]`, `class PromptRouter`.

- [ ] **Step 1: Tests que fallan**

Crear `server/tests/test_mlx_router.py`:

```python
import pytest
from ide_server.mlx.router import parse_route, PromptRouter, RouteDecision


def test_parse_route_sentinel():
    assert parse_route("ROUTE_TO_CLAUDE") == ("claude", None)
    assert parse_route("  ROUTE_TO_CLAUDE  \n") == ("claude", None)


def test_parse_route_local():
    assert parse_route("La capital de Francia es París.") == ("local", "La capital de Francia es París.")


class _FakeClient:
    def __init__(self, reply): self._reply = reply; self.messages = None
    async def chat(self, messages): self.messages = messages; return self._reply


@pytest.mark.asyncio
async def test_prompt_router_local():
    c = _FakeClient("2 + 2 = 4")
    d = await PromptRouter(c, "SYS").route("cuánto es 2+2")
    assert d == RouteDecision(route="local", reply="2 + 2 = 4")
    assert c.messages == [{"role": "system", "content": "SYS"},
                          {"role": "user", "content": "cuánto es 2+2"}]


@pytest.mark.asyncio
async def test_prompt_router_claude():
    d = await PromptRouter(_FakeClient("ROUTE_TO_CLAUDE"), "SYS").route("edita el archivo main.py")
    assert d == RouteDecision(route="claude", reply=None)
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL.

- [ ] **Step 3: Implementar**

Crear `server/ide_server/mlx/router.py`:

```python
from __future__ import annotations
from dataclasses import dataclass

_SENTINEL = "ROUTE_TO_CLAUDE"


@dataclass
class RouteDecision:
    route: str            # "local" | "claude"
    reply: str | None
    degraded: bool = False


def parse_route(text: str) -> tuple[str, str | None]:
    stripped = (text or "").strip()
    if stripped == _SENTINEL or stripped.split()[-1:] == [_SENTINEL] and len(stripped.split()) == 1:
        return ("claude", None)
    if stripped == _SENTINEL:
        return ("claude", None)
    return ("local", text)


class PromptRouter:
    def __init__(self, client, router_prompt: str) -> None:
        self._client = client
        self._prompt = router_prompt

    async def route(self, text: str) -> RouteDecision:
        reply = await self._client.chat([
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": text},
        ])
        route, local_reply = parse_route(reply)
        return RouteDecision(route=route, reply=local_reply)
```

> Nota: simplifica `parse_route` — el sentinela debe matchear cuando la respuesta stripeada **es
> exactamente** `ROUTE_TO_CLAUDE`. Implementación mínima:
> `return ("claude", None) if (text or "").strip() == _SENTINEL else ("local", text)`. Ajusta el
> cuerpo a esa forma (el ejemplo de arriba quedó redundante); los tests deben pasar igual.

- [ ] **Step 4: Correr, verificar que pasa** → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/mlx/router.py server/tests/test_mlx_router.py
git commit -m "feat(mlx): PromptRouter + parse_route (sentinela ROUTE_TO_CLAUDE)"
```

---

### Task 3: `mlx/client.py` + `mlx/server.py` + deps

**Files:**
- Create: `server/ide_server/mlx/client.py`, `server/ide_server/mlx/server.py`
- Modify: `server/pyproject.toml` (httpx runtime + extra `mlx`)
- Test: `server/tests/test_mlx_client.py`, `server/tests/test_mlx_server.py`

**Interfaces:**
- Consumes: `find_free_port` de `ide_server.cli`.
- Produces: `MlxClient(base_url, *, http_post=None)` con `async chat(messages) -> str`;
  `MlxServer(model, *, spawn=None, http_get=None, find_port=None)` con `async ensure_running() -> str`
  y `stop()`; excepción `MlxUnavailable`.

- [ ] **Step 1: Tests que fallan**

Crear `server/tests/test_mlx_client.py`:

```python
import pytest
from ide_server.mlx.client import MlxClient


@pytest.mark.asyncio
async def test_chat_posts_openai_and_parses():
    captured = {}
    async def fake_post(url, json):
        captured["url"] = url; captured["json"] = json
        return {"choices": [{"message": {"content": "hola"}}]}
    c = MlxClient("http://localhost:9001", http_post=fake_post)
    out = await c.chat([{"role": "user", "content": "hi"}])
    assert out == "hola"
    assert captured["url"] == "http://localhost:9001/v1/chat/completions"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]
```

Crear `server/tests/test_mlx_server.py`:

```python
import pytest
from ide_server.mlx.server import MlxServer, MlxUnavailable


class _FakeProc:
    def __init__(self): self._alive = True
    def poll(self): return None if self._alive else 0
    def terminate(self): self._alive = False
    def wait(self, timeout=None): self._alive = False


@pytest.mark.asyncio
async def test_ensure_running_spawns_and_waits_health():
    calls = {}
    def fake_spawn(cmd): calls["cmd"] = cmd; return _FakeProc()
    health = iter([False, True])                       # 2do poll: listo
    async def fake_get(url): calls["health_url"] = url; return next(health)
    srv = MlxServer("mlx-community/Q", spawn=fake_spawn,
                    http_get=fake_get, find_port=lambda h, s: 9001)
    url = await srv.ensure_running()
    assert url == "http://127.0.0.1:9001"
    assert "mlx_lm.server" in " ".join(calls["cmd"]) and "mlx-community/Q" in calls["cmd"]
    assert "9001" in calls["cmd"]
    # segunda vez no re-spawnea
    assert await srv.ensure_running() == url


@pytest.mark.asyncio
async def test_ensure_running_spawn_fails_raises_unavailable():
    def bad_spawn(cmd): raise FileNotFoundError("no mlx_lm")
    srv = MlxServer("m", spawn=bad_spawn, http_get=None, find_port=lambda h, s: 9001)
    with pytest.raises(MlxUnavailable):
        await srv.ensure_running()
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

Crear `server/ide_server/mlx/client.py`:

```python
from __future__ import annotations
import sys


async def _httpx_post(url: str, json: dict) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=120.0) as cl:
        r = await cl.post(url, json=json)
        r.raise_for_status()
        return r.json()


class MlxClient:
    def __init__(self, base_url: str, *, http_post=None) -> None:
        self._base = base_url.rstrip("/")
        self._post = http_post or _httpx_post

    async def chat(self, messages: list[dict]) -> str:
        data = await self._post(f"{self._base}/v1/chat/completions",
                                {"model": "local", "messages": messages})
        return data["choices"][0]["message"]["content"]
```

Crear `server/ide_server/mlx/server.py`:

```python
from __future__ import annotations
import asyncio
import subprocess
import sys


class MlxUnavailable(RuntimeError):
    pass


async def _httpx_get_ok(url: str) -> bool:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as cl:
            return (await cl.get(url)).status_code == 200
    except Exception:                                  # noqa: BLE001
        return False


def _spawn(cmd: list[str]):
    return subprocess.Popen(cmd)


class MlxServer:
    def __init__(self, model: str, *, spawn=None, http_get=None, find_port=None,
                 host: str = "127.0.0.1", tries: int = 60, sleep=asyncio.sleep) -> None:
        self._model = model
        self._spawn = spawn or _spawn
        self._get = http_get or _httpx_get_ok
        self._host = host
        self._tries = tries
        self._sleep = sleep
        if find_port is None:
            from ide_server.cli import find_free_port
            find_port = find_free_port
        self._find_port = find_port
        self._proc = None
        self._url: str | None = None

    async def ensure_running(self) -> str:
        if self._proc is not None and self._proc.poll() is None and self._url:
            return self._url
        port = self._find_port(self._host, 9000)
        cmd = [sys.executable, "-m", "mlx_lm.server", "--model", self._model,
               "--port", str(port), "--host", self._host]
        try:
            self._proc = self._spawn(cmd)
        except (FileNotFoundError, OSError) as e:
            raise MlxUnavailable(f"no se pudo lanzar mlx_lm.server (¿instalaste ide-server[mlx]?): {e}")
        url = f"http://{self._host}:{port}"
        for _ in range(self._tries):
            if await self._get(f"{url}/v1/models"):
                self._url = url
                return url
            await self._sleep(1.0)
        self.stop()
        raise MlxUnavailable("el modelo local no cargó a tiempo")

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except Exception:                          # noqa: BLE001
                pass
        self._proc = None
        self._url = None
```

En `server/pyproject.toml`: mover/declarar `httpx>=0.27` en `dependencies` (runtime) y agregar el
extra opcional:

```toml
[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27", "pytest-asyncio>=0.23"]
mlx = ["mlx-lm>=0.19"]
```
(y agregar `"httpx>=0.27",` a la lista `dependencies`.)

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd server && uv run pytest tests/test_mlx_client.py tests/test_mlx_server.py -q` → PASS.
`cd server && uv sync --extra dev` (por el cambio de deps) y suite completa → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/mlx/client.py server/ide_server/mlx/server.py server/pyproject.toml server/tests/test_mlx_client.py server/tests/test_mlx_server.py
git commit -m "feat(mlx): MlxClient (OpenAI) + MlxServer (spawn mlx_lm.server + health) + deps"
```

---

### Task 4: `MlxRouter` (orquestador + degradación) + wire `app.py`

**Files:**
- Create: `server/ide_server/mlx/orchestrator.py`
- Modify: `server/ide_server/app.py`
- Test: `server/tests/test_mlx_orchestrator.py`

**Interfaces:**
- Consumes: `mlx_config` (T1), `PromptRouter`/`RouteDecision` (T2), `MlxClient`/`MlxServer`/
  `MlxUnavailable` (T3).
- Produces: `build_mlx_router(root) -> MlxRouter | None` (`None` si mlx off); `MlxRouter` con
  `async decide(text) -> RouteDecision | None`.

- [ ] **Step 1: Tests que fallan**

Crear `server/tests/test_mlx_orchestrator.py`:

```python
import pytest
from ide_server.mlx.orchestrator import MlxRouter
from ide_server.mlx.router import RouteDecision
from ide_server.mlx.server import MlxUnavailable


class _Srv:
    def __init__(self, url="http://x", fail=False): self._url = url; self._fail = fail
    async def ensure_running(self):
        if self._fail: raise MlxUnavailable("nope")
        return self._url
    def stop(self): pass


class _Router:
    def __init__(self, dec): self._dec = dec
    async def route(self, text): return self._dec


@pytest.mark.asyncio
async def test_decide_local():
    r = MlxRouter(_Srv(), lambda url: _Router(RouteDecision("local", "hola")))
    assert (await r.decide("hi")).route == "local"


@pytest.mark.asyncio
async def test_decide_degrades_when_unavailable():
    r = MlxRouter(_Srv(fail=True), lambda url: _Router(RouteDecision("local", "x")))
    d = await r.decide("hi")
    assert d.route == "claude" and d.degraded is True
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

Crear `server/ide_server/mlx/orchestrator.py`:

```python
from __future__ import annotations
from pathlib import Path
from ide_server.mlx.config import mlx_config
from ide_server.mlx.server import MlxServer, MlxUnavailable
from ide_server.mlx.client import MlxClient
from ide_server.mlx.router import PromptRouter, RouteDecision


class MlxRouter:
    def __init__(self, server, router_factory) -> None:
        # router_factory(base_url) -> objeto con async route(text) -> RouteDecision
        self._server = server
        self._router_factory = router_factory

    async def decide(self, text: str) -> RouteDecision:
        try:
            url = await self._server.ensure_running()
        except MlxUnavailable:
            return RouteDecision(route="claude", reply=None, degraded=True)
        return await self._router_factory(url).route(text)


def build_mlx_router(root: Path) -> MlxRouter | None:
    cfg = mlx_config(root)
    if cfg is None:
        return None
    server = MlxServer(cfg.model, find_port=(lambda h, s: cfg.port) if cfg.port else None)
    return MlxRouter(server, lambda url: PromptRouter(MlxClient(url), cfg.router_prompt))
```

En `server/ide_server/app.py`: `from ide_server.mlx.orchestrator import build_mlx_router`, y cablear:

```python
    mlx_router = build_mlx_router(root)
    hub = chat_cap.register(registry, root, manager, mlx_router=mlx_router)
```

- [ ] **Step 4: Correr, verificar que pasan** → PASS. Suite completa → PASS (app.py sigue armando).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/mlx/orchestrator.py server/ide_server/app.py server/tests/test_mlx_orchestrator.py
git commit -m "feat(mlx): MlxRouter.decide (degrada a claude si mlx no está) + wire en app"
```

---

### Task 5: Evento `Routed` + triage en `chat.send`

**Files:**
- Modify: `server/ide_server/chat/events.py`, `server/ide_server/capabilities/chat.py`
- Test: `server/tests/test_chat_events.py`, `server/tests/test_chat_capability.py`

**Interfaces:**
- Consumes: `MlxRouter.decide` (T4); `TextDelta`/`Done`/`ChatError` (events existentes).
- Produces: `Routed(source:str)` en events; `chat.send` con triage.

- [ ] **Step 1: Tests que fallan**

En `server/tests/test_chat_events.py` agregar:

```python
def test_routed_payload():
    from ide_server.chat.events import Routed, to_payload
    assert to_payload(Routed(source="local")) == {"kind": "routed", "source": "local"}
```

En `server/tests/test_chat_capability.py` agregar (usa el `FakeManager`/`FakeDriver` del archivo):

```python
class _FakeRouter:
    def __init__(self, decision): self._d = decision
    async def decide(self, text): return self._d


@pytest.mark.asyncio
async def test_send_local_route_answers_without_driver(tmp_path, monkeypatch):
    from ide_server.mlx.router import RouteDecision
    import ide_server.capabilities.chat as chatmod
    reg = Registry(); mgr = FakeManager()
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None})
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver,
                     mlx_router=_FakeRouter(RouteDecision("local", "respuesta local")))
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    FakeDriver.last.sent.clear()
    await reg.dispatch("chat.send", {"sessionId": "s1", "text": "hola"})
    kinds = [p for _, p in mgr.events]
    assert {"kind": "routed", "source": "local"} in kinds
    assert any(p.get("kind") == "text_delta" and p.get("text") == "respuesta local" for p in kinds)
    assert FakeDriver.last.sent == []                       # NO tocó a Claude


@pytest.mark.asyncio
async def test_send_claude_route_calls_driver(tmp_path, monkeypatch):
    from ide_server.mlx.router import RouteDecision
    import ide_server.capabilities.chat as chatmod
    reg = Registry(); mgr = FakeManager()
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None})
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver,
                     mlx_router=_FakeRouter(RouteDecision("claude", None)))
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    await reg.dispatch("chat.send", {"sessionId": "s1", "text": "edita main.py"})
    assert FakeDriver.last.sent == ["edita main.py"]
    assert {"kind": "routed", "source": "claude"} in [p for _, p in mgr.events]


@pytest.mark.asyncio
async def test_send_degraded_emits_warning(tmp_path, monkeypatch):
    from ide_server.mlx.router import RouteDecision
    import ide_server.capabilities.chat as chatmod
    reg = Registry(); mgr = FakeManager()
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None})
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver,
                     mlx_router=_FakeRouter(RouteDecision("claude", None, degraded=True)))
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    await reg.dispatch("chat.send", {"sessionId": "s1", "text": "hola"})
    assert any(p.get("kind") == "error" for _, p in mgr.events)     # aviso visible
    assert FakeDriver.last.sent == ["hola"]                          # igual va a Claude
```

(Los tests existentes de `chat.send` — sin `mlx_router` — deben seguir verdes: `mlx_router=None` →
flujo actual.)

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

En `server/ide_server/chat/events.py`, agregar la dataclass y la rama en `to_payload`:

```python
@dataclass
class Routed:
    source: str            # "local" | "claude"
```
```python
    if isinstance(event, Routed):
        return {"kind": "routed", "source": event.source}
```

En `server/ide_server/capabilities/chat.py`: `register(..., mlx_router=None)` y reescribir `send`:

```python
from ide_server.chat.events import Routed, TextDelta, Done, ChatError
```
```python
    async def send(payload: dict) -> dict:
        sid, text = payload["sessionId"], payload["text"]
        decision = await mlx_router.decide(text) if mlx_router is not None else None
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
```

> Verifica la firma de `hub.emit` (es `async def emit(self, session_id, event)` que hace
> `await manager.broadcast(...)`, del SessionHub). `ChatError` tiene `code`/`message`.

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd server && uv run pytest tests/test_chat_events.py tests/test_chat_capability.py -q` → PASS.
Suite completa: `cd server && uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/chat/events.py server/ide_server/capabilities/chat.py server/tests/test_chat_events.py server/tests/test_chat_capability.py
git commit -m "feat(mlx): triage en chat.send (local responde sin tocar Claude; claude/degraded avisan)"
```

---

### Task 6: Frontend — badge de routing

**Files:**
- Modify: `ui/src/state/chat.ts`, `ui/src/chat/MessageBubble.tsx`
- Test: `ui/src/state/chat.test.ts`, `ui/src/chat/MessageBubble.test.tsx` (o el test de bubble existente)

**Interfaces:**
- `Msg` gana `source?: "local" | "claude"`. `applyEvent` maneja `kind:"routed"`.

- [ ] **Step 1: Tests que fallan**

En `ui/src/state/chat.test.ts` agregar:

```ts
it("un evento routed taggea el próximo mensaje de agente con source", () => {
  const { applyEvent } = useChat.getState();
  applyEvent("s1", { kind: "routed", source: "local" });
  applyEvent("s1", { kind: "text_delta", text: "hola" });
  const c = useChat.getState().convos["s1"];
  const m = c.messages[c.messages.length - 1];
  expect(m.role).toBe("agent");
  expect(m.text).toBe("hola");
  expect(m.source).toBe("local");
});
```

En el test del bubble (mira `MessageBubble.test.tsx` — el que ya tiene el badge de relay): agregar
un caso que renderice un `Msg` de agente con `source:"local"` y asere que aparece el badge "local".

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

En `ui/src/state/chat.ts`: `Msg` gana `source?: "local" | "claude"`. Agregar `pendingSource` al
`Convo` (o una variable). En `applyEvent`:

```ts
    else if (e.kind === "routed") { c.pendingSource = e.source; }
```
y en `lastAgent(c)`, al crear un `Msg` de agente nuevo, tomar `c.pendingSource`:

```ts
function lastAgent(c: Convo): Msg {
  const last = c.messages[c.messages.length - 1];
  if (last && last.role === "agent") return last;
  const m: Msg = { role: "agent", text: "", chips: [], source: c.pendingSource };
  c.pendingSource = undefined;
  c.messages.push(m);
  return m;
}
```
(agregar `pendingSource?: "local" | "claude"` a la interfaz `Convo`, y `source?` a `Msg`).

En `ui/src/chat/MessageBubble.tsx`: si el `Msg` es de agente y tiene `source`, mostrar un badge:
**"local"** (color distinto, p.ej. `text-[#7fb069]` verde) o **"claude"** (`text-[#e0863f]` ámbar),
junto al mensaje. Sigue el markup del badge de relay ya existente.

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd ui && npm test -- chat MessageBubble` → PASS. Suite completa: `cd ui && npm test` → PASS.
`cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/state/chat.ts ui/src/chat/MessageBubble.tsx ui/src/state/chat.test.ts ui/src/chat/MessageBubble.test.tsx
git commit -m "feat(mlx): badge local/claude por turno en el chat"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** config por-proyecto (T1), router pluggable prompt-based (T2), client+server
  lifecycle (T3), MlxRouter.decide+degradación (T4), evento Routed + triage en chat.send (T5), badge
  (T6). ✓
- **Consistencia:** `RouteDecision{route,reply,degraded}` (T2) usado en T4/T5; `MlxRouter.decide` (T4)
  ↔ `chat.send` (T5); `Routed{source}` (T5) ↔ front (T6). mlx off (`mlx_router=None`) → chat.send
  idéntico a hoy (tests existentes verdes). ✓
- **Riesgo señalado:** `parse_route` — la nota del Step 3/T2 simplifica a la comparación exacta con
  el sentinela (ignorar el ejemplo redundante). httpx pasa a runtime (ya viene transitivo por
  notion-client). El extra `mlx` no se importa (solo se spawnea) → no rompe non-Mac.
- **Verificación E2E manual (fuera del plan):** instalar `ide-server[mlx]` + bajar un modelo,
  `[mlx].enabled=true`, y probar en el chat una pregunta simple (→ local) y una de código (→ Claude).
```
