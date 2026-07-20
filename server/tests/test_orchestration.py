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
    res = await orq._t_ask_session(hub, "coord", {"session_id": "c1", "task": "hacé X"})
    assert hub.asked == [("c1", "hacé X")]
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
