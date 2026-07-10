# server/tests/test_terminals_io.py
import base64
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import terminals as term_cap


class _FakeManager:
    async def broadcast(self, channel, payload): pass


def _ws(tmp_path: Path) -> Path:
    (tmp_path / ".ide").mkdir()
    return tmp_path


@pytest.mark.asyncio
async def test_write_reaches_pty_and_close(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); term_cap.register(reg, ws, _FakeManager())
    opened = await reg.dispatch("terminal.open", {"cmd": ["cat"]})
    tid = opened["id"]
    await reg.dispatch("terminal.write",
                       {"id": tid, "data": base64.b64encode(b"eco-42\n").decode()})
    pty = term_cap.register._pty
    out = b""
    for _ in range(80):
        out += pty.read(tid, timeout=0.1)
        if b"eco-42" in out:
            break
    assert b"eco-42" in out
    await reg.dispatch("terminal.resize", {"id": tid, "cols": 90, "rows": 30})
    assert (await reg.dispatch("terminal.close", {"id": tid}))["ok"] is True
    assert pty.is_alive(tid) is False
