from __future__ import annotations
from pathlib import Path
from .config import mlx_config
from .server import MlxServer, MlxUnavailable
from .client import MlxClient
from .router import PromptRouter, RouteDecision
from typing import Callable, Protocol


class RouterLike(Protocol):
    async def route(self, text: str) -> RouteDecision: ...


RouterFactory = Callable[[str], RouterLike]


class MlxRouter:
    def __init__(self, server: MlxServer, router_factory: RouterFactory) -> None:
        # router_factory(base_url) -> objeto con async route(text) -> RouteDecision
        self._server = server
        self._router_factory = router_factory

    async def decide(self, text: str) -> RouteDecision:
        try:
            url = await self._server.ensure_running()
        except MlxUnavailable:
            return RouteDecision(route="claude", reply=None, degraded=True)
        return await self._router_factory(url).route(text)

    async def aclose(self) -> None:
        self._server.stop()


def build_mlx_router(root: Path) -> MlxRouter | None:
    cfg = mlx_config(root)
    if cfg is None:
        return None
    find_port: Callable[[str, int], int] | None = None
    if cfg.port is not None:
        port = cfg.port
        find_port = lambda h, s: port
    server = MlxServer(cfg.model, find_port=find_port)
    router_factory: RouterFactory = lambda url: PromptRouter(
        MlxClient(url, model=cfg.model), cfg.router_prompt)
    return MlxRouter(server, router_factory=router_factory)
