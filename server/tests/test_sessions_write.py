import subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import sessions as sessions_cap
from ide_server.launcher import NullLauncher
from ide_server.worktrees import branch_occupied, BranchOccupied
from ide_server.sessions_store import load_sessions


def _ws(tmp_path: Path) -> Path:
    (tmp_path / ".ide" / "worktrees").mkdir(parents=True)
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, check=True)
    return tmp_path


@pytest.mark.asyncio
async def test_create_coordinator_persists(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); sessions_cap.register(reg, ws)
    out = await reg.dispatch("sessions.create",
        {"name": "Feature X", "kind": "coordinator"})
    assert out["session"]["branch"] is None
    assert load_sessions(ws)[0]["name"] == "Feature X"


@pytest.mark.asyncio
async def test_create_work_rw_makes_worktree_and_launches(tmp_path):
    ws = _ws(tmp_path)
    launcher = NullLauncher()
    reg = Registry(); sessions_cap.register(reg, ws, launcher=launcher)
    out = await reg.dispatch("sessions.create",
        {"name": "Fix", "kind": "work", "repoId": "repoA",
         "branch": "fix-1", "base": "main", "access": "rw"})
    assert branch_occupied(ws / "repoA", "fix-1") is True
    assert out["session"]["worktreePath"].endswith("/fix-1") or "fix" in out["session"]["worktreePath"]
    assert launcher.launched and launcher.launched[0]["name"] == "Fix"


@pytest.mark.asyncio
async def test_create_rw_on_occupied_branch_raises(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); sessions_cap.register(reg, ws)
    with pytest.raises(BranchOccupied):
        await reg.dispatch("sessions.create",
            {"name": "OnMain", "kind": "work", "repoId": "repoA",
             "branch": "main", "access": "rw"})


@pytest.mark.asyncio
async def test_rename(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); sessions_cap.register(reg, ws)
    created = await reg.dispatch("sessions.create", {"name": "A", "kind": "coordinator"})
    sid = created["session"]["id"]
    out = await reg.dispatch("sessions.rename", {"id": sid, "name": "B"})
    assert out["renamed"] is True
    assert load_sessions(ws)[0]["name"] == "B"


@pytest.mark.asyncio
async def test_close_rw_preserves_branch(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); sessions_cap.register(reg, ws)
    created = await reg.dispatch("sessions.create",
        {"name": "Fix", "kind": "work", "repoId": "repoA",
         "branch": "fix-2", "base": "main", "access": "rw"})
    sid = created["session"]["id"]
    out = await reg.dispatch("sessions.close", {"id": sid})
    assert out["closed"] is True
    # branch preservada, worktree removido → ya no ocupada
    assert branch_occupied(ws / "repoA", "fix-2") is False
    r = subprocess.run(["git", "-C", str(ws / "repoA"), "rev-parse", "--verify",
                        "refs/heads/fix-2"], capture_output=True)
    assert r.returncode == 0
