from __future__ import annotations
from dataclasses import dataclass

_SENTINEL = "ROUTE_TO_CLAUDE"


@dataclass
class RouteDecision:
    route: str            # "local" | "claude"
    reply: str | None
    degraded: bool = False


def parse_route(text: str) -> tuple[str, str | None]:
    stripped = (text or "").strip()
    if stripped == _SENTINEL:
        return ("claude", None)
    return ("local", text)


class PromptRouter:
    def __init__(self, client, router_prompt: str) -> None:
        self._client = client
        self._prompt = router_prompt

    async def route(self, text: str) -> RouteDecision:
        reply = await self._client.chat([
            {"role": "system", "content": self._prompt},
            {"role": "user", "content": text},
        ])
        route, local_reply = parse_route(reply)
        return RouteDecision(route=route, reply=local_reply)

    async def answer(self, text: str) -> str:
        # respuesta directa del modelo local (sin clasificar) — para el override "forzar local"
        return await self._client.chat([
            {"role": "system", "content": "Respondé de forma directa y concisa."},
            {"role": "user", "content": text},
        ])
