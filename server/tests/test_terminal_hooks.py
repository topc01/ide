import asyncio
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import terminals as term_cap


class Rec:
    def __init__(self): self.events = []
    async def broadcast(self, channel, payload): self.events.append((channel, payload))


@pytest.mark.asyncio
async def test_hooks_spawn_with_env_streams_and_calls_on_exit(tmp_path):
    rec, exited = Rec(), asyncio.Event()
    hooks = term_cap.register(Registry(), tmp_path, rec)
    tid = hooks.spawn(tmp_path, ["sh", "-c", 'echo "v=$FOO"'], {"FOO": "bar", "PATH": "/bin:/usr/bin"},
                      exited.set, session_id="s1")
    await asyncio.wait_for(exited.wait(), 5)
    import base64
    data = b"".join(base64.b64decode(p["data"]) for c, p in rec.events if c == f"terminal.data.{tid}")
    assert b"v=bar" in data
    assert (f"terminal.exit.{tid}", {}) in rec.events


@pytest.mark.asyncio
async def test_hooks_kill(tmp_path):
    hooks = term_cap.register(Registry(), tmp_path, Rec())
    exits = []
    tid = hooks.spawn(tmp_path, ["sleep", "30"], {"PATH": "/bin:/usr/bin"}, lambda: exits.append(1))
    hooks.kill(tid)                              # reap sincrónico: no cuelga ni deja zombie
    await asyncio.sleep(0.1)
    assert exits == []                           # un kill explícito no dispara on_exit


@pytest.mark.filterwarnings("ignore:This process .* forkpty")
@pytest.mark.asyncio
async def test_natural_exit_releases_pty_and_kill_is_noop(tmp_path):          # I7
    from ide_server.pty_manager import PtyManager
    pty, exited, chunks = PtyManager(), asyncio.Event(), []
    hooks = term_cap.register(Registry(), tmp_path, Rec(), pty)
    tid = hooks.spawn(tmp_path, ["sh", "-c", "echo hola"], {"PATH": "/bin:/usr/bin"}, exited.set,
                      on_output=chunks.append)
    await asyncio.wait_for(exited.wait(), 5)
    assert tid not in pty.list_ids()
    hooks.kill(tid)                              # ya cosechado: no-op, no explota
    assert b"hola" in b"".join(chunks)


@pytest.mark.filterwarnings("ignore:This process .* forkpty")
@pytest.mark.asyncio
async def test_write_calls_on_input(tmp_path):
    reg, inputs = Registry(), []
    hooks = term_cap.register(reg, tmp_path, Rec())
    tid = hooks.spawn(tmp_path, ["cat"], {"PATH": "/bin:/usr/bin"}, lambda: None,
                      on_input=lambda: inputs.append(1))
    import base64
    await reg.dispatch("terminal.write", {"id": tid, "data": base64.b64encode(b"\r").decode()})
    assert inputs == [1]
    hooks.kill(tid)
