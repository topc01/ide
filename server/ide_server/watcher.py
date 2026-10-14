from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


def relevant(root: Path, path: str) -> bool:
    ide = (root / ".ide").resolve()
    p = Path(path)
    # Resolve only the parent so a repo symlink entry (sessions/<id>/<repo> -> worktrees/...)
    # keeps its own name inside sessions/, while files reached through it still resolve
    # into worktrees/ and are ignored.
    try:
        rel = (p.parent.resolve() / p.name).relative_to(ide).parts
    except ValueError:
        try:
            rel = p.relative_to(root / ".ide").parts
        except ValueError:
            return False
    if not rel:
        return False
    if rel[0] == "scripts":
        return True
    return rel[0] == "sessions" and len(rel) <= 3


async def watch_workspace(root: Path, on_change: Callable[[], None], *,
                          stop_event: asyncio.Event, debounce_ms: int = 300) -> None:
    from watchfiles import awatch
    paths = [root / ".ide" / "sessions", root / ".ide" / "scripts"]
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
    async for _ in awatch(*paths, debounce=debounce_ms, stop_event=stop_event,
                          watch_filter=lambda _c, path: relevant(root, path)):
        try:
            on_change()
        except Exception:
            log.exception("on_change falló; el watcher sigue activo")
