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
    def __init__(self, dec, answer="respuesta directa"): self._dec = dec; self._answer = answer
    async def route(self, text): return self._dec
    async def answer_stream(self, text, emit):
        await emit(self._answer)
        return self._answer


@pytest.mark.asyncio
async def test_decide_local():
    r = MlxRouter(_Srv(), lambda url: _Router(RouteDecision("local", "hola")))
    assert (await r.decide("hi")).route == "local"


@pytest.mark.asyncio
async def test_decide_degrades_when_unavailable():
    r = MlxRouter(_Srv(fail=True), lambda url: _Router(RouteDecision("local", "x")))
    d = await r.decide("hi")
    assert d.route == "claude" and d.degraded is True


@pytest.mark.asyncio
async def test_decide_force_claude_skips_mlx():
    # force="claude" no debe tocar el server (aunque falle) → claude directo
    r = MlxRouter(_Srv(fail=True), lambda url: _Router(RouteDecision("local", "x")))
    d = await r.decide("hi", force="claude")
    assert d.route == "claude" and d.degraded is False


@pytest.mark.asyncio
async def test_stream_local_streams_chunks():
    r = MlxRouter(_Srv(), lambda url: _Router(RouteDecision("claude", None), answer="hola local"))
    got = []
    async def emit(ch): got.append(ch)
    full = await r.stream_local("hi", emit)
    assert got == ["hola local"] and full == "hola local"


@pytest.mark.asyncio
async def test_stream_local_raises_when_unavailable():
    r = MlxRouter(_Srv(fail=True), lambda url: _Router(RouteDecision("local", "x")))
    async def emit(ch): pass
    with pytest.raises(MlxUnavailable):
        await r.stream_local("hi", emit)


@pytest.mark.asyncio
async def test_aclose_stops_server():
    class _S:
        def __init__(self): self.stopped = False
        async def ensure_running(self): return "http://x"
        def stop(self): self.stopped = True
    s = _S()
    r = MlxRouter(s, lambda url: None)
    await r.aclose()
    assert s.stopped is True
