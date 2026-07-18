import json, sqlite3, subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import graphite as graphite_cap


def _seed(tmp_path: Path) -> tuple[Path, str, str]:
    (tmp_path / ".ide").mkdir()
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "a.py").write_text("uno\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "base"], cwd=repo, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "-b", "feat-a"], cwd=repo, check=True)
    (repo / "a.py").write_text("uno\ndos\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "agrega dos"], cwd=repo, check=True)
    tip = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    db = repo / ".git" / ".graphite_metadata.db"
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "branch_metadata" ("branch_name" text primary key, '
                '"parent_branch_name" text, "parent_branch_revision" text, "branch_revision" text)')
    con.executemany('INSERT INTO branch_metadata VALUES (?,?,?,?)',
                    [("main", None, None, base), ("feat-a", "main", base, tip)])
    con.commit(); con.close()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps(
        {"sessions": [{"id": "s1", "name": "S1", "repoId": "repoA", "branch": "feat-a",
                       "worktreePath": str(repo), "children": []}]}))
    return tmp_path, base, tip


@pytest.mark.asyncio
async def test_graphite_stack_for_session(tmp_path):
    root, base, tip = _seed(tmp_path)
    reg = Registry(); graphite_cap.register(reg, root)
    out = await reg.dispatch("graphite.stack", {"sessionId": "s1"})
    names = [b["name"] for b in out["stack"]]
    assert names == ["main", "feat-a"]
    assert out["current"] == "feat-a"
    assert next(b for b in out["stack"] if b["name"] == "feat-a")["current"] is True


@pytest.mark.asyncio
async def test_graphite_branch_commits_and_files(tmp_path):
    root, base, tip = _seed(tmp_path)
    reg = Registry(); graphite_cap.register(reg, root)
    out = await reg.dispatch("graphite.branch", {"sessionId": "s1", "branch": "feat-a"})
    assert out["commits"][0]["message"] == "agrega dos"
    assert any(f["path"] == "a.py" for f in out["commits"][0]["files"])


@pytest.mark.asyncio
async def test_graphite_stack_non_graphite_raises(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps({"sessions": []}))
    (tmp_path / "repoB").mkdir()
    reg = Registry(); graphite_cap.register(reg, root=tmp_path)
    from ide_server.graphite import GraphiteError
    with pytest.raises(GraphiteError):
        await reg.dispatch("graphite.stack", {"repoId": "repoB"})
