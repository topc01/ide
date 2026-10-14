import asyncio
import pytest
from ide_server.plugins import Registry
from ide_server.chat.events import TextDelta, PermissionRequest

class FakeManager:
    def __init__(self): self.events: list[tuple[str, dict]] = []
    async def broadcast(self, channel, payload): self.events.append((channel, payload))

class FakeDriver:
    last = None
    def __init__(self, *, cwd, system_prompt, permission_mode, allowed_tools,
                 on_event, on_permission, resume=None, model=None, client_factory=None):
        self.cwd = cwd; self.system_prompt = system_prompt
        self.permission_mode = permission_mode; self.allowed_tools = allowed_tools
        self.model = model
        self.on_event = on_event; self.on_permission = on_permission
        self.sent: list[str] = []; self.started = False; self.session_id = resume
        FakeDriver.last = self
    async def start(self): self.started = True
    async def send(self, text):
        self.sent.append(text); self.on_event(TextDelta(text="respuesta"))
    async def interrupt(self): pass

@pytest.mark.asyncio
async def test_start_then_send_broadcasts_events(tmp_path, monkeypatch):
    from ide_server import capabilities
    reg = Registry(); mgr = FakeManager()
    # Sembrar un árbol de sesiones mínimo con la sesión "s1".
    import ide_server.capabilities.chat as chatmod
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "sys", "role": None})
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver)
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    assert FakeDriver.last.started is True
    await reg.dispatch("chat.send", {"sessionId": "s1", "text": "hola"})
    assert FakeDriver.last.sent == ["hola"]
    assert ("chat.event.s1", {"kind": "text_delta", "text": "respuesta"}) in mgr.events

@pytest.mark.asyncio
async def test_start_applies_read_only_role_and_model(tmp_path):
    from ide_server.sessions_store import save_sessions
    import ide_server.capabilities.chat as chatmod
    (tmp_path / ".ide").mkdir()
    save_sessions(tmp_path, [{"id": "s1", "worktreePath": str(tmp_path), "role": "lector"}])
    reg = Registry(); mgr = FakeManager()
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver)
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    assert FakeDriver.last.permission_mode == "default"
    assert FakeDriver.last.allowed_tools == ["Read", "Grep", "Glob", "LS"]
    assert FakeDriver.last.model == "haiku"

@pytest.mark.asyncio
async def test_permission_decision_resolves_future(tmp_path, monkeypatch):
    import ide_server.capabilities.chat as chatmod
    reg = Registry(); mgr = FakeManager()
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None})
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver)
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    # Simular una petición de permiso del driver y su decisión.
    on_perm = FakeDriver.last.on_permission
    task = asyncio.ensure_future(on_perm("req-1"))
    await asyncio.sleep(0)
    await reg.dispatch("chat.permission", {"sessionId": "s1", "requestId": "req-1", "allow": True})
    assert await task is True

class _FakeRouter:
    def __init__(self, decision): self._d = decision; self.forced = "unset"; self.streamed = None
    async def decide(self, text, force=None): self.forced = force; return self._d
    async def stream_local(self, text, emit):
        self.streamed = text
        for ch in ["ho", "la"]: await emit(ch)
        return "hola"


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


@pytest.mark.asyncio
async def test_send_forwards_manual_override_to_router(tmp_path, monkeypatch):
    from ide_server.mlx.router import RouteDecision
    import ide_server.capabilities.chat as chatmod
    reg = Registry(); mgr = FakeManager()
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None})
    router = _FakeRouter(RouteDecision("claude", None))
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver, mlx_router=router)
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    await reg.dispatch("chat.send", {"sessionId": "s1", "text": "hola", "route": "claude"})
    assert router.forced == "claude"                                # el override llega al router


@pytest.mark.asyncio
async def test_send_force_local_without_mlx_errors(tmp_path, monkeypatch):
    import ide_server.capabilities.chat as chatmod
    reg = Registry(); mgr = FakeManager()
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None})
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver, mlx_router=None)
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    FakeDriver.last.sent.clear()
    out = await reg.dispatch("chat.send", {"sessionId": "s1", "text": "hola", "route": "local"})
    assert out == {"sent": False}
    assert any(p.get("kind") == "error" and p.get("code") == "mlx_off" for _, p in mgr.events)
    assert FakeDriver.last.sent == []                                # no fue a Claude


