import subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import repos as repos_cap

def _git_repo(path: Path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=path, check=True)

@pytest.mark.asyncio
async def test_repos_list(tmp_path):
    (tmp_path / ".ide").mkdir()
    _git_repo(tmp_path / "repo-a")
    reg = Registry()
    repos_cap.register(reg, tmp_path)
    out = await reg.dispatch("repos.list", {})
    assert out["repos"][0]["name"] == "repo-a"

@pytest.mark.asyncio
async def test_repos_list_empty(tmp_path):
    (tmp_path / ".ide").mkdir()
    reg = Registry()
    repos_cap.register(reg, tmp_path)
    assert await reg.dispatch("repos.list", {}) == {"repos": []}
