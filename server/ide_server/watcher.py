from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Callable


def relevant(root: Path, path: str) -> bool:
    ide = (root / ".ide").resolve()
    try:
        rel = Path(path).resolve().relative_to(ide).parts
    except ValueError:
        try:
            rel = Path(path).relative_to(root / ".ide").parts
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
        on_change()
