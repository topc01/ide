import json
import pytest
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.capabilities import notion as notion_cap


class _FakeClient:
    def __init__(self):
        self.updated = []
    class _P:
        async def retrieve(self, **kw):
            return {"properties": {"t": {"type": "title", "title": [{"plain_text": "T"}]}}}
    class _CH:
        async def list(self, **kw):
            return {"results": [{"id": "b1", "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text",
                    "text": {"content": "hola", "link": None},
                    "annotations": {"bold": False, "italic": False, "strikethrough": False,
                    "underline": False, "code": False, "color": "default"}, "plain_text": "hola"}]},
                    "has_children": False}], "has_more": False, "next_cursor": None}
    @property
    def pages(self): return self._P()
    @property
    def blocks(self):
        outer = self
        class _B:
            children = _FakeClient._CH()
            async def update(self, **kw): outer.updated.append(kw)
        return _B()


def _reg(tmp_path, token="tok"):
    (tmp_path / ".ide").mkdir(exist_ok=True)
    home = tmp_path / "home"; (home / ".ide").mkdir(parents=True)
    if token:
        (home / ".ide" / "config.toml").write_text(f'[notion]\ntoken="{token}"\n')
    fake = _FakeClient()
    reg = Registry()
    notion_cap.register(reg, tmp_path, home=home, client_factory=lambda t: fake)
    return reg, fake


@pytest.mark.asyncio
async def test_health_and_add_list(tmp_path):
    reg, _ = _reg(tmp_path)
    assert (await reg.dispatch("notion.health", {}))["connected"] is True
    raw = "1234567890abcdef1234567890abcdef"
    await reg.dispatch("notion.add", {"url": f"https://notion.so/{raw}"})
    pages = (await reg.dispatch("notion.list", {}))["pages"]
    assert pages[0]["title"] == "T"


@pytest.mark.asyncio
async def test_page_and_save_text(tmp_path):
    reg, fake = _reg(tmp_path)
    page = await reg.dispatch("notion.page", {"id": "b-page"})
    assert page["title"] == "T" and page["blocks"][0]["id"] == "b1"
    loaded = page["blocks"]
    edited = [{**loaded[0], "content": [{"type": "text", "text": "chau", "styles": {}}]}]
    res = await reg.dispatch("notion.save", {"id": "b-page", "loaded": loaded, "edited": edited,
                                             "unsupportedIds": page["unsupportedIds"]})
    assert res["structural"] is False and res["failed"] == []
    assert fake.updated and fake.updated[0]["block_id"] == "b1"


@pytest.mark.asyncio
async def test_health_no_token(tmp_path):
    reg, _ = _reg(tmp_path, token="")
    assert (await reg.dispatch("notion.health", {}))["connected"] is False
