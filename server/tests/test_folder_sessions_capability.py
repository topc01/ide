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
    def __init__(self): self.spawned, self.killed, self.n = [], [], 0
    def spawn(self, cwd, argv, env, on_exit, session_id=None):
        self.n += 1; self.spawned.append((cwd, argv, env)); return f"t{self.n}"
    def kill(self, tid): self.killed.append(tid)


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
    sup = Supervisor(root, spawn=hooks.spawn, kill=hooks.kill, server_url="u",
                     home=root / "home", which=lambda c: "/x")
    poller = PrPoller(root, interval=0)
    notify = cap.register(reg, root, rec, hooks=hooks, supervisor=sup, poller=poller)
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
    await asyncio.sleep(0)
    assert any(c == "sessions.changed" for c, _ in rec.events)


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
