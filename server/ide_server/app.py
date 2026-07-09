from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ide_server.config import Settings
from ide_server.plugins import Registry
from ide_server.bus import handle_message, ConnectionManager
from ide_server.capabilities import repos as repos_cap


def create_app(root: Path) -> FastAPI:
    settings = Settings()
    registry = Registry()
    repos_cap.register(registry, root)
    manager = ConnectionManager()

    app = FastAPI(title="Agentic IDE")
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

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        try:
            while True:
                raw = await ws.receive_text()
                await ws.send_text(await handle_message(raw, registry))
        except WebSocketDisconnect:
            manager.disconnect(ws)

    return app
