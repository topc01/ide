import os
from pathlib import Path
import pytest
from ide_server.pty_manager import PtyManager


def _read_until(m: PtyManager, tid: str, needle: bytes, tries: int = 80) -> bytes:
    out = b""
    for _ in range(tries):
        out += m.read(tid, timeout=0.1)
        if needle in out:
            break
    return out


def test_spawn_echo_produces_output(tmp_path):
    m = PtyManager()
    tid = m.spawn(tmp_path, ["echo", "hola-pty"])
    assert _read_until(m, tid, b"hola-pty").find(b"hola-pty") >= 0
    m.close(tid)


def test_write_is_echoed_back(tmp_path):
    m = PtyManager()
    tid = m.spawn(tmp_path, ["cat"])          # cat repite lo que recibe
    m.write(tid, b"ping-123\n")
    assert b"ping-123" in _read_until(m, tid, b"ping-123")
    m.close(tid)


def test_close_kills_process(tmp_path):
    m = PtyManager()
    tid = m.spawn(tmp_path, ["sleep", "30"])
    assert m.is_alive(tid) is True
    pid = m._terms[tid]["pid"]
    m.close(tid)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)                        # el proceso ya no existe
    assert tid not in m.list_ids()
