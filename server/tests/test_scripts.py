# server/tests/test_scripts.py
import io, os, subprocess
import pytest
from ide_server.scripts import list_scripts, script_env, run_script, script_argv
from ide_server.repos_fs import add_repo, rm_repo, worktree_path
from ide_server.sessions_fs import create_session_dir, read_session, SessionError


def _git(*a, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True,
                   capture_output=True)


def _ws(tmp_path):
    r = tmp_path / "repo-a"; r.mkdir()
    _git("init", "-q", "-b", "main", cwd=r); _git("commit", "-q", "--allow-empty", "-m", "x", cwd=r)
    create_session_dir(tmp_path, sid="t1", kind="ticket", permissions="analyze", prompt="")
    (tmp_path / ".ide" / "scripts" / "repo-a").mkdir(parents=True)
    return tmp_path


def _script(root, name, body, executable=True):
    p = root / ".ide" / "scripts" / "repo-a" / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    if executable:
        p.chmod(0o755)
    return p


def test_list_scripts_flags_non_executable(tmp_path):
    root = _ws(tmp_path)
    _script(root, "run", "echo run"); _script(root, "test", "echo t", executable=False)
    assert list_scripts(root, "repo-a") == [{"name": "run", "executable": True},
                                            {"name": "test", "executable": False}]
    with pytest.raises(SessionError) as e:
        script_argv(root, "repo-a", "test")
    assert e.value.code == "script_not_executable" and "chmod +x" in str(e.value)
    with pytest.raises(SessionError) as e:
        script_argv(root, "repo-a", "nope")
    assert e.value.code == "script_not_found"


def test_setup_runs_on_add_with_env_in_worktree(tmp_path):
    root = _ws(tmp_path)
    _script(root, "setup", 'echo "$IDE_SESSION_ID $IDE_REPO $IDE_PORT $IDE_ROOT_REPO" > env.txt; pwd')
    out = io.StringIO()
    add_repo(root, "t1", "repo-a", out=out)
    wt = worktree_path(root, "t1", "repo-a")
    assert (wt / "env.txt").read_text().split() == ["t1", "repo-a", "8100", str(root / "repo-a")]
    assert str(wt.resolve()) in out.getvalue()
    assert read_session(root, "t1")["repos"][0]["setup"] == "ok"


def test_setup_failure_keeps_worktree_and_marks(tmp_path):
    root = _ws(tmp_path)
    _script(root, "setup", "echo boom; exit 3")
    with pytest.raises(SessionError) as e:
        add_repo(root, "t1", "repo-a", out=io.StringIO())
    assert e.value.code == "setup_failed" and "exit 3" in str(e.value)
    assert worktree_path(root, "t1", "repo-a").exists()
    assert read_session(root, "t1")["repos"][0]["setup"] == "failed"
    _script(root, "setup", "true")
    assert run_script(root, "t1", "repo-a", "setup", out=io.StringIO()) == 0
    assert read_session(root, "t1")["repos"][0]["setup"] == "ok"


def test_archive_runs_on_rm_and_blocks_on_failure(tmp_path):
    root = _ws(tmp_path)
    add_repo(root, "t1", "repo-a", out=io.StringIO())
    marker = tmp_path / "archived"
    _script(root, "archive", f"touch {marker}; exit 1")
    with pytest.raises(SessionError) as e:
        rm_repo(root, "t1", "repo-a", out=io.StringIO())
    assert e.value.code == "archive_failed" and marker.exists()
    rm_repo(root, "t1", "repo-a", force=True, out=io.StringIO())
    assert not worktree_path(root, "t1", "repo-a").exists()


def test_script_env_without_port(tmp_path):
    root = _ws(tmp_path)
    env = script_env(root, "t1", "repo-a", base_env={"PATH": "/bin"})
    assert env["IDE_WORKSPACE"] == str(root) and "IDE_PORT" not in env and env["PATH"] == "/bin"
