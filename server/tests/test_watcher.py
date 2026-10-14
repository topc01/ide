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


def test_relevant_keeps_repo_symlink_entry(tmp_path):
    wt = tmp_path / ".ide" / "worktrees" / "a" / "repo-a"
    (wt / "src").mkdir(parents=True)
    (wt / "src" / "x.py").write_text("x")
    link = tmp_path / ".ide" / "sessions" / "a" / "repo-a"
    link.parent.mkdir(parents=True)
    link.symlink_to("../../worktrees/a/repo-a")
    assert relevant(tmp_path, str(link))
    assert not relevant(tmp_path, str(link / "src" / "x.py"))


def test_relevant_templates(tmp_path):
    assert relevant(tmp_path, str(tmp_path / ".ide" / "sessions" / "templates" / "ticket.md"))


@pytest.mark.asyncio
async def test_watch_survives_on_change_error(tmp_path):
    (tmp_path / ".ide" / "sessions" / "a").mkdir(parents=True)
    calls, stop = [], asyncio.Event()

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    task = asyncio.create_task(watch_workspace(tmp_path, flaky,
                                               stop_event=stop, debounce_ms=50))
    await asyncio.sleep(0.3)
    (tmp_path / ".ide" / "sessions" / "a" / "TICKET.md").write_text("1")
    for _ in range(40):
        if calls:
            break
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.3)
    (tmp_path / ".ide" / "sessions" / "a" / "TICKET2.md").write_text("2")
    for _ in range(40):
        if len(calls) >= 2:
            break
        await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(task, 3)
    assert len(calls) >= 2
