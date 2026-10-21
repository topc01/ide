from __future__ import annotations
import asyncio
import base64
import io
import logging
import re
import threading
import os
import secrets
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from ide_server.claude_usage import LimitsPoller, session_context
from ide_server.config import manager_config, sessions_config, ui_modules
from ide_server.feedback import as_markdown, collect, pending_plans
from ide_server.telegram import TelegramBridge, get_token
from ide_server.gh_discussion import fetch_body, fetch_discussion, save_body
from ide_server.db import Db
from ide_server.devs import PHASES, assign_indices, dev_states, link_prs, set_dev_state, list_devs, set_status, show_dev, sync_from_disk
from ide_server.gh_merge import Merger
from ide_server import pr_changes
from ide_server import pins as pins_mod
from ide_server import later as later_mod
from ide_server.gh_reviews import GithubReviews
from ide_server.plugins import Registry
from ide_server.pr_poller import PrPoller
from ide_server.prompts import list_prompts, load_prompt
from ide_server.repos_fs import require_session, rm_repo, worktree_path
from ide_server.scripts import list_scripts, script_argv, script_env
from ide_server.session_ops import (
    archive_session, check_delete, create_pr_session, create_session, create_stack_review, parse_pr_url, refresh_review,
    remove_session,
)
from ide_server.sessions_fs import (
    find_main, list_sessions, normalize_id, parse_frontmatter, read_session, read_toml, render_template, require_plain_name,
    session_path, state_file, SessionError, update_session_toml,
)
from ide_server.supervisor import Supervisor, clean_env
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
                "later": later_mod.items(db) if db else [],
                "feedbackPending": pending_plans(root),
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
        sid = _resolve(p.get("id"))
        # solo la principal rutea: lo prueba con el token que el IDE le pasa a SU claude al lanzarla
        # (un campo "caller" lo podría omitir cualquiera)
        if not secrets.compare_digest(str(p.get("token") or ""), supervisor.manager_token):
            raise SessionError("forbidden", "solo la sesión principal puede mandar prompts a otras sesiones")
        caller = "manager"
        # con encabezado: nunca empieza con "!" (claude lo correría como shell) ni con "/", y la
        # sesión sabe de quién viene
        text = "[Mensaje de la sesión manager]\n" + text.strip()
        state, how = _deliver_to(sid, text, caller)
        return {"id": sid, "process": state, "delivered": how}

    def _deliver_to(sid: str, text: str, actor: str) -> tuple[str, str]:
        """Al claude de una sesión: a su cola si corre; si está parada, la lanza con el texto."""
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
            db.event(datetime.now().isoformat(timespec="seconds"), actor, "prompt", dev=sid, data={"text": text[:300]})
        notify()
        return state, how

    def _resolve(raw: str) -> str:
        """Id de sesión o número de desarrollo (#8/8) → id de sesión."""
        sid = str(raw or "").strip()
        if re.fullmatch(r"#?\d+", sid) and db is not None:
            n = int(sid.lstrip("#"))
            hit = [k[2:] for k, v in db.with_prefix("devidx:").items() if v == n and k.startswith("s:")]
            if not hit:
                raise SessionError("unknown_dev", f"el desarrollo #{n} no tiene sesión")
            sid = hit[0]
        require_session(root, sid)
        return sid

    def _manager_only(p: dict) -> None:
        if not secrets.compare_digest(str(p.get("token") or ""), supervisor.manager_token):
            raise SessionError("forbidden", "solo la sesión principal")

    # -- Telegram (ver telegram.py) ------------------------------------------------------------------
    async def _tg_deliver(text: str) -> str:
        main = await asyncio.to_thread(find_main, root)
        if main is None:
            raise SessionError("no_main", "no hay sesión principal")
        _, how = _deliver_to(main, "[Mensaje de Telegram del usuario] (respóndele con `ide reply`; para mandar algo a "
                             "una sesión usa `ide session propose`)\n" + text, "telegram")
        return how

    async def _tg_propose_ok(sid: str, text: str) -> str:
        _, how = _deliver_to(sid, "[Mensaje de la sesión manager]\n" + text, "telegram")
        return f"Mandado a {sid} ({how})."

    bridge = TelegramBridge(db, deliver=_tg_deliver, propose_ok=_tg_propose_ok) if db is not None else None

    async def tg_reply(p: dict) -> dict:
        _manager_only(p)
        if bridge is None:
            raise SessionError("no_db", "sin base")
        text = (p.get("text") or "").strip()
        if not text:
            raise SessionError("bad_request", "falta el texto")
        try:
            await bridge.send(text)
        except RuntimeError as exc:
            raise SessionError("telegram_off", str(exc))
        return {"ok": True}

    async def propose(p: dict) -> dict:
        """La manager propone mandarle algo a una sesión; se ejecuta solo con tu Sí en Telegram."""
        _manager_only(p)
        text = (p.get("text") or "").strip()
        if not text or bridge is None:
            raise SessionError("bad_request", "falta el texto")
        sid = await asyncio.to_thread(_resolve, p.get("id"))
        n = db.get(f"devidx:s:{sid}") if db else None
        try:
            pid = await bridge.propose(sid, f"#{n} ({sid})" if n else sid, text)
        except RuntimeError as exc:
            raise SessionError("telegram_off", str(exc))
        return {"id": sid, "proposal": pid}

    async def tg_status(_p: dict) -> dict:
        return {"token": bool(await asyncio.to_thread(get_token)), "chat": bool(db and db.get("telegram:chat"))}

    nightly_state = {"running": False}

    def _run_nightly(main: str, text: str, log_path: Path) -> None:
        """`claude -p` aparte, en la carpeta de la principal (sus instrucciones de manager), con permisos
        mínimos: leer, `ide feedback collect` y escribir en `feedback/`. El material que lee lo pueden
        haber escrito terceros (PRs, tickets): no le damos con qué actuar (ni `ide session`, ni shell)."""
        import shlex
        cmd = sessions_config(root)["claude_command"]
        # sin shell: el material ya lo juntó el IDE (feedback/material-*.md); leer solo el workspace y tu
        # CLAUDE.md global, editar solo en feedback/ (Edit cubre toda escritura de archivos)
        argv = [*shlex.split(cmd), "-p", text, "--add-dir", str(root),
                "--allowedTools", f"Read(/{root}/**)", "Read(~/.claude/CLAUDE.md)",
                f"Edit(/{session_path(root, main)}/feedback/**)"]   # ruta absoluta: la relativa no la toma
        env = {**clean_env(dict(os.environ)), "IDE_WORKSPACE": str(root)}
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "wb") as fh:
                subprocess.run(argv, cwd=session_path(root, main), env=env, stdin=subprocess.DEVNULL,
                               stdout=fh, stderr=subprocess.STDOUT, timeout=1800)
        except Exception:  # noqa: BLE001
            log.exception("la revisión nocturna falló")
        finally:
            nightly_state["running"] = False
            try:
                asyncio.run_coroutine_threadsafe(_notify_async(), loop_box["loop"])
            except Exception:  # noqa: BLE001
                pass

    loop_box: dict = {}

    async def _notify_async() -> None:
        notify()

    async def nightly(_p: dict | None = None) -> dict:
        """Revisión de feedback desde la última (prompt `nightly-review`), como manager en modo
        restringido (ver _run_nightly). Deja un plan en `feedback/` de la principal."""
        main = await asyncio.to_thread(find_main, root)
        if main is None:
            raise SessionError("no_main", "no hay sesión principal")
        if nightly_state["running"]:
            raise SessionError("busy", "ya hay una revisión de feedback corriendo")
        now = datetime.now()
        since = (db.get("nightly:since") if db else None) or (now - timedelta(days=7)).isoformat(timespec="minutes")
        date = now.date().isoformat()
        material = session_path(root, main) / "feedback" / f"material-{date}.md"
        data = await asyncio.to_thread(collect, root, Path.home(), datetime.fromisoformat(since))
        material.parent.mkdir(parents=True, exist_ok=True)
        material.write_text(as_markdown(data), encoding="utf-8")
        text = render_template(await asyncio.to_thread(load_prompt, root, "nightly-review"),
                               {"date": date, "since": since, "material": f"feedback/{material.name}"})
        nightly_state["running"] = True
        loop_box["loop"] = asyncio.get_running_loop()
        log_path = session_path(root, main) / "feedback" / f"{now.date().isoformat()}.log"
        threading.Thread(target=_run_nightly, args=(main, text, log_path), daemon=True).start()
        if db is not None:
            db.set("nightly:since", now.isoformat(timespec="minutes"))
            db.set("nightly:last", now.date().isoformat())
            db.event(now.isoformat(timespec="seconds"), "ide", "nightly-review", dev=main, data={"since": since})
        return {"id": main, "delivered": f"revisión corriendo aparte (log: feedback/{log_path.name})", "process": "headless"}

    async def nightly_loop(stop: asyncio.Event) -> None:
        """A la hora de `[manager] nightly` (si el IDE está corriendo), una vez por día."""
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), 60)
                return
            except asyncio.TimeoutError:
                pass
            hhmm = str(manager_config(root).get("nightly") or "")
            if not re.fullmatch(r"\d{1,2}:\d{2}", hhmm) or db is None:
                continue
            now = datetime.now()
            h, m = map(int, hhmm.split(":"))
            if (now.hour, now.minute) >= (h, m) and db.get("nightly:last") != now.date().isoformat():
                try:
                    await nightly()
                except Exception:  # noqa: BLE001 — se reintenta en el próximo minuto
                    log.exception("no se pudo pedir la revisión nocturna")

    def _review_session(url: str) -> str | None:
        """La sesión que revisa la PR: la suya o la de un stack que la incluye."""
        found = None
        for s in list_sessions(root):
            if s.get("kind") != "review":
                continue
            if url in (s.get("stackPrs") or []):
                return s["id"]
            if s.get("prUrl") == url:
                found = s["id"]
        return found

    async def review_draft(p: dict) -> dict:
        """El veredicto de la sesión de revisión y el review listo para publicar (de su SESSION.md)."""
        sid = await asyncio.to_thread(_review_session, p["url"])
        if sid is None:
            return {"id": None, "verdict": None, "body": "", "why": ""}
        f = session_path(root, sid) / "SESSION.md"
        _, body = parse_frontmatter(f.read_text(encoding="utf-8")) if f.is_file() else ({}, "")
        level = "##"
        stack = (await asyncio.to_thread(read_session, root, sid)).get("stackPrs")
        if stack:                               # revisión de stack: la sección `## <repo>#<n>` de esta PR
            repo, number = parse_pr_url(p["url"])
            m = re.search(rf"^## [^\n]*{re.escape(repo)}#{number}\b[^\n]*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
            body, level = (m.group(1) if m else ""), "###"
        def section(name: str) -> str:
            m = re.search(rf"^{level} {name}[^\n]*\n(.*?)(?=^{level} |^## |\Z)", body, re.M | re.S)
            return m.group(1).strip() if m else ""
        v = section("Veredicto")
        first = v.splitlines()[0].strip().lower() if v else ""
        verdict = "approve" if first.startswith("aprob") else "request-changes" if "cambio" in first else None
        return {"id": sid, "verdict": verdict, "why": "\n".join(v.splitlines()[1:]).strip(),
                "body": section("Review para GitHub")}

    async def review_submit(p: dict) -> dict:
        """Publica TU review (botones Aprobar / Pedir cambios): `gh pr review`. La sesión solo sugiere."""
        url, event, body = p.get("url"), p.get("event"), (p.get("body") or "").strip()
        if event not in ("approve", "request-changes"):
            raise SessionError("bad_request", "event: approve | request-changes")
        if event == "request-changes" and not body:
            raise SessionError("bad_request", "pedir cambios necesita un comentario")
        st = gh_reviews.state if gh_reviews else {}
        mine_to_review = {c["url"] for c in [*(st.get("pending") or []), *(st.get("changesRequested") or [])]}
        sid = await asyncio.to_thread(_review_session, url)
        if url not in mine_to_review and sid is None:
            raise SessionError("forbidden", "solo PRs que te pidieron revisar (o con sesión de revisión)")
        out = await asyncio.to_thread(subprocess.run, ["gh", "pr", "review", url, f"--{event}", "--body-file", "-"],
                                      input=body, capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            raise SessionError("gh_failed", f"gh pr review: {out.stderr.strip() or out.returncode}")
        stack = sid is not None and (await asyncio.to_thread(read_session, root, sid)).get("stackPrs")
        if sid is not None and db is not None and not stack:   # en un stack, la sesión marca el total
            await asyncio.to_thread(set_status, root, db, sid,
                                    "approved" if event == "approve" else "changes-requested", actor="ide")
        if db is not None:
            db.event(datetime.now().isoformat(timespec="seconds"), "ide", f"review-{event}", dev=sid, pr_url=url)
        if gh_reviews is not None:
            asyncio.get_running_loop().create_task(gh_reviews.poll_once())
        notify()
        return {"ok": True}

    async def attach(p: dict) -> dict:
        """Adjuntar un archivo a la conversación: se guarda en `attachments/` de la sesión (su claude lo
        lee sin pedir permiso) y, si corre, se pega su ruta en el input (las imágenes entran como
        [Image #n]). Por WS en base64 (máx. 10 MB)."""
        sid = require_plain_name(p["id"], "sesión")
        require_session(root, sid)
        try:
            raw = base64.b64decode(p.get("data") or "", validate=True)
        except (ValueError, TypeError):
            raise SessionError("bad_request", "archivo inválido")
        if not raw or len(raw) > 10 * 1024 * 1024:
            raise SessionError("too_large", "el archivo tiene que pesar entre 1 byte y 10 MB")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(str(p.get("name") or "archivo")).name).strip("-.") or "archivo"
        d = session_path(root, sid) / "attachments"
        d.mkdir(exist_ok=True)
        f = d / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{name[-80:]}"
        await asyncio.to_thread(f.write_bytes, raw)
        pasted = p.get("paste", True) is not False and supervisor.state(sid) == "running"
        if pasted:
            supervisor.paste(sid, f" {f} ")
        return {"path": str(f), "pasted": pasted}

    def _att(sid: str, name: str | None = None) -> Path:
        require_plain_name(sid, "sesión")
        require_session(root, sid)
        d = session_path(root, sid) / "attachments"
        return d if name is None else d / require_plain_name(name, "archivo")

    def _link(f: Path) -> str | None:
        if f.suffix.lower() != ".url":
            return None
        m = re.search(r"^URL=(https?://\S+)", f.read_text(encoding="utf-8", errors="replace"), re.M)
        return m.group(1) if m else None

    def _kind(f: Path) -> str:
        """image | pdf | text | other: por extensión o, sin ella, por el contenido."""
        import mimetypes
        mime = mimetypes.guess_type(f.name)[0]
        if mime is None:
            with open(f, "rb") as fh:
                head = fh.read(16)
            if head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8")) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
                return "image"
            if head.startswith(b"%PDF"):
                return "pdf"
            return "other"
        if mime.startswith("image/") and mime != "image/svg+xml":
            return "image"
        if mime == "application/pdf":
            return "pdf"
        return "text" if mime.startswith("text/") or mime in ("application/json", "application/xml", "application/x-sh") else "other"

    async def attachments_list(p: dict) -> dict:
        d = _att(p["id"])
        files = sorted((f for f in d.iterdir() if f.is_file() and not f.name.startswith(".")),
                       key=lambda f: f.stat().st_mtime, reverse=True) if d.is_dir() else []
        return {"dir": str(d), "files": [{"name": f.name, "size": f.stat().st_size, "path": str(f), "kind": _kind(f),
                                          "url": _link(f),
                                          "at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")}
                                         for f in files]}

    async def attachments_link(p: dict) -> dict:
        """Un link como adjunto: `<nombre>.url` (acceso directo estándar, `URL=…`; claude lo lee)."""
        url = str(p.get("url") or "").strip()
        if not re.fullmatch(r"https?://\S{3,2000}", url):
            raise SessionError("bad_request", "tiene que ser un link http(s)")
        from urllib.parse import urlparse
        u = urlparse(url)
        base = str(p.get("name") or "").strip() or (u.netloc + u.path).strip("/").replace("/", "-")
        name = (re.sub(r"[^A-Za-z0-9._ -]+", "-", base).strip(" .-") or "link")[:80]
        d = _att(p["id"])
        d.mkdir(exist_ok=True)
        f = d / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{name}.url"
        f.write_text(f"[InternetShortcut]\nURL={url}\n", encoding="utf-8")
        return {"name": f.name}

    async def attachments_rename(p: dict) -> dict:
        src, to = _att(p["id"], p["name"]), str(p.get("to") or "").strip()
        if src.suffix and not Path(to).suffix:      # "tech1" → "tech1.png": sin la extensión no se sabe qué es
            to += src.suffix
        dst = _att(p["id"], re.sub(r"[^A-Za-z0-9._ -]+", "-", to).strip(" .") or "archivo")
        if not src.is_file():
            raise SessionError("not_found", f"no existe {p['name']}")
        if dst.exists():
            raise SessionError("exists", f"ya hay un archivo {dst.name}")
        src.rename(dst)
        return {"name": dst.name, "path": str(dst)}

    async def attachments_delete(p: dict) -> dict:
        f = _att(p["id"], p["name"])
        if f.is_file():
            f.unlink()
        return {"ok": True}

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
        # fase de GitHub al ponerla a mano: la puesta gana hasta que GitHub cambie
        extra = {}
        if "gh" in p:
            if p["gh"] is not None and p["gh"] not in (*PHASES, "merging"):
                raise SessionError("bad_request", f"fase de GitHub inválida: {p['gh']!r}")
            extra["gh"] = p["gh"]
        await asyncio.to_thread(set_dev_state, root, db, key, p.get("status"), actor="ide", note=note, **extra)
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
        return await asyncio.to_thread(lambda: pr_changes.changes(root, _pr_card(p["url"]), fresh=bool(p.get("fresh"))))

    async def pr_file_diff(p: dict) -> dict:
        return await asyncio.to_thread(pr_changes.file_diff, root, _pr_card(p["url"]), p["path"], p.get("oldPath"))

    async def pr_reviewers(p: dict) -> dict:
        """Pedir revisión a (add) o sacar (remove) revisores de una PR tuya: `gh pr edit`."""
        pr = _pr_card(p["url"])
        me = (gh_reviews.state if gh_reviews else {}).get("me")
        if not me or pr.get("author") != f"@{me}":
            raise SessionError("not_yours", "solo en tus PRs")
        logins = [l for l in (p.get("add") or []) + (p.get("remove") or [])]
        if not logins or not all(isinstance(l, str) and re.fullmatch(r"[A-Za-z0-9-]{1,39}(/[A-Za-z0-9_.-]+)?", l) for l in logins):
            raise SessionError("bad_request", "logins inválidos")
        args = ["gh", "pr", "edit", p["url"]]
        if p.get("add"):
            args += ["--add-reviewer", ",".join(p["add"])]
        if p.get("remove"):
            args += ["--remove-reviewer", ",".join(p["remove"])]
        out = await asyncio.to_thread(subprocess.run, args, capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            raise SessionError("gh_failed", f"gh pr edit: {out.stderr.strip() or out.returncode}")
        if db is not None:
            db.event(datetime.now().isoformat(timespec="seconds"), "ide", "reviewers", pr_url=p["url"],
                     data={"add": p.get("add") or [], "remove": p.get("remove") or []})
        if gh_reviews is not None:
            asyncio.get_running_loop().create_task(gh_reviews.poll_once())
        return {"ok": True}

    async def session_messages(p: dict) -> dict:
        sid = require_plain_name(p["id"], "sesión")
        return {"messages": await asyncio.to_thread(pins_mod.recent_messages, root, sid, Path.home(), int(p.get("limit") or 15))}

    def _pin_key(key) -> str:
        if not isinstance(key, str) or not re.match(r"^(s|st|p):.{1,300}$", key):
            raise SessionError("bad_request", f"clave de desarrollo inválida: {key!r}")
        return key

    async def pins_list(_p: dict) -> dict:
        return {"pins": pins_mod.all_pins(db) if db else {}}

    async def pins_add(p: dict) -> dict:
        text = (p.get("text") or "").strip()
        if not text or db is None:
            raise SessionError("bad_request", "falta el texto")
        pin = pins_mod.add(db, _pin_key(p.get("key")), text, p.get("source"))
        await manager.broadcast("pins.changed", {"pins": pins_mod.all_pins(db)})
        return {"pin": pin}

    async def pins_remove(p: dict) -> dict:
        if db is None:
            raise SessionError("no_db", "sin base")
        pins_mod.remove(db, _pin_key(p.get("key")), str(p.get("id")))
        await manager.broadcast("pins.changed", {"pins": pins_mod.all_pins(db)})
        return {"ok": True}

    # -- pendientes "para después" ----------------------------------------------------------------
    async def later_add(p: dict) -> dict:
        if db is None:
            raise SessionError("no_db", "sin base")
        key = _pin_key(p.get("key") or (f"s:{p['sid']}" if p.get("sid") else None))
        actor = p.get("actor") if isinstance(p.get("actor"), str) and p["actor"].startswith(("claude:", "cli")) else "usuario"
        try:
            item = later_mod.add(db, key, p.get("text") or "", p.get("context"), actor)
        except ValueError as exc:
            raise SessionError("bad_request", str(exc)) from exc
        db.event(datetime.now().isoformat(timespec="seconds"), actor, "later",
                 dev=key[2:] if key.startswith("s:") else None, data={"text": item["text"][:300]})
        notify()
        return {"item": item}

    async def later_list(p: dict) -> dict:
        return {"items": later_mod.items(db, open_only=not p.get("all")) if db else []}

    async def later_answer(p: dict) -> dict:
        """Responder un pendiente: la respuesta se le manda a la sesión (si el desarrollo tiene)."""
        if db is None:
            raise SessionError("no_db", "sin base")
        item = later_mod.get(db, str(p.get("id")))
        answer = (p.get("answer") or "").strip()
        if item is None or item["status"] != "open":
            raise SessionError("not_found", "ese pendiente ya no está abierto")
        if not answer:
            raise SessionError("bad_request", "falta la respuesta")
        how = "anotada"
        sid = item["key"][2:] if item["key"].startswith("s:") else None
        if sid and session_path(root, sid).is_dir():
            # con encabezado: nunca empieza con "!" o "/", y la sesión sabe qué es
            text = ("[Respuesta del usuario a un pendiente que quedó para después]\n"
                    f"Pendiente: {item['text']}\nRespuesta: {answer}")
            _, how = _deliver_to(sid, text, "usuario")
        later_mod.close(db, item["id"], "answered", answer)
        notify()
        return {"ok": True, "delivered": how}

    async def later_dismiss(p: dict) -> dict:
        if db is None:
            raise SessionError("no_db", "sin base")
        try:
            later_mod.close(db, str(p.get("id")), "dismissed")
        except KeyError as exc:
            raise SessionError("not_found", "no existe ese pendiente") from exc
        notify()
        return {"ok": True}

    async def stack_status(p: dict) -> dict:
        """Si el stack de esa PR necesita re-apilar (una rama quedó atrás de su madre) o ponerse al día
        con la base. Las PRs, de abajo hacia arriba."""
        pr = _pr_card(p["url"])
        st = gh_reviews.state if gh_reviews else {}
        prs = sorted((st.get("stacks") or {}).get(pr["stack"]["id"], [pr]) if pr.get("stack") else [pr],
                     key=lambda c: (c.get("stack") or {}).get("position", 1))
        return await asyncio.to_thread(pr_changes.stack_status, root, prs)

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

    async def review_start_stack(p: dict) -> dict:
        """"Revisar stack": una sola sesión para las PRs de un stack que te pidieron revisar (de abajo
        hacia arriba). Archiva las sesiones de revisión individuales de esas PRs."""
        st = gh_reviews.state if gh_reviews else {}
        pending = {c["url"]: c for c in st.get("pending") or []}
        urls = p.get("urls") or []
        if len(urls) < 2 or not all(isinstance(u, str) and u in pending for u in urls):
            raise SessionError("bad_request", "Revisar stack: al menos 2 PRs que te pidieron revisar")
        stacks = {(pending[u].get("stack") or {}).get("id") for u in urls}
        if len(stacks) != 1 or None in stacks:
            raise SessionError("bad_request", "esas PRs no son del mismo stack")
        urls = sorted(urls, key=lambda u: pending[u]["stack"]["position"])
        for u in urls:                          # las sesiones individuales se reemplazan por la del stack
            repo, number = parse_pr_url(u)
            old = normalize_id(f"pr-{repo}-{number}")
            if (session_path(root, old) / ".session.toml").is_file():
                if runner is not None:
                    await asyncio.to_thread(runner.stop_place, old)
                supervisor.stop(old)
                await asyncio.to_thread(archive_session, root, old, force=True)
        res = await asyncio.to_thread(create_stack_review, root, urls)
        sid = res["session"]["id"]
        process = supervisor.state(sid)
        if not res.get("existed"):
            process = supervisor.start(sid, resume=False)
        if db is not None:
            for u in urls:
                db.event(datetime.now().isoformat(timespec="seconds"), "ide", "review-start", dev=sid, pr_url=u)
        notify()
        return {"id": sid, "created": not res.get("existed"), "process": process}

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
        "reviews.github": github, "reviews.start": review_start, "reviews.startStack": review_start_stack, "reviews.setReviewers": set_reviewers,
        "dev.status": dev_status, "dev.rename": dev_rename, "dev.hide": dev_hide, "pr.files": pr_files, "pr.fileDiff": pr_file_diff, "stack.restack": stack_restack, "stack.status": stack_status, "pr.reviewers": pr_reviewers, "session.messages": session_messages,
        "later.add": later_add, "later.list": later_list, "later.answer": later_answer, "later.dismiss": later_dismiss,
        "pins.list": pins_list, "pins.add": pins_add, "pins.remove": pins_remove, "dev.state": dev_state, "prs.ready": prs_ready, "dev.unlinkPr": dev_unlink_pr, "dev.list": dev_list, "dev.show": dev_show,
        "reviews.merge": merge, "reviews.mergeDismiss": merge_dismiss, "reviews.discussion": discussion,
        "pr.body": pr_body, "pr.bodySave": pr_body_save, "reviews.mergeRetry": merge_retry, "usage.get": usage,
        "sessions.tree": tree, "sessions.new": new, "sessions.newForPr": new_for_pr, "sessions.open": open_,
        "sessions.stop": stop, "sessions.send": send, "sessions.attach": attach, "attachments.list": attachments_list,
        "attachments.rename": attachments_rename, "attachments.link": attachments_link, "attachments.delete": attachments_delete, "sessions.propose": propose, "telegram.reply": tg_reply, "telegram.status": tg_status,
        "sessions.fresh": fresh, "review.draft": review_draft, "review.submit": review_submit, "manager.nightly": nightly, "sessions.rm": rm, "sessions.archive": archive, "sessions.script": script,
        "sessions.doc": doc, "sessions.refreshReview": refresh, "sessions.repoRm": repo_rm,
        "ui.config": ui_config, "prompts.list": prompts,
    }.items():
        registry.register(channel, handler)
    notify.nightly_loop = nightly_loop      # type: ignore[attr-defined]
    notify.telegram = bridge                # type: ignore[attr-defined]
    return notify