@pytest.mark.asyncio
async def test_send_force_local_streams_chunks(tmp_path, monkeypatch):
    from ide_server.mlx.router import RouteDecision
    import ide_server.capabilities.chat as chatmod
    reg = Registry(); mgr = FakeManager()
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None})
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver,
                     mlx_router=_FakeRouter(RouteDecision("local", "x")))
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    FakeDriver.last.sent.clear()
    out = await reg.dispatch("chat.send", {"sessionId": "s1", "text": "escribe un poema", "route": "local"})
    kinds = [p for _, p in mgr.events]
    assert {"kind": "routed", "source": "local"} in kinds
    deltas = [p.get("text") for p in kinds if p.get("kind") == "text_delta"]
    assert deltas == ["ho", "la"]                                   # streameado en chunks
    assert any(p.get("kind") == "done" for p in kinds)
    assert FakeDriver.last.sent == [] and out == {"sent": True, "route": "local"}


@pytest.mark.asyncio
async def test_send_force_local_degrades_to_claude(tmp_path, monkeypatch):
    from ide_server.mlx.server import MlxUnavailable
    import ide_server.capabilities.chat as chatmod

    class _Unavail:
        async def stream_local(self, text, emit): raise MlxUnavailable("nope")

    reg = Registry(); mgr = FakeManager()
    monkeypatch.setattr(chatmod, "_load_session_context",
                        lambda root, sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None})
    chatmod.register(reg, tmp_path, mgr, driver_factory=FakeDriver, mlx_router=_Unavail())
    await reg.dispatch("chat.start", {"sessionId": "s1"})
    FakeDriver.last.sent.clear()
    out = await reg.dispatch("chat.send", {"sessionId": "s1", "text": "hola", "route": "local"})
    assert any(p.get("kind") == "error" for _, p in mgr.events)
    assert FakeDriver.last.sent == ["hola"]                         # degradó a Claude
    assert out == {"sent": True, "route": "claude"}


def test_airegex_session_usa_prompt_de_regex_y_cwd_del_worktree(tmp_path):
    from ide_server.capabilities.chat import _load_session_context, _LANG, REGEX_AGENT_PROMPT
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir()
    save_sessions(tmp_path, [{"id": "s1", "worktreePath": str(tmp_path)}])
    ctx = _load_session_context(tmp_path, "airegex:s1")
    assert ctx["cwd"] == str(tmp_path)
    assert ctx["system_prompt"].startswith(_LANG)
    assert REGEX_AGENT_PROMPT in ctx["system_prompt"]
    assert ctx["role"] is None and ctx["model"] is None
    assert ctx["is_coordinator"] is False


def test_airegex_de_sesion_inexistente_cae_al_root(tmp_path):
    from ide_server.capabilities.chat import _load_session_context, REGEX_AGENT_PROMPT
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir()
    save_sessions(tmp_path, [])
    ctx = _load_session_context(tmp_path, "airegex:nope")
    assert ctx["cwd"] == str(tmp_path)                 # fallback al root, no explota
    assert REGEX_AGENT_PROMPT in ctx["system_prompt"]


def test_load_session_context_spanish_instruction_always_first(tmp_path):
    from ide_server.capabilities.chat import _load_session_context, _LANG
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir()
    # Caso 1: sesión con descripción y rol (ambos contribuyen al prompt)
    save_sessions(tmp_path, [
        {"id": "s1", "worktreePath": str(tmp_path), "description": "My session", "role": "lector"}
    ])
    ctx = _load_session_context(tmp_path, "s1")
    assert ctx["system_prompt"].startswith(_LANG)
    assert "My session" in ctx["system_prompt"]
    # Caso 2: sesión sin descripción ni rol (solo _LANG)
    save_sessions(tmp_path, [{"id": "s2", "worktreePath": str(tmp_path)}])
    ctx = _load_session_context(tmp_path, "s2")
    assert ctx["system_prompt"] == _LANG
    # Caso 3: sesión con descripción pero sin rol
    save_sessions(tmp_path, [
        {"id": "s3", "worktreePath": str(tmp_path), "description": "Another session"}
    ])
    ctx = _load_session_context(tmp_path, "s3")
    assert ctx["system_prompt"].startswith(_LANG)
    assert "Another session" in ctx["system_prompt"]
