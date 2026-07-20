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


@pytest.mark.asyncio
async def test_ask_returns_child_text_and_emits_relays(tmp_path):
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir(exist_ok=True)
    save_sessions(tmp_path, [{"id": "coord", "name": "King",
                              "children": [{"id": "c1", "name": "Hija A", "worktreePath": str(tmp_path)}]}])
    hub = SessionHub(tmp_path, FakeManager(), FakeDriver)
    hub._load_ctx = lambda sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                                 "model": None, "is_coordinator": sid == "coord"}
    reply = await hub.ask("coord", "c1", "compilá")
    assert reply == "ok"
    kinds = [(ch, p["kind"], p.get("direction"), p.get("text")) for ch, p in hub.manager.events if p["kind"] == "relay"]
    # entrante a la hija, saliente al coord, respuesta entrante al coord
    assert ("chat.event.c1", "relay", "in", "compilá") in kinds
    assert ("chat.event.coord", "relay", "out", "compilá") in kinds
    assert ("chat.event.coord", "relay", "in", "ok") in kinds


@pytest.mark.asyncio
async def test_ask_flushes_child_broadcasts_before_returning(tmp_path):
    # `send` de la hija dispara `on_event` (TextDelta) de forma síncrona durante
    # el `ask`; ese broadcast se encola vía `_make_on_event` y debe quedar
    # flusheado en `manager.events` al retornar `ask`, no en un tick futuro
    # (invariante del hub: sin tasks huérfanas cuyas excepciones nunca se recuperen).
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir(exist_ok=True)
    save_sessions(tmp_path, [{"id": "coord", "name": "King",
                              "children": [{"id": "c1", "name": "Hija A", "worktreePath": str(tmp_path)}]}])

    class StreamingFakeDriver(FakeDriver):
        async def send(self, text):
            self.sent.append(text)
            self.on_event(TextDelta(text="stream"))
            return "ok"

    hub = SessionHub(tmp_path, FakeManager(), StreamingFakeDriver)
    hub._load_ctx = lambda sid: {"cwd": str(tmp_path), "system_prompt": "s", "role": None,
                                 "model": None, "is_coordinator": sid == "coord"}
    await hub.ask("coord", "c1", "x")
    assert ("chat.event.c1", {"kind": "text_delta", "text": "stream"}) in hub.manager.events


@pytest.mark.asyncio
async def test_ask_serializes_per_session(tmp_path):
    # dos ask concurrentes a la misma hija no se solapan (el driver registra orden)
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir(exist_ok=True)
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


def test_list_children(tmp_path):
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir(exist_ok=True)
    save_sessions(tmp_path, [{"id": "coord", "name": "K", "children": [
        {"id": "c1", "name": "A", "status": "idle", "repoId": "repo1", "worktreePath": "/x"},
        {"id": "c2", "name": "B", "status": "running", "repoId": "repo2", "worktreePath": "/y"}]}])
    hub = SessionHub(tmp_path, FakeManager(), FakeDriver)
    kids = hub.list_children("coord")
    assert kids == [{"sessionId": "c1", "name": "A", "status": "idle", "repoId": "repo1"},
                    {"sessionId": "c2", "name": "B", "status": "running", "repoId": "repo2"}]
    assert hub.list_children("desconocido") == []
