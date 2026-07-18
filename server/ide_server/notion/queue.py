from __future__ import annotations
import asyncio
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class RateLimited(Exception):
    def __init__(self, retry_after: float = 1.0) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after


class RateLimitedRunner:
    def __init__(self, rate_per_sec: float = 3.0, sleep=asyncio.sleep, now=time.monotonic) -> None:
        self._min_gap = 1.0 / rate_per_sec
        self._sleep = sleep
        self._now = now
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def run(self, coro_fn: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:                       # serializa
            gap = self._min_gap - (self._now() - self._last)
            if gap > 0:
                await self._sleep(gap)
            while True:
                try:
                    result = await coro_fn()
                    self._last = self._now()
                    return result
                except RateLimited as exc:
                    await self._sleep(exc.retry_after)
