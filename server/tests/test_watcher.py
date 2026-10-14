import asyncio
import pytest
from ide_server.watcher import relevant, watch_workspace


def test_relevant_filters_depth(tmp_path):
    s = tmp_path / ".ide" / "sessions"
    assert relevant(tmp_path, str(s / "a" / "TICKET.md"))
    assert relevant(tmp_path, str(s / "a"))
    assert relevant(tmp_path, str(tmp_path / ".ide" / "scripts" / "repo" / "run"))
    assert not relevant(tmp_path, str(s / "a" / "repo-a" / "src" / "x.py"))
    assert not relevant(tmp_path, str(tmp_path / ".ide" / "worktrees" / "a" / "f"))


@pytest.mark.asyncio
async def test_watch_reports_ticket_change(tmp_path):
    (tmp_path / ".ide" / "sessions" / "a").mkdir(parents=True)
    hits, stop = [], asyncio.Event()
    task = asyncio.create_task(watch_workspace(tmp_path, lambda: hits.append(1),
                                               stop_event=stop, debounce_ms=50))
    await asyncio.sleep(0.3)
    (tmp_path / ".ide" / "sessions" / "a" / "TICKET.md").write_text("---\nstatus: ready\n---\n")
    for _ in range(40):
        if hits:
            break
        await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(task, 3)
    assert hits
