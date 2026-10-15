# server/tests/test_folder_sessions_capability.py
import asyncio, io, subprocess
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import folder_sessions as cap
from ide_server.supervisor import Supervisor
from ide_server.pr_poller import PrPoller
from ide_server.sessions_fs import seed_workspace, session_path
from ide_server.repos_fs import add_repo, worktree_path


class Rec:
    def __init__(self): self.events = []
    async def broadcast(self, channel, payload): self.events.append((channel, payload))


class FakeHooks:
    def __init__(self):
        self.spawned, self.killed, self.n, self.outputs, self.kill_threads = [], [], 0, {}, []
    def spawn(self, cwd, argv, env, on_exit, session_id=None, on_output=None, on_input=None):
        self.n += 1; self.spawned.append((cwd, argv, env)); self.outputs[f"t{self.n}"] = on_output
        return f"t{self.n}"
    def kill(self, tid):
        import threading
        self.killed.append(tid); self.kill_threads.append(threading.current_thread())


async def _until(cond, tries=200):
    for _ in range(tries):
        if cond():
            return True
        await asyncio.sleep(0.01)
    return False


def _ws(tmp_path):
    r = tmp_path / "repo-a"; r.mkdir()
    for a in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=r, check=True)
    seed_workspace(tmp_path)
    s = tmp_path / ".ide" / "scripts" / "repo-a"; s.mkdir(parents=True, exist_ok=True)
    (s / "run").write_text("#!/bin/sh\necho corriendo $IDE_PORT\n"); (s / "run").chmod(0o755)
    return tmp_path


def _reg(root):
    reg, rec, hooks = Registry(), Rec(), FakeHooks()
    box = {"fn": lambda: None}
    sup = Supervisor(root, spawn=hooks.spawn, kill=hooks.kill, server_url="u",
                     home=root / "home", which=lambda c: "/x", on_change=lambda: box["fn"]())
    poller = PrPoller(root, interval=0)
    box["fn"] = cap.register(reg, root, rec, hooks=hooks, supervisor=sup, poller=poller)
    return reg, rec, hooks, sup


@pytest.mark.asyncio
async def test_new_starts_and_tree_reports_process(tmp_path):
    reg, rec, hooks, _ = _reg(_ws(tmp_path))
    out = await reg.dispatch("sessions.new", {"id": "FIN-1", "template": "ticket",
                             "vars": {"title": "T", "notion_url": "n", "body": "b"}})
    assert out["session"]["id"] == "fin-1" and out["process"] == "running"
    tree = await reg.dispatch("sessions.tree", {})
    s = tree["sessions"][0]
    assert s["process"] == "running" and s["terminalId"] == "t1"
    assert tree["workspaceRepos"][0]["id"] == "repo-a"
    assert tree["scripts"]["repo-a"] == [{"name": "run", "executable": True}]
    assert await _until(lambda: any(c == "sessions.changed" for c, _ in rec.events))


@pytest.mark.asyncio
async def test_stop_open_rm(tmp_path):
    root = _ws(tmp_path)
    reg, _, hooks, sup = _reg(root)
    await reg.dispatch("sessions.new", {"id": "a", "prompt": "p"})
    await reg.dispatch("sessions.stop", {"id": "a"})
    assert hooks.killed == ["t1"] and sup.state("a") == "stopped"
    assert (await reg.dispatch("sessions.open", {"id": "a"}))["process"] == "running"
    add_repo(root, "a", "repo-a", out=io.StringIO())
    (worktree_path(root, "a", "repo-a") / "x").write_text("sucio")
    from ide_server.sessions_fs import SessionError
    with pytest.raises(SessionError):
        await reg.dispatch("sessions.rm", {"id": "a"})
    assert sup.state("a") == "running"                     # Review Focus 5: no tocó nada
    await reg.dispatch("sessions.rm", {"id": "a", "force": True})
    assert sup.state("a") == "stopped" and not session_path(root, "a").exists()


@pytest.mark.asyncio
async def test_script_spawns_in_worktree_with_env(tmp_path):
    root = _ws(tmp_path)
    reg, _, hooks, _ = _reg(root)
    await reg.dispatch("sessions.new", {"id": "a", "prompt": ""})
    add_repo(root, "a", "repo-a", out=io.StringIO())
    out = await reg.dispatch("sessions.script", {"id": "a", "repo": "repo-a", "name": "run"})
    cwd, argv, env = hooks.spawned[-1]
    assert out["terminalId"] == "t2" and cwd == worktree_path(root, "a", "repo-a")
    assert argv[0].endswith("/run") and env["IDE_PORT"] == "8100"


