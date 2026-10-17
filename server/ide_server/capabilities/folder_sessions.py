from __future__ import annotations
import asyncio
import io
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable
from ide_server.claude_usage import LimitsPoller, session_context
from ide_server.config import ui_modules
from ide_server.gh_discussion import fetch_body, fetch_discussion, save_body
from ide_server.db import Db
from ide_server.devs import assign_indices, dev_states, link_prs, set_dev_state, list_devs, set_status, show_dev, sync_from_disk
from ide_server.gh_merge import Merger
from ide_server import pr_changes
from ide_server.gh_reviews import GithubReviews
from ide_server.plugins import Registry
from ide_server.pr_poller import PrPoller
from ide_server.prompts import list_prompts, load_prompt
from ide_server.repos_fs import require_session, rm_repo, worktree_path
from ide_server.scripts import list_scripts, script_argv, script_env
from ide_server.session_ops import (
    archive_session, check_delete, create_pr_session, create_session, parse_pr_url, refresh_review,
    remove_session,
)
from ide_server.sessions_fs import (
    list_sessions, normalize_id, read_session, read_toml, render_template, require_plain_name,
    session_path, state_file, SessionError, update_session_toml,
)
from ide_server.supervisor import Supervisor
from ide_server.workspace import discover_repos

log = logging.getLogger(__name__)


