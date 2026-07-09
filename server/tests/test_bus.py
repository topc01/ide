import json
import pytest
from ide_server.bus import handle_message
from ide_server.plugins import Registry

@pytest.mark.asyncio
async def test_req_returns_res():
    reg = Registry()
    async def h(p): return {"n": p["n"] + 1}
    reg.register("t.inc", h)
    raw = json.dumps({"type": "req", "id": "1", "channel": "t.inc", "payload": {"n": 41}})
    out = json.loads(await handle_message(raw, reg))
    assert out == {"type": "res", "id": "1", "channel": "t.inc", "payload": {"n": 42}}

@pytest.mark.asyncio
async def test_unknown_channel_returns_error():
    raw = json.dumps({"type": "req", "id": "9", "channel": "nope", "payload": {}})
    out = json.loads(await handle_message(raw, Registry()))
    assert out["type"] == "error"
    assert out["id"] == "9"
    assert out["payload"]["code"] == "unknown_channel"

@pytest.mark.asyncio
async def test_non_json_returns_error():
    out = json.loads(await handle_message("not json {{{", Registry()))
    assert out["type"] == "error"
    assert out["payload"]["code"] == "invalid_message"

@pytest.mark.asyncio
async def test_non_object_json_returns_error():
    out = json.loads(await handle_message("[1, 2]", Registry()))
    assert out["type"] == "error"
    assert out["payload"]["code"] == "invalid_message"
