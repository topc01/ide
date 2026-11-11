from __future__ import annotations
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable
from ide_server.sessions_fs import list_sessions

GhRunner = Callable[[list[str]], Awaitable[tuple[int, str, str]]]
GH_TIMEOUT = 60
log = logging.getLogger(__name__)


async def _default_gh(args: list[str]) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        return 127, "", "gh no está instalado"
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=GH_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"gh timeout ({GH_TIMEOUT}s)"
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
        # la PR de una revisión tiene commits nuevos (`prState` stale): quien lo atiende (mover el worktree)
        self.on_stale: Callable[[str, str | None], Awaitable[None]] | None = None

    async def _poll(self, s: dict) -> tuple[str, dict]:
        prev = self.derived.get(s["id"], {"prState": None, "pollError": None, "lastOk": None})
        try:
            async with self._sem:
                code, out, err = await self._gh(
                    ["pr", "view", s["prUrl"], "--json", "headRefOid,state,latestReviews,reviewRequests"])
            if code != 0:
                return s["id"], {**prev, "pollError": err.strip() or f"gh exit {code}"}
            data = json.loads(out)
            if not isinstance(data, dict):
                raise ValueError("se esperaba un objeto JSON")
            state = {"MERGED": "merged", "CLOSED": "closed"}.get(data.get("state", ""))
            if state is None and data.get("headRefOid") != s.get("reviewedSha"):
                state = "stale"
        except Exception as exc:  # cualquier fallo queda marcado, nunca silencioso
            msg = str(exc) or type(exc).__name__
            return s["id"], {**prev, "pollError": f"respuesta inválida de gh: {msg}"}
        # el estado de cada revisor (para el estado de la sesión cuando la PR no está en tus listas de GitHub:
        # p. ej. una PR ajena que ya aprobaste no sale ni en Pendientes ni en Pedí cambios)
        reviews = {r["author"]["login"]: {"APPROVED": "approved", "CHANGES_REQUESTED": "changes"}.get(r.get("state"))
                   for r in data.get("latestReviews") or [] if (r.get("author") or {}).get("login")}
        for r in data.get("reviewRequests") or []:
            if r.get("login"):
                reviews[r["login"]] = "requested"
        ts = datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(timespec="seconds")
        return s["id"], {"prState": state, "pollError": None, "lastOk": ts, "reviewers": reviews,
                         "headSha": data.get("headRefOid")}

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
            try:
                if await self.poll_once():
                    self._on_change()
                if self.on_stale is not None:
                    for sid, d in list(self.derived.items()):
                        if d.get("prState") == "stale":
                            await self.on_stale(sid, d.get("headSha"))
            except Exception:
                log.exception("el poller de PRs falló en un ciclo; sigue en el próximo")
            try:
                await asyncio.wait_for(stop.wait(), self.next_delay())
            except asyncio.TimeoutError:
                pass
