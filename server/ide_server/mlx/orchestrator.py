from __future__ import annotations
from pathlib import Path
from ide_server.mlx.config import mlx_config
from ide_server.mlx.server import MlxServer, MlxUnavailable
from ide_server.mlx.client import MlxClient
from ide_server.mlx.router import PromptRouter, RouteDecision


class MlxRouter:
    def __init__(self, server, router_factory) -> None:
        # router_factory(base_url) -> objeto con async route(text) -> RouteDecision
        self._server = server
        self._router_factory = router_factory

    async def decide(self, text: str) -> RouteDecision:
        try:
            url = await self._server.ensure_running()
        except MlxUnavailable:
            return RouteDecision(route="claude", reply=None, degraded=True)
        return await self._router_factory(url).route(text)


def build_mlx_router(root: Path) -> MlxRouter | None:
    cfg = mlx_config(root)
    if cfg is None:
        return None
    server = MlxServer(cfg.model, find_port=(lambda h, s: cfg.port) if cfg.port else None)
    return MlxRouter(server, lambda url: PromptRouter(MlxClient(url), cfg.router_prompt))
