from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.responses import JSONResponse
from ide_server.capabilities import folder_sessions as folder_cap
from ide_server.config import sessions_config, reviews_config
from ide_server.pr_poller import PrPoller
from ide_server.sessions_fs import SessionError
from ide_server.supervisor import Supervisor
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
        on_change=lambda: notify_box["fn"]())
    poller = PrPoller(root, interval=reviews_config(root)["poll_interval"],
                      on_change=lambda: notify_box["fn"]())
    notify_box["fn"] = folder_cap.register(registry, root, manager, hooks=hooks,
                                           supervisor=supervisor, poller=poller)
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

    stop_bg = asyncio.Event()

    def _log_done(t: asyncio.Task) -> None:
        if not t.cancelled() and t.exception() is not None:
            log.error("tarea de fondo falló", exc_info=t.exception())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        tasks = [
            asyncio.create_task(watch_workspace(root, lambda: notify_box["fn"](), stop_event=stop_bg)),
            asyncio.create_task(poller.run(stop_bg)),
        ]
        for t in tasks:
            t.add_done_callback(_log_done)
        try:
            yield
        finally:
            stop_bg.set()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if mlx_router is not None:
                await mlx_router.aclose()

    app = FastAPI(title="Agentic IDE", lifespan=lifespan)
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
            return await registry.dispatch(channel, payload)
        except (SessionError, BranchOccupied) as exc:
            code = getattr(exc, "code", "branch_occupied")
            return JSONResponse({"code": code, "message": str(exc)}, status_code=409)
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

    @app.post("/api/sessions/{sid}/stop")
    async def api_stop(sid: str):
        return await _http("sessions.stop", {"id": sid})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        try:
            while True:
                raw = await ws.receive_text()
                await ws.send_text(await handle_message(raw, registry))
        except WebSocketDisconnect:
            manager.disconnect(ws)

    if web_dir is not None and (web_dir / "index.html").is_file():
        from starlette.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
