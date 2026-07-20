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


class SlowFakeDriver(FakeDriver):
    """Como FakeDriver, pero cede el loop en `start()` para poder forzar el
    entrelazado de dos `ensure_started` concurrentes en el mismo test."""
    instances = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        SlowFakeDriver.instances += 1

    async def start(self):
        await asyncio.sleep(0)
        self.started = True


@pytest.mark.asyncio
async def test_ensure_started_concurrent_creates_single_driver(tmp_path):
    SlowFakeDriver.instances = 0
    hub = _hub(tmp_path, ctx={"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                              "model": None, "is_coordinator": False})
    hub._factory = SlowFakeDriver

    d1, d2 = await asyncio.gather(
        hub.ensure_started("s1"), hub.ensure_started("s1"),
    )

    assert d1 is d2
    assert SlowFakeDriver.instances == 1
