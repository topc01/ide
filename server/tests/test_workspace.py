import subprocess
from pathlib import Path
from ide_server.workspace import find_workspace_root, discover_repos

def _git_repo(path: Path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=path, check=True)

def test_find_root_walks_up(tmp_path):
    (tmp_path / ".ide").mkdir()
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert find_workspace_root(deep) == tmp_path

def test_find_root_none_when_absent(tmp_path):
    assert find_workspace_root(tmp_path) is None

def test_discover_repos(tmp_path):
    (tmp_path / ".ide").mkdir()
    _git_repo(tmp_path / "repo-a")
    _git_repo(tmp_path / "repo-b")
    repos = discover_repos(tmp_path)
    names = sorted(r["name"] for r in repos)
    assert names == ["repo-a", "repo-b"]
    assert all(r["branch"] == "main" for r in repos)

def test_discover_repos_invalid_git_is_unknown(tmp_path):
    (tmp_path / ".ide").mkdir()
    broken = tmp_path / "broken"
    (broken / ".git").mkdir(parents=True)
    repos = discover_repos(tmp_path)
    assert repos[0]["name"] == "broken"
    assert repos[0]["branch"] == "unknown"
