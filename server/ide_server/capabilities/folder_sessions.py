from __future__ import annotations
import asyncio
import io
import logging
from pathlib import Path
from typing import Callable
from ide_server.claude_usage import LimitsPoller, session_context
from ide_server.config import ui_modules
from ide_server.gh_reviews import GithubReviews
from ide_server.plugins import Registry
from ide_server.pr_poller import PrPoller
from ide_server.prompts import list_prompts, load_prompt
from ide_server.repos_fs import require_session, rm_repo, worktree_path
from ide_server.scripts import list_scripts, script_argv, script_env
from ide_server.session_ops import (
    archive_session, check_delete, create_session, parse_pr_url, refresh_review, remove_session,
)
from ide_server.sessions_fs import (
    list_sessions, normalize_id, read_session, read_toml, render_template, require_plain_name,
    session_path, state_file, SessionError,
)
from ide_server.supervisor import Supervisor
from ide_server.workspace import discover_repos

log = logging.getLogger(__name__)


def register(registry: Registry, root: Path, manager, *, hooks, supervisor: Supervisor,
             poller: PrPoller, gh_reviews: GithubReviews | None = None,
             limits: LimitsPoller | None = None) -> Callable[[], None]:

    def build_tree(snap: dict, derived: dict) -> dict:
        """Lectura de disco + git: corre en un thread (no bloquea el loop)."""
        sessions = list_sessions(root)
        for s in sessions:
            p = snap.get(s["id"], {})
            s.update(process=p.get("process", "stopped"), terminalId=p.get("terminalId"),
                     launchError=p.get("launchError"), attention=p.get("attention"))
            if s["kind"] == "review":
                s.update({"prState": None, "pollError": None, "lastOk": None,
                          **derived.get(s["id"], {})})
        repos = discover_repos(root)
        return {"sessions": sessions, "workspaceRepos": repos,
                "scripts": {r["id"]: list_scripts(root, r["id"]) for r in repos}}

    async def tree_payload() -> dict:
        # el estado en memoria se copia en el loop; el disco se lee en un thread
        snap, derived = supervisor.snapshot(), dict(poller.derived)
        return await asyncio.to_thread(build_tree, snap, derived)

    pending = {"dirty": False, "task": None}

    async def broadcast_loop() -> None:
        while pending["dirty"]:                 # coalesce: el último broadcast es el más nuevo
            pending["dirty"] = False
            try:
                await manager.broadcast("sessions.changed", await tree_payload())
            except Exception:  # noqa: BLE001 — se loguea; el próximo cambio reintenta
                log.exception("no se pudo emitir sessions.changed")
        pending["task"] = None

    def notify() -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        pending["dirty"] = True
        if pending["task"] is None:
            pending["task"] = loop.create_task(broadcast_loop())

    async def tree(_p: dict) -> dict:
        return await tree_payload()

    async def new(p: dict) -> dict:
        res = await asyncio.to_thread(create_session, root, p)
        if res.get("dryRun") or res.get("existed"):
            return {**res, "process": supervisor.state(res["session"]["id"])}
        process = supervisor.start(res["session"]["id"], resume=False)
        notify()
        return {**res, "process": process}

    async def open_(p: dict) -> dict:
        return {"process": supervisor.start(p["id"])}

    async def stop(p: dict) -> dict:
        supervisor.stop(p["id"])
        return {"ok": True}

    async def rm(p: dict) -> dict:
        force = bool(p.get("force"))
        await asyncio.to_thread(check_delete, root, p["id"], force=force)
        supervisor.stop(p["id"])                # en el loop: el supervisor no es thread-safe
        await asyncio.to_thread(remove_session, root, p["id"], force=force)
        notify()
        return {"ok": True}

    async def archive(p: dict) -> dict:
        require_session(root, p["id"])
        supervisor.stop(p["id"])                # en el loop: el supervisor no es thread-safe
        await asyncio.to_thread(archive_session, root, p["id"], force=bool(p.get("force")))
        notify()
        return {"ok": True}

    async def script(p: dict) -> dict:
        require_session(root, p["id"])
        require_plain_name(p["repo"], "repo")
        if not worktree_path(root, p["id"], p["repo"]).exists():
            raise SessionError("unknown_repo", f"{p['repo']} no está en la sesión {p['id']}")
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
        s = await asyncio.to_thread(refresh_review, root, p["id"])
        await poller.poll_once()
        notify()
        return {"session": s}

    async def repo_rm(p: dict) -> dict:
        await asyncio.to_thread(rm_repo, root, p["id"], p["repo"], force=bool(p.get("force")),
                                out=io.StringIO())
        notify()
        return {"ok": True}

    async def ui_config(_p: dict) -> dict:
        return {"modules": ui_modules(root)}

    async def prompts(_p: dict) -> dict:
        return {"prompts": await asyncio.to_thread(list_prompts, root)}

    async def github(_p: dict) -> dict:
        return gh_reviews.state if gh_reviews else {"pending": [], "changesRequested": [], "me": None,
                                                    "reviewers": [], "reviewersTruncated": False,
                                                    "members": [], "selected": None, "mine": {}, "stacks": {},
                                                    "error": "polling de GitHub desactivado",
                                                    "lastOk": None, "orgs": []}

    async def set_reviewers(p: dict) -> dict:
        if gh_reviews is None:
            raise SessionError("github_off", "polling de GitHub desactivado")
        logins = p["logins"]
        if not isinstance(logins, list):
            raise SessionError("bad_request", "logins debe ser una lista")
        await gh_reviews.set_selection(logins)
        return gh_reviews.state

    async def review_start(p: dict) -> dict:
        """Botón de revisión: manda `.ide/prompts/review-pr.md` a la sesión del PR (la crea si falta)."""
        url = p["url"]
        repo, number = parse_pr_url(url)
        sid = normalize_id(f"pr-{repo}-{number}")
        if not (session_path(root, sid) / ".session.toml").is_file():
            await asyncio.to_thread(create_session, root,
                                          {"review": url, "prompt_file": "review-pr"})
            process = supervisor.start(sid, resume=False)
            notify()
            return {"id": sid, "created": True, "process": process}
        s = await asyncio.to_thread(read_session, root, sid)
        text = render_template(await asyncio.to_thread(load_prompt, root, "review-pr"), {
            "id": sid, "pr_url": url, "repo": repo, "title": s.get("title") or "",
            "author": s["meta"].get("author", "")})
        state = supervisor.state(sid)
        if state == "queued":
            raise SessionError("queued", f"{sid} está en cola: espera a que arranque")
        if state == "running":
            supervisor.send(sid, text)
        else:
            state = supervisor.start(sid, prompt=text)
        notify()
        return {"id": sid, "created": False, "process": state}

    async def usage(p: dict) -> dict:
        ctx = None
        sid = p.get("sessionId")
        if sid:
            require_plain_name(sid, "sesión")
            ctx = await asyncio.to_thread(session_context, session_path(root, sid), Path.home())
        lim = limits.state if limits else {"fiveHour": None, "weekly": None,
                                           "error": "sin poller de límites", "lastOk": None}
        return {"context": ctx, "limits": lim}

    for channel, handler in {
        "reviews.github": github, "reviews.start": review_start, "reviews.setReviewers": set_reviewers, "usage.get": usage,
        "sessions.tree": tree, "sessions.new": new, "sessions.open": open_,
        "sessions.stop": stop, "sessions.rm": rm, "sessions.archive": archive, "sessions.script": script,
        "sessions.doc": doc, "sessions.refreshReview": refresh, "sessions.repoRm": repo_rm,
        "ui.config": ui_config, "prompts.list": prompts,
    }.items():
        registry.register(channel, handler)
    return notify
