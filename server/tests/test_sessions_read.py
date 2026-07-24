import subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import sessions as sessions_cap
from ide_server.sessions_store import save_sessions


def _ws(tmp_path: Path) -> Path:
    (tmp_path / ".ide").mkdir()
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, check=True)
    return tmp_path


@pytest.mark.asyncio
async def test_tree_returns_sessions_and_repos(tmp_path):
    ws = _ws(tmp_path)
    save_sessions(ws, [{"id": "s1", "name": "Coord", "children": []}])
    reg = Registry(); sessions_cap.register(reg, ws)
    out = await reg.dispatch("sessions.tree", {})
    assert out["sessions"][0]["name"] == "Coord"
    assert out["repos"][0]["name"] == "repoA"


@pytest.mark.asyncio
async def test_tree_annotates_live_branch(tmp_path):
    ws = _ws(tmp_path)
    save_sessions(ws, [{"id": "s1", "name": "Coord", "children": [
        {"id": "s2", "name": "Hija", "worktreePath": "/wt/a", "branch": "vieja", "children": []}]}])
    reg = Registry()
    sessions_cap.register(reg, ws, branch_of=lambda wt: "viva")
    out = await reg.dispatch("sessions.tree", {})
    hija = out["sessions"][0]["children"][0]
    assert hija["branch"] == "viva"                         # rama en vivo, no la guardada


@pytest.mark.asyncio
async def test_tree_keeps_stored_branch_when_git_fails(tmp_path):
    ws = _ws(tmp_path)
    save_sessions(ws, [{"id": "s1", "name": "s", "worktreePath": "/wt/x",
                        "branch": "guardada", "children": []}])
    reg = Registry()
    sessions_cap.register(reg, ws, branch_of=lambda wt: None)   # git falló / worktree ausente
    out = await reg.dispatch("sessions.tree", {})
    assert out["sessions"][0]["branch"] == "guardada"       # se conserva


@pytest.mark.asyncio
async def test_branches_marks_occupied(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); sessions_cap.register(reg, ws)
    out = await reg.dispatch("sessions.branches", {"repoId": "repoA"})
    names = {b["name"]: b["occupied"] for b in out["branches"]}
    assert names["main"] is True


@pytest.mark.asyncio
async def test_branches_unknown_repo_raises(tmp_path):
    ws = _ws(tmp_path)
    reg = Registry(); sessions_cap.register(reg, ws)
    with pytest.raises(KeyError):
        await reg.dispatch("sessions.branches", {"repoId": "nope"})
