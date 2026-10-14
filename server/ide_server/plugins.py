from __future__ import annotations
from typing import Awaitable, Callable

Handler = Callable[[dict], Awaitable[dict]]


class UnknownChannel(Exception):
    """Canal sin handler (no es KeyError: un KeyError de un handler es otra cosa)."""


class Registry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, channel: str, handler: Handler) -> None:
        self._handlers[channel] = handler

    async def dispatch(self, channel: str, payload: dict) -> dict:
        if channel not in self._handlers:
            raise UnknownChannel(channel)
        return await self._handlers[channel](payload)
