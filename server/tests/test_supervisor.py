import pytest
from pathlib import Path
from ide_server.supervisor import Supervisor, build_argv, encode_project_dir, has_history
from ide_server.sessions_fs import create_session_dir, SessionError


class FakePty:
    def __init__(self):
        self.spawned, self.killed, self.exits, self.n = [], [], {}, 0

    fail_for: set = set()

    def spawn(self, cwd, argv, env, on_exit):
        if cwd.name in self.fail_for:
            raise RuntimeError(f"pty roto para {cwd.name}")
        self.n += 1
        tid = f"t{self.n}"
        self.spawned.append((tid, cwd, argv, env))
        self.exits[tid] = on_exit
        return tid

    def kill(self, tid):
        self.killed.append(tid)


def _mk(tmp_path, *sids, perm="analyze"):
    for sid in sids:
        create_session_dir(tmp_path, sid=sid, kind="ticket", permissions=perm, prompt=f"hacé {sid}")
    return tmp_path


def _sup(root, pty, **kw):
    return Supervisor(root, spawn=pty.spawn, kill=pty.kill, server_url="http://127.0.0.1:9",
                      home=root / "home", which=lambda c: "/usr/bin/" + c, **kw)


def test_argv_by_permissions(tmp_path):
    root = _mk(tmp_path, "a")
    create_session_dir(root, sid="f", kind="ticket", permissions="full", prompt="")
    create_session_dir(root, sid="d", kind="ticket", permissions="default", prompt="p")
    perm = root / ".ide" / "permissions"
    wt = lambda s: f"--add-dir={root / '.ide' / 'worktrees' / s}"
    assert build_argv(root, "a", command="claude", resume=False) == [
        "claude", "--settings", str(perm / "analyze.json"), wt("a"), "hacé a"]
    assert build_argv(root, "f", command="claude --verbose", resume=True) == [
        "claude", "--verbose", "--settings", str(perm / "full.json"),
        "--permission-mode", "bypassPermissions", wt("f"), "--continue"]
    assert build_argv(root, "d", command="claude", resume=False) == ["claude", wt("d"), "p"]


def test_argv_main_uses_main_profile_and_sees_sessions(tmp_path):     # C1 + I5
    create_session_dir(tmp_path, sid="m", kind="main", permissions="analyze", prompt="hola")
    argv = build_argv(tmp_path, "m", command="claude", resume=False)
    assert argv == ["claude", "--settings", str(tmp_path / ".ide" / "permissions" / "main.json"),
                    f"--add-dir={tmp_path / '.ide' / 'worktrees' / 'm'}",
                    f"--add-dir={tmp_path / '.ide' / 'sessions'}", "hola"]


def test_argv_prompt_starting_with_dash_is_not_a_flag(tmp_path):
    create_session_dir(tmp_path, sid="a", kind="ticket", permissions="default", prompt="--help me")
    assert build_argv(tmp_path, "a", command="claude", resume=False)[-1] == " --help me"


def test_history_detection(tmp_path):
    p = tmp_path / ".ide" / "sessions" / "a"
    assert encode_project_dir(Path("/x/.ide/s_1")) == "-x--ide-s-1"
    proj = tmp_path / "home" / ".claude" / "projects" / encode_project_dir(p.resolve())
    assert not has_history(p, tmp_path / "home")
    proj.mkdir(parents=True); (proj / "abc.jsonl").write_text("{}")
    assert has_history(p, tmp_path / "home")


def test_start_spawns_with_env_and_exit_marks_stopped(tmp_path):
    root, pty, changes = _mk(tmp_path, "a"), FakePty(), []
    sup = _sup(root, pty, on_change=lambda: changes.append(1))
    assert sup.start("a") == "running"
    tid, cwd, argv, env = pty.spawned[0]
    assert cwd == root / ".ide" / "sessions" / "a" and argv[-1] == "hacé a"
    assert env["IDE_SESSION_ID"] == "a" and env["IDE_URL"] == "http://127.0.0.1:9"
    assert env["IDE_WORKSPACE"] == str(root)
    assert sup.snapshot() == {"a": {"process": "running", "terminalId": tid, "launchError": None}}
    pty.exits[tid]()
    assert sup.state("a") == "stopped" and changes


def test_start_twice_is_idempotent_and_unknown_raises(tmp_path):
    root, pty = _mk(tmp_path, "a"), FakePty()
    sup = _sup(root, pty)
    sup.start("a"); sup.start("a")
    assert len(pty.spawned) == 1
    with pytest.raises(SessionError) as e:
        sup.start("nope")
    assert e.value.code == "unknown_session"


def test_queue_fifo_with_max_running(tmp_path):
    root, pty = _mk(tmp_path, "a", "b", "c"), FakePty()
    sup = _sup(root, pty, max_running=1)
    assert [sup.start(s) for s in ("a", "b", "c")] == ["running", "queued", "queued"]
    pty.exits["t1"]()
    assert sup.state("b") == "running" and sup.state("c") == "queued"
    sup.stop("c")
    assert sup.state("c") == "stopped"
    sup.stop("b")
    assert pty.killed == ["t2"] and sup.state("b") == "stopped"


def test_stale_exit_callback_ignored_after_restart(tmp_path):
    root, pty = _mk(tmp_path, "a"), FakePty()
    sup = _sup(root, pty)
    sup.start("a"); sup.stop("a"); sup.start("a")
    pty.exits["t1"]()                              # salida tardía del proceso viejo
    assert sup.state("a") == "running"


def test_missing_claude_binary(tmp_path):
    root, pty = _mk(tmp_path, "a"), FakePty()
    sup = Supervisor(root, spawn=pty.spawn, kill=pty.kill, server_url="u", which=lambda c: None)
    with pytest.raises(SessionError) as e:
        sup.start("a")
    assert e.value.code == "claude_missing" and pty.spawned == []


def test_queued_launch_error_is_reported(tmp_path):
    root, pty = _mk(tmp_path, "a", "b"), FakePty()
    found = {"ok": True}
    sup = Supervisor(root, spawn=pty.spawn, kill=pty.kill, server_url="u", max_running=1,
                     home=root / "home", which=lambda c: "/x" if found["ok"] else None)
    sup.start("a"); sup.start("b")
    found["ok"] = False
    pty.exits["t1"]()
    snap = sup.snapshot()["b"]
    assert snap["process"] == "stopped" and snap["terminalId"] is None
    assert "claude" in snap["launchError"]


def test_drain_survives_non_session_error_and_keeps_queue_moving(tmp_path):
    root, pty = _mk(tmp_path, "a", "b", "c"), FakePty()
    sup = _sup(root, pty, max_running=1)
    sup.start("a"); sup.start("b"); sup.start("c")
    pty.fail_for = {"b"}
    pty.exits["t1"]()
    snap = sup.snapshot()
    assert snap["b"]["process"] == "stopped" and snap["b"]["terminalId"] is None
    assert "pty roto" in snap["b"]["launchError"]
    assert sup.state("c") == "running" and snap["c"]["terminalId"] == "t2"


def test_stop_clears_stale_launch_error(tmp_path):
    root, pty = _mk(tmp_path, "a", "b"), FakePty()
    sup = _sup(root, pty, max_running=1)
    sup.start("a"); sup.start("b")
    pty.fail_for = {"b"}
    pty.exits["t1"]()
    assert sup.snapshot()["b"]["launchError"]
    sup.stop("b")
    assert "b" not in sup.snapshot()
