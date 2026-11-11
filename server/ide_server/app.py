from __future__ import annotations
import asyncio
import contextvars
import subprocess
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi.responses import JSONResponse
from ide_server.capabilities import folder_sessions as folder_cap
from ide_server.capabilities import runs as runs_cap
from ide_server.runs import Runner
from ide_server.db_viewer import DbViewer
from ide_server.config import sessions_config, reviews_config
from ide_server.pr_poller import PrPoller
from ide_server.gh_reviews import GithubReviews
from ide_server.gh_merge import Merger
from ide_server.db import Db
from ide_server.updater import Updater
from ide_server.claude_usage import LimitsPoller
from ide_server.sessions_fs import SessionError
from ide_server.supervisor import ClaudeAgents, Supervisor
from ide_server.watcher import watch_workspace
from ide_server.worktrees import BranchOccupied
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ide_server.config import Settings
from ide_server.plugins import Registry
from ide_server.bus import handle_message, ConnectionManager
from ide_server.capabilities import repos as repos_cap
from ide_server.capabilities import terminals as terminals_cap
from ide_server.capabilities import chat as chat_cap
from ide_server.capabilities import customizations as customizations_cap
from ide_server.capabilities import changes as changes_cap
from ide_server.capabilities import files as files_cap
from ide_server.capabilities import search as search_cap
from ide_server.capabilities import graphite as graphite_cap
from ide_server.capabilities import notion as notion_cap
from ide_server.capabilities import tasks as tasks_cap
from ide_server.capabilities import models as models_cap
from ide_server.capabilities import models_fit as models_fit_cap
from ide_server.capabilities import mlx_config as mlx_config_cap
from ide_server.mlx.orchestrator import build_mlx_router
from ide_server.models.downloader import ModelDownloader

log = logging.getLogger(__name__)
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


_peer_port: contextvars.ContextVar[int | None] = contextvars.ContextVar("peer_port", default=None)


