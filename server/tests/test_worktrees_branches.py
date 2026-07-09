import subprocess
from pathlib import Path
import pytest
from ide_server.worktrees import list_branches, branch_occupied


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=path, check=True)
    return path


def test_list_branches_marks_main_occupied(tmp_path):
    repo = _repo(tmp_path / "r")
    subprocess.run(["git", "-C", str(repo), "branch", "feature/x"], check=True)
    branches = {b["name"]: b["occupied"] for b in list_branches(repo)}
    assert set(branches) == {"main", "feature/x"}
    assert branches["main"] is True            # main está checkouteada en el repo principal
    assert branches["feature/x"] is False


def test_branch_occupied_true_for_checked_out(tmp_path):
    repo = _repo(tmp_path / "r")
    assert branch_occupied(repo, "main") is True
    assert branch_occupied(repo, "nope") is False


def test_slash_branch_occupied_when_checked_out(tmp_path):
    repo = _repo(tmp_path / "r")
    subprocess.run(["git", "-C", str(repo), "branch", "feature/x"], check=True)
    wt = tmp_path / "wt-fx"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", str(wt), "feature/x"], check=True)
    assert branch_occupied(repo, "feature/x") is True
    marks = {b["name"]: b["occupied"] for b in list_branches(repo)}
    assert marks["feature/x"] is True
