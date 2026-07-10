import subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import terminals as term_cap
from ide_server.sessions_store import save_sessions


class _FakeManager:                            # ConnectionManager stub (no streaming en Task 3)
    async def broadcast(self, channel, payload): pass


def _ws(tmp_path: Path) -> Path:
    (tmp_path / ".ide" / "worktrees" / "s1").mkdir(parents=True)
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, check=True)
    save_sessions(tmp_path, [{"id": "s1", "name": "S1", "repoId": "repoA",
                              "worktreePath": str(tmp_path / ".ide" / "worktrees" / "s1"),
                              "children": []}])
    return tmp_path


@pytest.mark.asyncio
async def test_open_in_session_cwd_and_list(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); term_cap.register(reg, ws, _FakeManager())
    out = await reg.dispatch("terminal.open", {"sessionId": "s1", "cmd": ["echo", "x"]})
    assert out["id"]
    assert out["cwd"].endswith("/worktrees/s1")
    lst = await reg.dispatch("terminal.list", {"sessionId": "s1"})
    assert lst["terminals"][0]["id"] == out["id"]


@pytest.mark.asyncio
async def test_open_repo_main_cwd(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); term_cap.register(reg, ws, _FakeManager())
    out = await reg.dispatch("terminal.open", {"repoId": "repoA", "cmd": ["echo", "x"]})
    assert out["cwd"].endswith("/repoA")


@pytest.mark.asyncio
async def test_open_unknown_session_raises(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); term_cap.register(reg, ws, _FakeManager())
    with pytest.raises(KeyError):
        await reg.dispatch("terminal.open", {"sessionId": "nope", "cmd": ["echo", "x"]})
