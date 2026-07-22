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
