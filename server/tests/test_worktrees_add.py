import subprocess
from pathlib import Path
import pytest
from ide_server.worktrees import (
    add_worktree, remove_worktree, has_uncommitted_changes,
    branch_occupied, BranchOccupied,
)


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=path, check=True)
    return path


def test_rw_new_branch_creates_worktree_and_branch(tmp_path):
    repo = _repo(tmp_path / "r")
    wt = tmp_path / "wt-feat"
    add_worktree(repo, wt, "feature/a", access="rw", base="main")
    assert (wt / ".git").exists()
    assert branch_occupied(repo, "feature/a") is True


def test_rw_on_occupied_branch_raises(tmp_path):
    repo = _repo(tmp_path / "r")
    with pytest.raises(BranchOccupied):
        add_worktree(repo, tmp_path / "wt-main", "main", access="rw")


def test_ro_repeatable_on_same_branch(tmp_path):
    repo = _repo(tmp_path / "r")
    add_worktree(repo, tmp_path / "ro1", "main", access="ro")
    add_worktree(repo, tmp_path / "ro2", "main", access="ro")   # detached: repetible
    assert (tmp_path / "ro1" / ".git").exists()
    assert (tmp_path / "ro2" / ".git").exists()


def test_remove_worktree(tmp_path):
    repo = _repo(tmp_path / "r")
    wt = tmp_path / "wt"
    add_worktree(repo, wt, "feature/b", access="rw", base="main")
    remove_worktree(repo, wt)
    assert not wt.exists()


def test_has_uncommitted_changes(tmp_path):
    repo = _repo(tmp_path / "r")
    wt = tmp_path / "wt"
    add_worktree(repo, wt, "feature/c", access="rw", base="main")
    assert has_uncommitted_changes(wt) is False
    (wt / "dirty.txt").write_text("x")
    assert has_uncommitted_changes(wt) is True
