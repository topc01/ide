import pytest
from ide_server.notion.client import fetch_page, patch_block_text
from ide_server.notion.queue import RateLimited


class _FakeChildren:
    def __init__(self, pages): self._pages = pages; self.calls = []
    async def list(self, **kw):
        self.calls.append(kw)
        # devuelve 1 página por llamada según cursor
        idx = 0 if kw.get("start_cursor") is None else int(kw["start_cursor"])
        return self._pages[idx]


class _FakeBlocks:
    def __init__(self, pages): self.children = _FakeChildren(pages); self.updated = []
    async def update(self, **kw): self.updated.append(kw)


class _FakePages:
    async def retrieve(self, **kw):
        return {"properties": {"title": {"type": "title",
                "title": [{"plain_text": "Mi Página"}]}}}


class _FakeClient:
    def __init__(self, pages):
        self.blocks = _FakeBlocks(pages); self.pages = _FakePages()


@pytest.mark.asyncio
async def test_fetch_page_paginates_and_titles():
    pages = [
        {"results": [{"id": "b1", "type": "paragraph", "paragraph": {"rich_text": []}, "has_children": False}],
         "next_cursor": "1", "has_more": True},
        {"results": [{"id": "b2", "type": "paragraph", "paragraph": {"rich_text": []}, "has_children": False}],
         "next_cursor": None, "has_more": False},
    ]
    client = _FakeClient(pages)
    out = await fetch_page(client, "page-x")
    assert out["title"] == "Mi Página"
    assert [b["id"] for b in out["blocks"]] == ["b1", "b2"]
    assert len(client.blocks.children.calls) == 2      # paginó


@pytest.mark.asyncio
async def test_patch_block_text_shape():
    client = _FakeClient([])
    await patch_block_text(client, "b1", "heading_2", [{"text": {"content": "x"}}])
    assert client.blocks.updated == [{"block_id": "b1", "heading_2": {"rich_text": [{"text": {"content": "x"}}]}}]


class _RateLimitedError(Exception):
    def __init__(self, status=429, code=None, headers=None):
        super().__init__("rate limited")
        self.status = status
        self.code = code
        self.headers = headers or {}


class _FakeBlocksRaising:
    def __init__(self, exc):
        self._exc = exc
        self.children = None

    async def update(self, **kw):
        raise self._exc


class _FakeClientRaising:
    def __init__(self, exc):
        self.blocks = _FakeBlocksRaising(exc)


@pytest.mark.asyncio
async def test_patch_block_text_429_raises_rate_limited():
    exc = _RateLimitedError(status=429, headers={"Retry-After": "2"})
    client = _FakeClientRaising(exc)
    with pytest.raises(RateLimited) as exc_info:
        await patch_block_text(client, "b1", "paragraph", [])
    assert exc_info.value.retry_after == 2.0


@pytest.mark.asyncio
async def test_patch_block_text_non_429_propagates():
    exc = _RateLimitedError(status=400)
    client = _FakeClientRaising(exc)
    with pytest.raises(_RateLimitedError):
        await patch_block_text(client, "b1", "paragraph", [])
