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


@pytest.mark.asyncio
async def test_concurrent_ensure_running_spawns_once():
    import asyncio
    spawns = {"n": 0}
    def fake_spawn(cmd): spawns["n"] += 1; return _FakeProc()
    async def fake_get(url): return True                # sano al primer poll (sin sleep)
    srv = MlxServer("m", spawn=fake_spawn, http_get=fake_get, find_port=lambda h, s: 9001)
    urls = await asyncio.gather(srv.ensure_running(), srv.ensure_running())
    assert spawns["n"] == 1
    assert urls[0] == urls[1] == "http://127.0.0.1:9001"
