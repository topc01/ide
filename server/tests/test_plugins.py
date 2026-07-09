import pytest
from ide_server.plugins import Registry

@pytest.mark.asyncio
async def test_register_and_dispatch():
    reg = Registry()
    async def handler(payload): return {"echo": payload["x"]}
    reg.register("t.echo", handler)
    assert await reg.dispatch("t.echo", {"x": 1}) == {"echo": 1}

@pytest.mark.asyncio
async def test_unknown_channel():
    reg = Registry()
    with pytest.raises(KeyError):
        await reg.dispatch("nope", {})
