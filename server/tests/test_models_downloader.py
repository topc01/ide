import asyncio
import pytest
from ide_server.models.downloader import ModelDownloader


class FakeManager:
    def __init__(self): self.events = []
    async def broadcast(self, channel, payload): self.events.append((channel, payload))


@pytest.mark.asyncio
async def test_progress_then_done_and_cleanup():
    mgr = FakeManager()
    def dl(repo_id, state): state.downloaded = 100; state.total = 100
    d = ModelDownloader(mgr, download_fn=dl, poll_interval=0)
    await (await d.start("r1"))
    kinds = [p["kind"] for _, p in mgr.events]
    assert "progress" in kinds and kinds[-1] == "done"
    assert all(p["repoId"] == "r1" for _, p in mgr.events)
    assert all(ch == "models.event" for ch, _ in mgr.events)
    assert d.active() == {}


@pytest.mark.asyncio
async def test_error_emits_error_and_cleanup():
    mgr = FakeManager()
    def dl(repo_id, state): raise RuntimeError("boom")
    d = ModelDownloader(mgr, download_fn=dl, poll_interval=0)
    await (await d.start("r1"))
    assert any(p["kind"] == "error" and p["message"] == "boom" for _, p in mgr.events)
    assert d.active() == {}


@pytest.mark.asyncio
async def test_dedup_same_repo():
    mgr = FakeManager()
    started = {"n": 0}
    def dl(repo_id, state): started["n"] += 1
    d = ModelDownloader(mgr, download_fn=dl, poll_interval=0)
    t1 = await d.start("r1")
    t2 = await d.start("r1")                              # ya activo → dedup
    assert t2 is None
    await t1
    assert started["n"] == 1


@pytest.mark.asyncio
async def test_concurrent_two_repos():
    mgr = FakeManager()
    def dl(repo_id, state): state.downloaded = 1; state.total = 1
    d = ModelDownloader(mgr, download_fn=dl, poll_interval=0)
    t1 = await d.start("r1"); t2 = await d.start("r2")
    assert t2 is not None
    await asyncio.gather(t1, t2)
    assert {p["repoId"] for _, p in mgr.events} == {"r1", "r2"}
