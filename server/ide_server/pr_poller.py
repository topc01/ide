from __future__ import annotations
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable
from ide_server.sessions_fs import list_sessions

GhRunner = Callable[[list[str]], Awaitable[tuple[int, str, str]]]


async def _default_gh(args: list[str]) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        return 127, "", "gh no está instalado"
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(), err.decode()


class PrPoller:
    def __init__(self, root: Path, *, interval: int, run_gh: GhRunner | None = None,
                 on_change: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.time, concurrency: int = 4) -> None:
        self._root, self._interval = root, interval
        self._gh = run_gh or _default_gh
        self._on_change = on_change or (lambda: None)
        self._clock = clock
        self._sem = asyncio.Semaphore(concurrency)
        self._failures = 0
        self.derived: dict[str, dict] = {}

    async def _poll(self, s: dict) -> tuple[str, dict]:
        prev = self.derived.get(s["id"], {"prState": None, "pollError": None, "lastOk": None})
        async with self._sem:
            code, out, err = await self._gh(["pr", "view", s["prUrl"], "--json", "headRefOid,state"])
        if code != 0:
            return s["id"], {**prev, "pollError": err.strip() or f"gh exit {code}"}
        data = json.loads(out)
        state = {"MERGED": "merged", "CLOSED": "closed"}.get(data.get("state", ""))
        if state is None and data.get("headRefOid") != s.get("reviewedSha"):
            state = "stale"
        ts = datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(timespec="seconds")
        return s["id"], {"prState": state, "pollError": None, "lastOk": ts}

    async def poll_once(self) -> bool:
        reviews = [s for s in list_sessions(self._root)
                   if s["kind"] == "review" and s.get("prUrl")]
        results = dict(await asyncio.gather(*(self._poll(s) for s in reviews)))
        self._failures = self._failures + 1 if any(r["pollError"] for r in results.values()) else 0

        def key(d: dict) -> dict:
            return {k: v for k, v in d.items() if k != "lastOk"}
        changed = {k: key(v) for k, v in results.items()} != \
                  {k: key(v) for k, v in self.derived.items()}
        self.derived = results
        return changed

    def next_delay(self) -> float:
        if self._failures == 0:
            return float(self._interval)
        return float(min(self._interval * 2 ** self._failures, 4 * self._interval))

    async def run(self, stop: asyncio.Event) -> None:
        if self._interval <= 0:
            return
        while not stop.is_set():
            if await self.poll_once():
                self._on_change()
            try:
                await asyncio.wait_for(stop.wait(), self.next_delay())
            except asyncio.TimeoutError:
                pass
