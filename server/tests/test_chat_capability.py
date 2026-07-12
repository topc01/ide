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
