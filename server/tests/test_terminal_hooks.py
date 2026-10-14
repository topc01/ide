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
