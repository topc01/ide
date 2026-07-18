import sqlite3
import subprocess
from pathlib import Path
import pytest
from ide_server.graphite import read_stack, branch_commits, commit_files, GraphiteError


def _gitdir(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    return repo


def _seed_db(repo: Path, rows: list[tuple]) -> None:
    db = repo / ".git" / ".graphite_metadata.db"
    con = sqlite3.connect(db)
    con.execute(
        'CREATE TABLE "branch_metadata" ("branch_name" text not null primary key, '
        '"parent_branch_name" text, "parent_branch_revision" text, "branch_revision" text)')
    con.executemany(
        'INSERT INTO branch_metadata '
        '("branch_name","parent_branch_name","parent_branch_revision","branch_revision") '
        'VALUES (?,?,?,?)', rows)
    con.commit(); con.close()


def test_read_stack_returns_normalized_rows(tmp_path):
    repo = _gitdir(tmp_path)
    _seed_db(repo, [
        ("main", None, None, "r0"),
        ("feat-a", "main", "r0", "r1"),
    ])
    rows = {r["name"]: r for r in read_stack(repo)}
    assert rows["main"] == {"name": "main", "parent": None, "parentRevision": None, "revision": "r0"}
    assert rows["feat-a"]["parent"] == "main" and rows["feat-a"]["revision"] == "r1"


def test_read_stack_missing_db_raises(tmp_path):
    with pytest.raises(GraphiteError):
        read_stack(_gitdir(tmp_path))


def _real_repo(tmp_path: Path) -> tuple[Path, str, str]:
    r = tmp_path / "rr"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    (r / "a.py").write_text("uno\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "base"], cwd=r, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True).stdout.strip()
    (r / "a.py").write_text("uno\ndos\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "agrega dos"], cwd=r, check=True)
    tip = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True).stdout.strip()
    return r, base, tip


def test_branch_commits_and_files(tmp_path):
    r, base, tip = _real_repo(tmp_path)
    commits = branch_commits(r, tip, base)
    assert len(commits) == 1 and commits[0]["message"] == "agrega dos"
    assert branch_commits(r, tip, None) == []      # trunk → sin commits
    files = commit_files(r, tip)
    assert any(f["path"] == "a.py" and f["added"] == 1 for f in files)
