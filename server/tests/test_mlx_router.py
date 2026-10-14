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
    async def chat_stream(self, messages, emit):
        self.messages = messages
        await emit(self._reply)
        return self._reply


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


@pytest.mark.asyncio
async def test_prompt_router_answer_stream_is_direct():
    c = _FakeClient("respuesta directa")
    got = []
    async def emit(ch): got.append(ch)
    out = await PromptRouter(c, "SYS").answer_stream("cuánto es 2+2", emit)
    assert out == "respuesta directa" and got == ["respuesta directa"]
    # answer_stream NO usa el prompt de router (clasificador); usa un system distinto
    assert c.messages[0]["role"] == "system" and c.messages[0]["content"] != "SYS"
    assert c.messages[1] == {"role": "user", "content": "cuánto es 2+2"}
