# server/tests/test_repos_fs.py
import os, subprocess
import pytest
from ide_server.repos_fs import add_repo, rm_repo, worktree_path, allocate_port
from ide_server.sessions_fs import create_session_dir, read_session, session_path, SessionError
from ide_server.worktrees import BranchOccupied


def _git(*a, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True,
                   capture_output=True)


def _ws(tmp_path):
    for name in ("repo-a", "repo-b"):
        r = tmp_path / name; r.mkdir()
        _git("init", "-q", "-b", "main", cwd=r); _git("commit", "-q", "--allow-empty", "-m", "x", cwd=r)
    for sid in ("t1", "t2"):
        create_session_dir(tmp_path, sid=sid, kind="ticket", permissions="analyze", prompt="")
    return tmp_path


def test_add_repo_creates_worktree_symlink_and_port(tmp_path):
    root = _ws(tmp_path)
    info = add_repo(root, "t1", "repo-a")
    wt = worktree_path(root, "t1", "repo-a")
    link = session_path(root, "t1") / "repo-a"
    assert info == {"name": "repo-a", "branch": "t1", "path": str(wt), "port": 8100}
    assert link.is_symlink() and os.readlink(link) == "../../worktrees/t1/repo-a"
    assert read_session(root, "t1")["repos"][0]["branch"] == "t1"


def test_ports_are_distinct_and_reused_after_rm(tmp_path):        # Review Focus (puertos)
    root = _ws(tmp_path)
    assert add_repo(root, "t1", "repo-a")["port"] == 8100
    assert add_repo(root, "t2", "repo-a")["port"] == 8110
    rm_repo(root, "t1", "repo-a")
    assert allocate_port(root) == 8100


def test_add_repo_errors(tmp_path):
    root = _ws(tmp_path)
    with pytest.raises(SessionError) as e:
        add_repo(root, "t1", "nope")
    assert e.value.code == "unknown_repo"
    with pytest.raises(SessionError) as e:
        add_repo(root, "zz", "repo-a")
    assert e.value.code == "unknown_session"
    add_repo(root, "t1", "repo-a")
    with pytest.raises(SessionError) as e:
        add_repo(root, "t1", "repo-a")
    assert e.value.code == "repo_exists"
    with pytest.raises(BranchOccupied):
        add_repo(root, "t2", "repo-a", branch="t1")
    assert not (session_path(root, "t2") / "repo-a").exists()


def test_add_repo_detached(tmp_path):
    root = _ws(tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root / "repo-a",
                         capture_output=True, text=True).stdout.strip()
    info = add_repo(root, "t1", "repo-a", detach_at=sha)
    assert info["branch"] is None
    assert read_session(root, "t1")["repos"][0]["branch"] == "HEAD"


def test_rm_repo_refuses_dirty_then_force(tmp_path):
    root = _ws(tmp_path)
    add_repo(root, "t1", "repo-a")
    (worktree_path(root, "t1", "repo-a") / "x.txt").write_text("sucio")
    with pytest.raises(SessionError) as e:
        rm_repo(root, "t1", "repo-a")
    assert e.value.code == "uncommitted_changes"
    rm_repo(root, "t1", "repo-a", force=True)
    assert not (session_path(root, "t1") / "repo-a").exists()
    assert not worktree_path(root, "t1", "repo-a").exists()
    assert read_session(root, "t1")["repos"] == []


def test_rm_repo_with_missing_worktree_prunes(tmp_path):
    import shutil
    root = _ws(tmp_path)
    add_repo(root, "t1", "repo-a")
    shutil.rmtree(worktree_path(root, "t1", "repo-a"))
    rm_repo(root, "t1", "repo-a")
    assert not (session_path(root, "t1") / "repo-a").is_symlink()


def test_used_ports_skips_malformed_ports(tmp_path):
    root = _ws(tmp_path)
    (session_path(root, "t1") / ".session.toml").write_text(
        'kind = "ticket"\npermissions = "analyze"\nports = ["x"]\n')
    (session_path(root, "t2") / ".session.toml").write_text(
        'kind = "ticket"\npermissions = "analyze"\n[ports]\nrepo-a = 8100\n')
    assert allocate_port(root) == 8110


def test_concurrent_add_repo_gets_distinct_ports(tmp_path, monkeypatch):     # I4
    import threading, time
    from ide_server import repos_fs
    root = _ws(tmp_path)
    real = repos_fs.allocate_port

    def slow(r):
        port = real(r); time.sleep(0.2); return port      # ventana de carrera

    monkeypatch.setattr(repos_fs, "allocate_port", slow)
    infos = {}
    ts = [threading.Thread(target=lambda s=s: infos.__setitem__(s, add_repo(root, s, "repo-a")))
          for s in ("t1", "t2")]
    for t in ts: t.start()
    for t in ts: t.join()
    assert sorted(i["port"] for i in infos.values()) == [8100, 8110]