def register(registry: Registry, root: Path, manager, *, hooks, supervisor: Supervisor,
             poller: PrPoller, gh_reviews: GithubReviews | None = None,
             limits: LimitsPoller | None = None, merger: Merger | None = None,
             db: Db | None = None, runner=None) -> Callable[[], None]:

    def build_tree(snap: dict, derived: dict) -> dict:
        """Lectura de disco + git: corre en un thread (no bloquea el loop)."""
        sessions = list_sessions(root)
        if db is not None:                      # la base es la fuente de verdad del estado
            sync_from_disk(root, db, sessions)
            status = {d["id"]: d["status"] for d in db.devs()}
            if gh_reviews is not None:
                link_prs(db, sessions, gh_reviews.state)
                assign_indices(db, list_devs(root, db, sessions, gh_reviews.state))
            for s in sessions:
                if status.get(s["id"]):
                    s["status"] = status[s["id"]]
        for s in sessions:
            p = snap.get(s["id"], {})
            s.update(process=p.get("process", "stopped"), terminalId=p.get("terminalId"),
                     launchError=p.get("launchError"), attention=p.get("attention"))
            if s["kind"] == "review":
                s.update({"prState": None, "pollError": None, "lastOk": None,
                          **derived.get(s["id"], {})})
        repos = discover_repos(root)
        return {"sessions": sessions, "workspaceRepos": repos, "devNames": db.dev_names() if db else {},
                "devHidden": db.hidden_devs() if db else [],
                "devPrs": db.dev_prs() if db else {},
                "devIndex": db.with_prefix("devidx:") if db else {},
                "devStates": dev_states(db) if db else {},
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

    async def new_for_pr(p: dict) -> dict:
        """Sesión para seguir trabajando una PR propia (worktree en su rama) y lanzar su claude."""
        res = await asyncio.to_thread(create_pr_session, root, p["url"])
        sid = res["session"]["id"]
        if db is not None and gh_reviews is not None:      # la sesión hereda el número de la PR/stack
            pr = next((c for lst in [*(gh_reviews.state.get("mine") or {}).values(), *(gh_reviews.state.get("stacks") or {}).values()]
                       for c in lst if c["url"] == p["url"]), None)
            keys = ([f"st:{pr['stack']['id']}"] if pr and pr.get("stack") else []) + [f"p:{p['url']}"]
            inherit = next((n for k in keys if (n := db.get(f"devidx:{k}")) is not None), None)
            if inherit is not None:
                db.dev_index(f"s:{sid}", inherit)
        process = supervisor.start(sid, resume=None if res.get("existed") else False)
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
        if runner is not None:                  # sus servidores no pueden quedar corriendo huérfanos
            await asyncio.to_thread(runner.stop_place, p["id"])
        supervisor.stop(p["id"])                # en el loop: el supervisor no es thread-safe
        await asyncio.to_thread(remove_session, root, p["id"], force=force)
        notify()
        return {"ok": True}

    async def archive(p: dict) -> dict:
        require_session(root, p["id"])
        if runner is not None:                  # para sus servidores antes del `archive` de cada repo
            await asyncio.to_thread(runner.stop_place, p["id"])
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

    async def send(p: dict) -> dict:
        """Encola un prompt a la sesión de un desarrollo (lo usa la principal para rutear): si corre,
        entra a la cola de claude (lo toma al terminar su turno); si está parada, la lanza con él.
        `id` = id de la sesión o el número del desarrollo (`#8`/`8`)."""
        text = p.get("text")
        if not isinstance(text, str) or not text.strip():
            raise SessionError("bad_request", "falta el texto")
        sid = str(p.get("id") or "").strip()
        if re.fullmatch(r"#?\d+", sid) and db is not None:
            n = int(sid.lstrip("#"))
            hit = [k[2:] for k, v in db.with_prefix("devidx:").items() if v == n and k.startswith("s:")]
            if not hit:
                raise SessionError("unknown_dev", f"el desarrollo #{n} no tiene sesión")
            sid = hit[0]
        require_session(root, sid)
        caller = p.get("caller")
        if caller:                               # desde una sesión: solo la principal rutea
            ck = (read_toml(session_path(root, require_plain_name(caller, "sesión")) / ".session.toml") or {}).get("kind")
            if ck != "main":
                raise SessionError("forbidden", "solo la sesión principal puede mandar prompts a otras sesiones")
        state = supervisor.state(sid)
        if state == "queued":
            raise SessionError("queued", f"{sid} está en cola (max_running): espera a que arranque")
        if state == "running":
            supervisor.send(sid, text)
            how = "encolado"
        else:
            state = supervisor.start(sid, prompt=text)
            how = "lanzada con el prompt"
        if db is not None:
            db.event(datetime.now().isoformat(timespec="seconds"), caller or "ide", "prompt", dev=sid,
                     data={"text": text[:300]})
        notify()
        return {"id": sid, "process": state, "delivered": how}

    async def fresh(p: dict) -> dict:
        """Nueva conversación en la misma sesión (misma carpeta, worktrees y SESSION.md): para cuando la
        conversación se alargó o se ensució. La anterior queda en su transcript."""
        sid = require_plain_name(p["id"], "sesión")
        require_session(root, sid)
        supervisor.stop(sid)
        await asyncio.to_thread(update_session_toml, root, sid,
                                lambda d: (d.pop("claude_session", None), d.pop("claude_name", None)))
        kind = (await asyncio.to_thread(read_toml, session_path(root, sid) / ".session.toml")).get("kind")
        prompt = None if kind == "main" else (
            "Conversación nueva en este mismo desarrollo (la anterior se cerró para empezar con contexto limpio). "
            "Lee tu SESSION.md (estado, plan, decisiones y Feedback) y `git status`/`git log` de tus worktrees, "
            "resúmeme en pocas líneas dónde quedó y qué sigue, y espera instrucciones.")
        state = supervisor.start(sid, resume=False, prompt=prompt)
        if db is not None:
            db.event(datetime.now().isoformat(timespec="seconds"), "ide", "fresh", dev=sid)
        notify()
        return {"process": state}

    async def doc(p: dict) -> dict:
        path = require_session(root, p["id"])
        name = state_file(read_toml(path / ".session.toml").get("kind"))
        if name is None:
            raise SessionError("no_doc", f"{p['id']} no tiene SESSION.md")
        f = path / name
        return {"name": name, "text": f.read_text(encoding="utf-8") if f.is_file() else ""}

    async def refresh(p: dict) -> dict:
        s = await asyncio.to_thread(refresh_review, root, p["id"])
        await poller.poll_once()
        notify()
        return {"session": s}

    async def repo_rm(p: dict) -> dict:
        if runner is not None:
            await asyncio.to_thread(runner.stop_place, require_plain_name(p["id"], "sesión"), p["repo"])
        await asyncio.to_thread(rm_repo, root, p["id"], p["repo"], force=bool(p.get("force")),
                                out=io.StringIO())
        notify()
        return {"ok": True}

    async def ui_config(_p: dict) -> dict:
        return {"modules": ui_modules(root)}

    async def prompts(_p: dict) -> dict:
        return {"prompts": await asyncio.to_thread(list_prompts, root)}

    async def github(_p: dict) -> dict:
        merges = merger.public() if merger else {}
        return {**gh_reviews.state, "merges": merges} if gh_reviews else {"pending": [], "changesRequested": [], "me": None,
                                                    "reviewers": [], "reviewersTruncated": False,
                                                    "members": [], "selected": None, "mine": {}, "stacks": {},
                                                    "error": "polling de GitHub desactivado",
                                                    "lastOk": None, "orgs": []}

    async def pr_body(p: dict) -> dict:
        return await asyncio.to_thread(fetch_body, p["url"])

    async def pr_body_save(p: dict) -> dict:
        body = p["body"]
        if not isinstance(body, str):
            raise SessionError("bad_request", "body debe ser texto")
        await asyncio.to_thread(save_body, p["url"], body)
        if db is not None:
            db.event(datetime.now().isoformat(timespec="seconds"), "ide", "pr-body-edited", pr_url=p["url"])
        return {"ok": True}

    async def discussion(p: dict) -> dict:
        return await asyncio.to_thread(fetch_discussion, p["url"])

    async def merge(p: dict) -> dict:
        if merger is None:
            raise SessionError("github_off", "merge desactivado")
        return await asyncio.to_thread(merger.merge, p["url"])

    async def merge_retry(p: dict) -> dict:
        if merger is None:
            raise SessionError("github_off", "merge desactivado")
        merger.retry(p["url"])
        return {"ok": True}

    async def dev_status(p: dict) -> dict:
        if db is None:
            raise SessionError("no_db", "sin base")
        row = await asyncio.to_thread(set_status, root, db, require_plain_name(p["id"], "sesión"),
                                      p["status"], actor=p.get("actor") or "ide", note=p.get("note"))
        notify()
        return {"dev": row}

    async def dev_rename(p: dict) -> dict:
        """Nombre del desarrollo solo para el IDE (no toca SESSION.md ni GitHub); vacío = el original."""
        if db is None:
            raise SessionError("no_db", "sin base")
        key, name = p.get("key"), (p.get("name") or "").strip()
        if not isinstance(key, str) or not re.match(r"^(s|st|p):.{1,300}$", key):
            raise SessionError("bad_request", f"clave de desarrollo inválida: {key!r}")
        if len(name) > 120:
            raise SessionError("bad_request", "nombre demasiado largo (máx. 120)")
        db.set_dev_name(key, name or None)
        db.event(datetime.now().isoformat(timespec="seconds"), "ide", "renamed",
                 dev=key[2:] if key.startswith("s:") else None, data={"key": key, "name": name or None})
        notify()
        return {"ok": True}

    async def dev_hide(p: dict) -> dict:
        """Ocultar/mostrar un desarrollo en Mis desarrollos (va al grupo "Ocultos"; solo el IDE)."""
        if db is None:
            raise SessionError("no_db", "sin base")
        key = p.get("key")
        if not isinstance(key, str) or not re.match(r"^(s|st|p):.{1,300}$", key):
            raise SessionError("bad_request", f"clave de desarrollo inválida: {key!r}")
        db.set_dev_hidden(key, bool(p.get("hidden")))
        db.event(datetime.now().isoformat(timespec="seconds"), "ide", "hidden" if p.get("hidden") else "shown",
                 dev=key[2:] if key.startswith("s:") else None, data={"key": key})
        notify()
        return {"ok": True}

    async def dev_unlink_pr(p: dict) -> dict:
        """Saca una PR del desarrollo de la sesión (no vuelve aunque el worktree esté en su rama)."""
        if db is None:
            raise SessionError("no_db", "sin base")
        sid = require_plain_name(p.get("id"), "sesión")
        url = p.get("url")
        if not isinstance(url, str) or not url.startswith("https://github.com/"):
            raise SessionError("bad_request", f"url inválida: {url!r}")
        db.link_pr(url, sid, out=True)
        db.event(datetime.now().isoformat(timespec="seconds"), "ide", "pr-unlinked", dev=sid, pr_url=url)
        notify()
        return {"ok": True}

    async def dev_state(p: dict) -> dict:
        """Estado del desarrollo desde la UI (cualquier desarrollo; `status` null = sin estado)."""
        if db is None:
            raise SessionError("no_db", "sin base")
        key = p.get("key")
        if not isinstance(key, str) or not re.match(r"^(s|st|p):.{1,300}$", key):
            raise SessionError("bad_request", f"clave de desarrollo inválida: {key!r}")
        note = (p.get("note") or "").strip()[:300] or None
        await asyncio.to_thread(set_dev_state, root, db, key, p.get("status"), actor="ide", note=note)
        notify()
        return {"ok": True}

    async def prs_ready(p: dict) -> dict:
        """"Mandar a revisión": saca de draft (`gh pr ready`) PRs tuyas en draft del desarrollo."""
        urls = p.get("urls")
        if not isinstance(urls, list) or not urls or gh_reviews is None:
            raise SessionError("bad_request", "faltan las PRs")
        st = gh_reviews.state
        mine = {c["url"]: c for lst in (st.get("mine") or {}).values() for c in lst}
        done, errors = [], []
        for u in urls:
            c = mine.get(u)
            if not c or c.get("author") != f"@{st.get('me')}":
                errors.append(f"{u}: no es una PR tuya abierta"); continue
            if not c.get("draft"):
                continue
            out = await asyncio.to_thread(subprocess.run, ["gh", "pr", "ready", u], capture_output=True, text=True, timeout=60)
            if out.returncode != 0:
                errors.append(f"{u}: {out.stderr.strip() or out.returncode}")
            else:
                done.append(u)
                if db is not None:
                    db.event(datetime.now().isoformat(timespec="seconds"), "ide", "pr-ready", pr_url=u)
        if errors and not done:
            raise SessionError("gh_failed", "; ".join(errors))
        return {"ready": done, "errors": errors}

    def _pr_card(url: str) -> dict:
        st = gh_reviews.state if gh_reviews else {}
        lists = [*(st.get("mine") or {}).values(), *(st.get("stacks") or {}).values(),
                 st.get("pending") or [], st.get("changesRequested") or []]
        pr = next((c for lst in lists for c in lst if c["url"] == url), None)
        if pr is None:
            raise SessionError("unknown_pr", f"no conozco la PR {url} (¿está abierta? espera el próximo poll)")
        return pr

    async def pr_files(p: dict) -> dict:
        return await asyncio.to_thread(pr_changes.changes, root, _pr_card(p["url"]))

    async def pr_file_diff(p: dict) -> dict:
        return await asyncio.to_thread(pr_changes.file_diff, root, _pr_card(p["url"]), p["path"], p.get("oldPath"))

    async def stack_restack(p: dict) -> dict:
        if merger is None:
            raise SessionError("github_off", "restack desactivado")
        res = await asyncio.to_thread(merger.restack, p["url"], update_base=bool(p.get("updateBase")))
        if gh_reviews is not None:              # que las cards reflejen las ramas movidas
            asyncio.get_running_loop().create_task(gh_reviews.poll_once())
        return res

    async def _sessions_now() -> list[dict]:
        return (await tree_payload())["sessions"]

    async def dev_list(_p: dict) -> dict:
        if db is None:
            raise SessionError("no_db", "sin base")
        sessions = await _sessions_now()
        return {"devs": await asyncio.to_thread(list_devs, root, db, sessions, gh_reviews.state if gh_reviews else {})}

    async def dev_show(p: dict) -> dict:
        if db is None:
            raise SessionError("no_db", "sin base")
        sessions = await _sessions_now()
        return {"dev": await asyncio.to_thread(show_dev, root, db, p["id"], sessions,
                                               gh_reviews.state if gh_reviews else {})}

    async def merge_dismiss(p: dict) -> dict:
        if merger is None:
            raise SessionError("github_off", "merge desactivado")
        merger.dismiss(p["url"])
        return {"ok": True}

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
        if db is not None:
            db.event(datetime.now().isoformat(timespec="seconds"), "ide", "review-start", dev=sid, pr_url=url)
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
        "reviews.github": github, "reviews.start": review_start, "reviews.setReviewers": set_reviewers,
        "dev.status": dev_status, "dev.rename": dev_rename, "dev.hide": dev_hide, "pr.files": pr_files, "pr.fileDiff": pr_file_diff, "stack.restack": stack_restack, "dev.state": dev_state, "prs.ready": prs_ready, "dev.unlinkPr": dev_unlink_pr, "dev.list": dev_list, "dev.show": dev_show,
        "reviews.merge": merge, "reviews.mergeDismiss": merge_dismiss, "reviews.discussion": discussion,
        "pr.body": pr_body, "pr.bodySave": pr_body_save, "reviews.mergeRetry": merge_retry, "usage.get": usage,
        "sessions.tree": tree, "sessions.new": new, "sessions.newForPr": new_for_pr, "sessions.open": open_,
        "sessions.stop": stop, "sessions.send": send, "sessions.fresh": fresh, "sessions.rm": rm, "sessions.archive": archive, "sessions.script": script,
        "sessions.doc": doc, "sessions.refreshReview": refresh, "sessions.repoRm": repo_rm,
        "ui.config": ui_config, "prompts.list": prompts,
    }.items():
        registry.register(channel, handler)
    return notify