@pytest.mark.asyncio
async def test_repo_rm_missing(tmp_path):
    import shutil
    root = _ws(tmp_path)
    reg, *_ = _reg(root)
    await reg.dispatch("sessions.new", {"id": "a", "prompt": ""})
    add_repo(root, "a", "repo-a", out=io.StringIO())
    shutil.rmtree(worktree_path(root, "a", "repo-a"))
    tree = await reg.dispatch("sessions.tree", {})
    assert tree["sessions"][0]["repos"][0]["state"] == "missing"
    await reg.dispatch("sessions.repoRm", {"id": "a", "repo": "repo-a"})
    assert (await reg.dispatch("sessions.tree", {}))["sessions"][0]["repos"] == []


@pytest.mark.asyncio
async def test_doc_and_ui_config(tmp_path):
    reg, *_ = _reg(_ws(tmp_path))
    await reg.dispatch("sessions.new", {"id": "a", "title": "Hola"})
    doc = await reg.dispatch("sessions.doc", {"id": "a"})
    assert doc["name"] == "TICKET.md" and "status: analyzing" in doc["text"]
    assert (await reg.dispatch("ui.config", {}))["modules"] == ["sessions", "terminal"]


@pytest.mark.asyncio
async def test_prompts_list(tmp_path):
    reg, *_ = _reg(_ws(tmp_path))
    names = [p["name"] for p in (await reg.dispatch("prompts.list", {}))["prompts"]]
    assert names == ["tickets-y-prs"]


@pytest.mark.asyncio
async def test_tree_reports_trust_attention(tmp_path):                       # C2
    reg, rec, hooks, _ = _reg(_ws(tmp_path))
    await reg.dispatch("sessions.new", {"id": "a", "prompt": "p"})
    assert (await reg.dispatch("sessions.tree", {}))["sessions"][0]["attention"] is None
    rec.events.clear()
    hooks.outputs["t1"](b"Do you trust the files in this folder?")
    assert (await reg.dispatch("sessions.tree", {}))["sessions"][0]["attention"] == "trust"
    assert await _until(lambda: any(c == "sessions.changed" and p["sessions"][0]["attention"]
                                    for c, p in rec.events))


@pytest.mark.asyncio
async def test_blocking_work_runs_off_the_event_loop(tmp_path, monkeypatch):  # I3
    import threading
    root = _ws(tmp_path)
    reg, _, hooks, _ = _reg(root)
    main, seen = threading.current_thread(), {}

    def spy(name, fn):
        def wrapper(*a, **k):
            seen[name] = threading.current_thread()
            return fn(*a, **k)
        monkeypatch.setattr(cap, name, wrapper)

    for name in ("create_session", "list_sessions", "discover_repos", "list_scripts",
                 "remove_session", "check_delete"):
        spy(name, getattr(cap, name))
    await reg.dispatch("sessions.new", {"id": "a", "prompt": "p"})
    await reg.dispatch("sessions.tree", {})
    await reg.dispatch("sessions.rm", {"id": "a"})
    assert set(seen) == {"create_session", "list_sessions", "discover_repos", "list_scripts",
                         "remove_session", "check_delete"}
    assert all(t is not main for t in seen.values())
    assert hooks.kill_threads == [main]                     # el supervisor sigue en el loop


@pytest.mark.asyncio
async def test_script_rejects_non_plain_names(tmp_path):
    from ide_server.sessions_fs import SessionError
    root = _ws(tmp_path)
    reg, *_ = _reg(root)
    await reg.dispatch("sessions.new", {"id": "a", "prompt": ""})
    add_repo(root, "a", "repo-a", out=io.StringIO())
    for bad in ("../run", "x/run", ".."):
        with pytest.raises(SessionError) as e:
            await reg.dispatch("sessions.script", {"id": "a", "repo": "repo-a", "name": bad})
        assert e.value.code == "invalid_name"


@pytest.mark.asyncio
async def test_new_dry_run_and_if_missing_do_not_spawn(tmp_path):
    reg, _, hooks, sup = _reg(_ws(tmp_path))
    dry = await reg.dispatch("sessions.new", {"id": "a", "prompt": "p", "dry_run": True})
    assert dry["dryRun"] is True and dry["process"] == "stopped" and hooks.spawned == []
    await reg.dispatch("sessions.new", {"id": "a", "prompt": "p"})
    assert len(hooks.spawned) == 1
    sup.stop("a")
    again = await reg.dispatch("sessions.new", {"id": "a", "prompt": "p", "if_missing": True})
    assert again["existed"] is True and again["process"] == "stopped"
    assert len(hooks.spawned) == 1
