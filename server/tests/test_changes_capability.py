import json, subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import changes as changes_cap


def _seed(tmp_path: Path) -> Path:
    (tmp_path / ".ide").mkdir()
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "a.py").write_text("uno\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (repo / "a.py").write_text("uno\ndos\n")
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps(
        {"sessions": [{"id": "s1", "name": "S1", "repoId": "repoA",
                       "worktreePath": str(repo), "children": []}]}))
    return tmp_path


@pytest.mark.asyncio
async def test_changes_list_for_session(tmp_path):
    root = _seed(tmp_path)
    reg = Registry(); changes_cap.register(reg, root)
    out = await reg.dispatch("changes.list", {"sessionId": "s1"})
    assert out["status"]["branch"] == "main"
    assert any(f["path"] == "a.py" for f in out["status"]["files"])


@pytest.mark.asyncio
async def test_changes_diff_for_session(tmp_path):
    root = _seed(tmp_path)
    reg = Registry(); changes_cap.register(reg, root)
    out = await reg.dispatch("changes.diff", {"sessionId": "s1", "path": "a.py", "status": "M"})
    assert any(l["type"] == "add" and l["text"] == "dos" for l in out["lines"])


@pytest.mark.asyncio
async def test_changes_list_non_git_root_raises(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps({"sessions": []}))
    reg = Registry(); changes_cap.register(reg, tmp_path)
    from ide_server.git import GitError
    with pytest.raises(GitError):
        await reg.dispatch("changes.list", {})
