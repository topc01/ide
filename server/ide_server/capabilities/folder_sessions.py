from __future__ import annotations
import asyncio
import io
from pathlib import Path
from typing import Callable
from ide_server.config import ui_modules
from ide_server.plugins import Registry
from ide_server.pr_poller import PrPoller
from ide_server.repos_fs import require_session, rm_repo, worktree_path
from ide_server.scripts import list_scripts, script_argv, script_env
from ide_server.session_ops import create_session, delete_session, refresh_review
from ide_server.sessions_fs import list_sessions, read_toml, session_path, state_file, SessionError
from ide_server.supervisor import Supervisor
from ide_server.workspace import discover_repos


def register(registry: Registry, root: Path, manager, *, hooks, supervisor: Supervisor,
             poller: PrPoller) -> Callable[[], None]:

    def tree_payload() -> dict:
        snap = supervisor.snapshot()
        sessions = list_sessions(root)
        for s in sessions:
            p = snap.get(s["id"], {})
            s.update(process=p.get("process", "stopped"), terminalId=p.get("terminalId"),
                     launchError=p.get("launchError"))
            if s["kind"] == "review":
                s.update({"prState": None, "pollError": None, "lastOk": None,
                          **poller.derived.get(s["id"], {})})
        repos = discover_repos(root)
        return {"sessions": sessions, "workspaceRepos": repos,
                "scripts": {r["id"]: list_scripts(root, r["id"]) for r in repos}}

    def notify() -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(manager.broadcast("sessions.changed", tree_payload()))

    async def tree(_p: dict) -> dict:
        return tree_payload()

    async def new(p: dict) -> dict:
        res = create_session(root, p)
        process = supervisor.start(res["session"]["id"], resume=False)
        notify()
        return {**res, "process": process}

    async def open_(p: dict) -> dict:
        return {"process": supervisor.start(p["id"])}

    async def stop(p: dict) -> dict:
        supervisor.stop(p["id"])
        return {"ok": True}

    async def rm(p: dict) -> dict:
        delete_session(root, p["id"], force=bool(p.get("force")), stop=supervisor.stop)
        notify()
        return {"ok": True}

    async def script(p: dict) -> dict:
        require_session(root, p["id"])
        argv = script_argv(root, p["repo"], p["name"])
        tid = hooks.spawn(worktree_path(root, p["id"], p["repo"]), argv,
                          script_env(root, p["id"], p["repo"]), notify, session_id=p["id"])
        return {"terminalId": tid}

    async def doc(p: dict) -> dict:
        path = require_session(root, p["id"])
        name = state_file(read_toml(path / ".session.toml").get("kind"))
        if name is None:
            raise SessionError("no_doc", f"{p['id']} no tiene TICKET.md/REVIEW.md")
        f = path / name
        return {"name": name, "text": f.read_text(encoding="utf-8") if f.is_file() else ""}

    async def refresh(p: dict) -> dict:
        s = refresh_review(root, p["id"])
        await poller.poll_once()
        notify()
        return {"session": s}

    async def repo_rm(p: dict) -> dict:
        rm_repo(root, p["id"], p["repo"], force=bool(p.get("force")), out=io.StringIO())
        notify()
        return {"ok": True}

    async def ui_config(_p: dict) -> dict:
        return {"modules": ui_modules(root)}

    for channel, handler in {
        "sessions.tree": tree, "sessions.new": new, "sessions.open": open_,
        "sessions.stop": stop, "sessions.rm": rm, "sessions.script": script,
        "sessions.doc": doc, "sessions.refreshReview": refresh, "sessions.repoRm": repo_rm,
        "ui.config": ui_config,
    }.items():
        registry.register(channel, handler)
    return notify
