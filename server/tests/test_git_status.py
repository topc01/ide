import subprocess
from pathlib import Path
import pytest
from ide_server.git import repo_status, file_diff_full, GitError


def _repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    (r / "a.py").write_text("uno\ndos\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], cwd=r, check=True)
    (r / "a.py").write_text("uno\nDOS\ntres\n")     # modificado
    (r / "b.txt").write_text("nuevo\n")             # untracked
    return r


def test_repo_status_lists_modified_and_untracked(tmp_path):
    r = _repo(tmp_path)
    st = repo_status(r)
    assert st["branch"] == "main"
    by = {f["path"]: f for f in st["files"]}
    assert by["a.py"]["status"] == "M" and by["a.py"]["added"] >= 1
    assert by["b.txt"]["status"] == "?" and by["b.txt"]["added"] == 1
    assert st["totalAdded"] >= 2


def test_file_diff_full_modified_has_add_and_del(tmp_path):
    r = _repo(tmp_path)
    lines = file_diff_full(r, "a.py", "M")
    types = {l["type"] for l in lines}
    assert "add" in types and "del" in types
    assert any(l["type"] == "add" and l["text"] == "DOS" for l in lines)


def test_file_diff_full_untracked_is_all_add(tmp_path):
    r = _repo(tmp_path)
    lines = file_diff_full(r, "b.txt", "?")
    assert lines[0] == {"type": "add", "text": "nuevo"}


def test_repo_status_non_git_raises(tmp_path):
    with pytest.raises(GitError):
        repo_status(tmp_path)