def create_app(root: Path, web_dir: Path | None = None, *, server_url: str | None = None,
               claude_command: str | None = None) -> FastAPI:
    settings = Settings()
    registry = Registry()
    repos_cap.register(registry, root)
    manager = ConnectionManager()
    hooks = terminals_cap.register(registry, root, manager)
    scfg = sessions_config(root)
    notify_box: dict = {"fn": lambda: None}
    supervisor = Supervisor(
        root, spawn=hooks.spawn, kill=hooks.kill,
        server_url=server_url or f"http://{settings.host}:{settings.port}",
        command=claude_command or scfg["claude_command"], max_running=scfg["max_running"],
        on_change=lambda: notify_box["fn"](),
        agents=ClaudeAgents(claude_command or scfg["claude_command"]), write=hooks.write, signal=hooks.signal)
    from ide_server import devs as _devs        # el click en una notificación abre el IDE en esta URL
    _devs.NOTIFY_URL = (server_url or f"http://{settings.host}:{settings.port}").rstrip("/")
    rcfg = reviews_config(root)
    db = Db(root)
    poller = PrPoller(root, interval=rcfg["poll_interval"], on_change=lambda: notify_box["fn"]())
    gh_reviews = GithubReviews(root, interval=rcfg["github_interval"], org=rcfg["github_org"], db=db,
                               on_change=lambda: notify_box["github"]())
    limits = LimitsPoller()
    merger = Merger(root, stacks=lambda: gh_reviews.state, db=db, on_change=lambda: notify_box["github"]())
    from ide_server.merge_all import MergeAll
    # se llama desde threads: el aviso va por el de Merger, que lo agenda en el loop del server
    merger.all = MergeAll(db, merger, stacks=lambda: gh_reviews.state, on_change=lambda: merger._on_change())
    runner = Runner(root)
    viewer = DbViewer(root)
    runs_watch = runs_cap.register(registry, root, manager, runner, viewer, db)
    notify_box["fn"] = folder_cap.register(registry, root, manager, hooks=hooks,
                                           supervisor=supervisor, poller=poller,
                                           gh_reviews=gh_reviews, limits=limits, merger=merger, db=db,
                                           runner=runner)
    def _github_changed() -> None:
        asyncio.get_running_loop().create_task(
            manager.broadcast("reviews.github", {**gh_reviews.state, "merges": merger.public(),
                                                 "mergeAll": merger.all.public()}))
        notify_box["fn"]()                      # el árbol vincula las PRs nuevas a sus sesiones (devPrs)
    notify_box["github"] = _github_changed
    mlx_router = build_mlx_router(root)
    hub = chat_cap.register(registry, root, manager, mlx_router=mlx_router)
    customizations_cap.register(registry, root)
    changes_cap.register(registry, root)
    files_cap.register(registry, root)
    search_cap.register(registry, root)
    graphite_cap.register(registry, root)
    notion_cap.register(registry, root)
    tasks_cap.register(registry, root)
    downloader = ModelDownloader(manager)
    models_cap.register(registry, root, manager, downloader=downloader)
    mlx_config_cap.register(registry, root)
    models_fit_cap.register(registry, root)

    updater = Updater(last_input=hooks.last_input, before_restart=hooks.save_history,
                      notify=lambda st: manager.broadcast("server.update", st))

    async def server_status(_p: dict) -> dict:
        return updater.status()

    async def server_restart(_p: dict) -> dict:
        updater.restart_now()
        return {"ok": True}

    registry.register("server.status", server_status)
    registry.register("server.restart", server_restart)

    async def save_history_loop(stop: asyncio.Event) -> None:
        """El historial de las terminales de `claude` se guarda seguido (sobrevive a un corte)."""
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), 30)
            except asyncio.TimeoutError:
                pass
            try:
                await asyncio.to_thread(hooks.save_history)
            except Exception:  # noqa: BLE001
                log.exception("no se pudo guardar el historial de las terminales")

    stop_bg = asyncio.Event()

    async def browsers_loop(stop: asyncio.Event) -> None:
        from ide_server.browsers import write_mcp_config
        while not stop.is_set():
            try:
                await asyncio.to_thread(write_mcp_config, root)
            except Exception:  # noqa: BLE001
                log.exception("servidores de navegador")
            try:
                await asyncio.wait_for(stop.wait(), 60)
            except asyncio.TimeoutError:
                pass
    from ide_server.devs import _notify_mac
    from ide_server.procs import Watcher
    procs_watcher = Watcher(root, _notify_mac)

    def _log_done(t: asyncio.Task) -> None:
        if not t.cancelled() and t.exception() is not None:
            log.error("tarea de fondo falló", exc_info=t.exception())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        tasks = [
            asyncio.create_task(watch_workspace(root, lambda: notify_box["fn"](), stop_event=stop_bg)),
            asyncio.create_task(poller.run(stop_bg)),
            asyncio.create_task(gh_reviews.run(stop_bg)),
            asyncio.create_task(limits.run(stop_bg)),
            asyncio.create_task(merger.run(stop_bg)),
            asyncio.create_task(merger.all.run(stop_bg)),
            asyncio.create_task(updater.run(stop_bg)),
            asyncio.create_task(save_history_loop(stop_bg)),
            asyncio.create_task(runs_watch(stop_bg)),
            asyncio.create_task(notify_box["fn"].nightly_loop(stop_bg)),
            *([] if os.environ.get("IDE_DB_PATH") else [asyncio.create_task(notify_box["fn"].notion_loop(stop_bg))]),
            # el vigilante de recursos (sin IA); no en un IDE de prueba (avisaría dos veces)
            *([] if os.environ.get("IDE_DB_PATH") else [asyncio.create_task(procs_watcher.run(stop_bg))]),
            # los navegadores de prueba compartidos (uno por perfil): se levantan y se reviven si se caen
            *([] if os.environ.get("IDE_DB_PATH") else [asyncio.create_task(browsers_loop(stop_bg))]),
            # con IDE_DB_PATH (un IDE de prueba contra una copia) no se conecta a Telegram: le robaría los
            # mensajes al IDE real (Telegram entrega cada mensaje a un solo getUpdates)
            *([asyncio.create_task(notify_box["fn"].telegram.run(stop_bg))]
              if notify_box["fn"].telegram and not os.environ.get("IDE_DB_PATH") else []),
        ]
        for t in tasks:
            t.add_done_callback(_log_done)
        try:
            yield
        finally:
            stop_bg.set()
            viewer.close_all()                  # los pgweb mueren con el server (sus claves también)
            try:
                hooks.save_history()            # la pantalla de cada claude, para después del reinicio
            except Exception:  # noqa: BLE001
                log.exception("no se pudo guardar el historial de las terminales")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if mlx_router is not None:
                await mlx_router.aclose()

    app = FastAPI(title="Agentic IDE", lifespan=lifespan)
    app.state.updater = updater
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/repos")
    async def api_repos() -> dict:
        return await registry.dispatch("repos.list", {})

    async def _http(channel: str, payload: dict):
        try:
            if payload.get("_http"):                    # el puerto de origen: para saber qué proceso llama
                payload = {**payload, "_peer": _peer_port.get()}
            return await registry.dispatch(channel, payload)
        except (SessionError, BranchOccupied) as exc:
            code = getattr(exc, "code", "branch_occupied")
            return JSONResponse({"code": code, "message": str(exc)}, status_code=409)
        except KeyError as exc:
            return JSONResponse({"code": "bad_request", "message": f"falta o no existe: {exc}"},
                                status_code=400)
        except Exception as exc:  # noqa: BLE001 — nunca silencioso
            return JSONResponse({"code": "handler_error", "message": str(exc)}, status_code=500)

    @app.get("/api/sessions")
    async def api_sessions():
        return await _http("sessions.tree", {})

    @app.post("/api/sessions")
    async def api_new(body: dict):
        return await _http("sessions.new", body)

    @app.post("/api/sessions/{sid}/open")
    async def api_open(sid: str):
        return await _http("sessions.open", {"id": sid})

    # -- diagnóstico de memoria (`ide debug memory`): cuánto ocupa el server y qué crece --------------------
    @app.get("/api/debug/memory")
    async def api_debug_memory(top: int = 25) -> dict:
        import gc, resource, sys, tracemalloc
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 if sys.platform == "darwin" else 1 / 1024)
        cur = None
        try:
            out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True, timeout=5)
            cur = int(out.stdout.strip()) * 1024
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        res = {"pid": os.getpid(), "rssMB": round((cur or 0) / 2**20, 1), "maxRssMB": round(rss / 2**20, 1),
               "tasks": len(asyncio.all_tasks()), "websockets": len(manager._active),
               "gcObjects": len(gc.get_objects()), "tracemalloc": tracemalloc.is_tracing()}
        if tracemalloc.is_tracing():
            snap = tracemalloc.take_snapshot().filter_traces([tracemalloc.Filter(False, tracemalloc.__file__)])
            base = getattr(app.state, "mem_base", None)
            stats = snap.compare_to(base, "lineno") if base else snap.statistics("lineno")
            res["top"] = [{"where": str(st.traceback[0]), "MB": round(st.size / 2**20, 2),
                           "growMB": round(getattr(st, "size_diff", 0) / 2**20, 2), "count": st.count}
                          for st in stats[:top]]
        return res

    @app.post("/api/debug/tracemalloc")
    async def api_debug_tracemalloc(body: dict) -> dict:
        """{on: true} empieza a rastrear (y toma la foto base para comparar); {on: false} lo apaga."""
        import tracemalloc
        if body.get("on"):
            if not tracemalloc.is_tracing():
                tracemalloc.start(1)
            app.state.mem_base = tracemalloc.take_snapshot()
        else:
            tracemalloc.stop()
            app.state.mem_base = None
        return {"tracemalloc": tracemalloc.is_tracing()}

    @app.post("/api/reviews/verdict")
    async def api_review_verdict(body: dict):
        return await _http("review.verdict", body)

    @app.post("/api/reviews/stack")
    async def api_review_stack(body: dict):
        return await _http("reviews.startStack", {**body, "_http": True})

    @app.get("/api/sessions/{sid}/evidence")
    async def api_evidence(sid: str):
        return await _http("evidence.list", {"id": sid})

    @app.post("/api/sessions/{sid}/evidence")
    async def api_evidence_new(sid: str, body: dict):
        return await _http("evidence.new", {"label": body.get("label"), "markdown": body.get("markdown") or "", "id": sid})

    @app.post("/api/sessions/{sid}/evidence/shot")
    async def api_evidence_shot(sid: str, body: dict):
        return await _http("evidence.shot", {**body, "id": sid})

    @app.post("/api/sessions/{sid}/evidence/github")
    async def api_evidence_github(sid: str, body: dict):
        return await _http("evidence.github", {**body, "id": sid})

    @app.post("/api/sessions/{sid}/evidence/delete")
    async def api_evidence_delete(sid: str, body: dict):
        return await _http("evidence.delete", {**body, "id": sid})

    @app.post("/api/sessions/{sid}/evidence/save")
    async def api_evidence_save(sid: str, body: dict):
        return await _http("evidence.save", {**body, "id": sid})

    @app.get("/api/sessions/archived")
    async def api_sessions_archived():
        return await _http("sessions.archived", {})

    @app.post("/api/sessions/archive")
    async def api_sessions_archive(body: dict):
        return await _http("sessions.archive", {**body, "_http": True})

    @app.post("/api/devs/hide")
    async def api_devs_hide(body: dict):
        return await _http("dev.hide", body)

    @app.post("/api/sessions/unarchive")
    async def api_sessions_unarchive(body: dict):
        return await _http("sessions.unarchive", {**body, "_http": True})

    @app.post("/api/devs/{sid}/ticket")
    async def api_ticket(sid: str, body: dict):
        return await _http("dev.ticketSet", {**body, "id": sid})

    @app.post("/api/devs/{sid}/pending-ticket")
    async def api_pending_ticket(sid: str, body: dict):
        return await _http("dev.ticketPending", {**body, "id": sid})

    @app.post("/api/admin/migrate-ids")
    async def api_migrate_ids(body: dict):
        return await _http("admin.migrateIds", {**body, "_http": True})

    @app.get("/api/merges")
    async def api_merges():
        return await _http("merges.list", {})

    @app.post("/api/merge")
    async def api_merge(body: dict):
        return await _http("reviews.merge", {**body, "_http": True})

    # enfocar una sesión en la UI (el click de una notificación): a todas las ventanas abiertas, y queda 30 s
    # para una que se abra recién (la app instalada que estaba cerrada)
    ui_focus: dict = {"id": None, "at": 0.0}

    @app.post("/api/ui/focus")
    async def api_ui_focus(body: dict):
        import time as _t
        from ide_server.sessions_fs import require_plain_name
        sid = require_plain_name(str(body.get("id") or ""), "sesión")
        ui_focus.update(id=sid, at=_t.time())
        await manager.broadcast("ui.focus", {"id": sid})
        return {"ok": True}

    @app.get("/api/ui/focus")
    async def api_ui_focus_get():
        import time as _t
        return {"id": ui_focus["id"] if _t.time() - ui_focus["at"] < 30 else None}

    @app.get("/api/later")
    async def api_later(all: bool = False):
        return await _http("later.list", {"all": all})

    @app.post("/api/later/{item_id}/resolve")
    async def api_later_resolve(item_id: str, body: dict):
        return await _http("later.resolve", {**body, "id": item_id})

    @app.post("/api/later")
    async def api_later_add(body: dict):
        return await _http("later.add", body)

    @app.post("/api/sessions/{sid}/activity")
    async def api_activity(sid: str, body: dict):
        return await _http("sessions.activity", {**body, "id": sid})

    @app.post("/api/sessions/{sid}/send")
    async def api_send(sid: str, body: dict):
        return await _http("sessions.send", {**body, "id": sid, "_http": True})

    def _sniff(f: Path) -> str | None:
        """Tipo por el contenido (archivos sin extensión, p.ej. renombrados a mano)."""
        with open(f, "rb") as fh:
            head = fh.read(16)
        for magic, mime in ((b"\x89PNG", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF8", "image/gif"),
                            (b"%PDF", "application/pdf")):
            if head.startswith(magic):
                return mime
        return "image/webp" if head[:4] == b"RIFF" and head[8:12] == b"WEBP" else None

    @app.get("/api/sessions/{sid}/attachments/{name:path}")
    async def api_attachment(sid: str, name: str, download: int = 0, view: str = ""):
        """Un adjunto de la sesión (vista previa o descarga; `name` puede tener carpetas). /api: mismos
        chequeos de origen. `view=html`: un .html como página (en el navegador), aislado del IDE."""
        from fastapi.responses import FileResponse
        from ide_server.sessions_fs import attachment_path, require_plain_name, session_path
        try:
            f = attachment_path(session_path(root, require_plain_name(sid, "sesión")) / "attachments", name)
        except Exception:
            return JSONResponse({"code": "bad_request", "message": "nombre inválido"}, status_code=400)
        if not f.is_file():
            return JSONResponse({"code": "not_found", "message": "no existe"}, status_code=404)
        # descarga: siempre como adjunto. Vista: nosniff, y todo lo que no es PDF/imagen va en sandbox
        # (un .html o .svg adjunto no corre en el origen del IDE); el visor de PDF no funciona en sandbox
        import mimetypes
        mime = mimetypes.guess_type(f.name)[0] or _sniff(f) or "application/octet-stream"
        safe = mime == "application/pdf" or (mime.startswith("image/") and mime != "image/svg+xml")
        headers = {"X-Content-Type-Options": "nosniff"}
        if view == "html" and mime == "text/html" and not download:
            # se ve como página (corre su JS), pero en sandbox sin allow-same-origin: su origen es opaco, no
            # el del IDE (no lee su almacenamiento y el chequeo de Origin le rechaza la API y el websocket)
            headers["Content-Security-Policy"] = "sandbox allow-scripts allow-forms allow-popups allow-modals"
            return FileResponse(f, media_type="text/html", content_disposition_type="inline", headers=headers)
        if not safe:
            headers["Content-Security-Policy"] = "sandbox; default-src 'none'; style-src 'unsafe-inline'"
        return FileResponse(f, filename=f.name if download else None, media_type=mime if safe or download else "text/plain",
                            content_disposition_type="attachment" if download else "inline", headers=headers)

    @app.post("/api/sessions/{sid}/propose")
    async def api_propose(sid: str, body: dict):
        return await _http("sessions.propose", {**body, "id": sid})

    @app.post("/api/telegram/reply")
    async def api_tg_reply(body: dict):
        return await _http("telegram.reply", body)

    @app.post("/api/manager/nightly")
    async def api_nightly():
        return await _http("manager.nightly", {})

    @app.get("/api/devs")
    async def api_devs():
        return await _http("dev.list", {})

    @app.get("/api/devs/{dev_id}")
    async def api_dev(dev_id: str):
        return await _http("dev.show", {"id": dev_id})

    @app.get("/api/devs/{sid}/servers")
    async def api_servers(sid: str):
        return await _http("servers.blocks", {"id": sid})

    @app.post("/api/devs/{sid}/servers/{action}")
    async def api_servers_action(sid: str, action: str, body: dict):
        if action not in ("start", "stop", "log"):
            return JSONResponse({"code": "bad_request", "message": "start | stop | log"}, status_code=400)
        return await _http(f"servers.{action}", {**body, "id": sid})

    @app.get("/api/deps")
    async def api_deps(pr: str):
        return await _http("dep.list", {"pr": pr})

    @app.post("/api/deps/{action}")
    async def api_deps_change(action: str, body: dict):
        if action not in ("add", "rm"):
            return JSONResponse({"code": "bad_request", "message": "add | rm"}, status_code=400)
        return await _http(f"dep.{action}", body)

    @app.post("/api/devs/{sid}/link")
    async def api_dev_link(sid: str, body: dict):
        return await _http("dev.linkPr", {**body, "id": sid, "_http": True})

    @app.post("/api/devs/{sid}/unlink")
    async def api_dev_unlink(sid: str, body: dict):
        return await _http("dev.unlinkPr", {**body, "id": sid, "_http": True})

    @app.post("/api/devs/{sid}/status")
    async def api_dev_status(sid: str, body: dict):
        return await _http("dev.status", {**body, "id": sid})

    @app.post("/api/sessions/{sid}/stop")
    async def api_stop(sid: str):
        return await _http("sessions.stop", {"id": sid})

    def _origin_ok(conn) -> bool:
        """Los navegadores dejan a cualquier página abrir un WebSocket o hacer un POST simple a
        localhost (CORS no lo frena): solo se acepta la propia UI (mismo host) o los orígenes de
        dev. Sin Origin = cliente no navegador (CLI), se acepta."""
        # Host loopback siempre: si no, un dominio que resuelve a 127.0.0.1 (DNS rebinding) tendría
        # Origin == Host y pasaría el chequeo de "mismo host".
        host = conn.headers.get("host", "")
        if urlparse(f"//{host}").hostname not in LOOPBACK:
            return False
        origin = conn.headers.get("origin")
        if origin is None:
            return True
        return urlparse(origin).netloc == host or origin in settings.cors_origins

    @app.middleware("http")
    async def _same_origin(request, call_next):
        _peer_port.set(request.client.port if request.client else None)
        if request.url.path.startswith("/api/") and not _origin_ok(request):
            log.warning("request rechazada: Origin %s", request.headers.get("origin"))
            return JSONResponse({"code": "forbidden_origin", "message": "origen no permitido"},
                                status_code=403)
        return await call_next(request)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        if not _origin_ok(ws):
            log.warning("WebSocket rechazado: Origin %s", ws.headers.get("origin"))
            await ws.close(code=1008)
            return
        # el websocket es de la UI (la CLI va por HTTP): una sesión no se conecta, o podría abrir una terminal
        # «tuya» (las que abres en el módulo Terminal cuentan como tu terminal) y escribir en ella
        from ide_server import peer
        claude = {hooks.pid_of(t) for t in supervisor.snapshot_tids()} - {None} if hooks.pid_of else set()
        why = await asyncio.to_thread(peer.ws_rejected, ws.client.port if ws.client else None, claude)
        if why:
            log.warning("WebSocket rechazado: %s", why)
            await ws.close(code=1008)
            return
        await manager.connect(ws)
        pending: set[asyncio.Task] = set()

        async def answer(raw: str) -> None:
            try:
                await ws.send_text(await handle_message(raw, registry))
            except (WebSocketDisconnect, RuntimeError):
                pass                            # se cerró mientras respondía

        try:
            while True:
                raw = await ws.receive_text()
                # La terminal (teclas, resize) se atiende en el acto y en orden; el resto (git, gh: el
                # módulo Stack tarda segundos) corre aparte: antes un pedido lento dejaba en fila las
                # teclas y claude parecía colgado.
                if '"channel": "terminal.' in raw or '"channel":"terminal.' in raw:
                    await answer(raw)
                else:
                    t = asyncio.create_task(answer(raw))
                    pending.add(t)
                    t.add_done_callback(pending.discard)
        except WebSocketDisconnect:
            manager.disconnect(ws)
            for t in pending:
                t.cancel()

    if web_dir is not None and (web_dir / "index.html").is_file():
        from starlette.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
