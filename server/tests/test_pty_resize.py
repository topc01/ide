from ide_server.pty_manager import PtyManager


def _read_until(m, tid, needle, tries=80):
    out = b""
    for _ in range(tries):
        out += m.read(tid, timeout=0.1)
        if needle in out:
            break
    return out


def test_resize_changes_winsize(tmp_path):
    m = PtyManager()
    tid = m.spawn(tmp_path, ["sh"])
    m.resize(tid, cols=100, rows=40)
    m.write(tid, b"stty size\n")               # imprime "rows cols" = "40 100"
    assert b"40 100" in _read_until(m, tid, b"40 100")
    m.close(tid)
