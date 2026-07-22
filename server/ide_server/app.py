from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ide_server.config import Settings
from ide_server.plugins import Registry
from ide_server.bus import handle_message, ConnectionManager
from ide_server.capabilities import repos as repos_cap
from ide_server.capabilities import sessions as sessions_cap
from ide_server.capabilities import terminals as terminals_cap
from ide_server.capabilities import chat as chat_cap
from ide_server.capabilities import customizations as customizations_cap
from ide_server.capabilities import changes as changes_cap
from ide_server.capabilities import graphite as graphite_cap
from ide_server.capabilities import notion as notion_cap
from ide_server.capabilities import tasks as tasks_cap
from ide_server.capabilities import models as models_cap
from ide_server.capabilities import mlx_config as mlx_config_cap
from ide_server.mlx.orchestrator import build_mlx_router
from ide_server.models.downloader import ModelDownloader


def create_app(root: Path, web_dir: Path | None = None) -> FastAPI:
    settings = Settings()
    registry = Registry()
    repos_cap.register(registry, root)
    sessions_cap.register(registry, root)
    manager = ConnectionManager()
    terminals_cap.register(registry, root, manager)
    mlx_router = build_mlx_router(root)
    hub = chat_cap.register(registry, root, manager, mlx_router=mlx_router)
    customizations_cap.register(registry, root)
    changes_cap.register(registry, root)
    graphite_cap.register(registry, root)
    notion_cap.register(registry, root)
    tasks_cap.register(registry, root)
    downloader = ModelDownloader(manager)
    models_cap.register(registry, root, manager, downloader=downloader)
    mlx_config_cap.register(registry, root)

    app = FastAPI(title="Agentic IDE")
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.on_event("shutdown")
    async def _shutdown_mlx() -> None:
        if mlx_router is not None:
            await mlx_router.aclose()

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/repos")
    async def api_repos() -> dict:
        return await registry.dispatch("repos.list", {})

    @app.get("/api/sessions")
    async def api_sessions() -> dict:
        return await registry.dispatch("sessions.tree", {})

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
