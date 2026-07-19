import json
import pytest
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.capabilities import notion as notion_cap


class _FakeClient:
    def __init__(self, users_me_raises=False):
        self.updated = []
        self._users_me_raises = users_me_raises
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
    @property
    def users(self):
        outer = self
        class _U:
            async def me(self):
                if outer._users_me_raises:
                    raise RuntimeError("token inválido")
                return {"id": "u1"}
        return _U()


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


@pytest.mark.asyncio
async def test_health_users_me_raises(tmp_path):
    (tmp_path / ".ide").mkdir(exist_ok=True)
    home = tmp_path / "home"; (home / ".ide").mkdir(parents=True)
    (home / ".ide" / "config.toml").write_text('[notion]\ntoken="tok"\n')
    fake = _FakeClient(users_me_raises=True)
    reg = Registry()
    notion_cap.register(reg, tmp_path, home=home, client_factory=lambda t: fake)
    assert (await reg.dispatch("notion.health", {}))["connected"] is False


@pytest.mark.asyncio
async def test_connect_valid_token_persists(tmp_path):
    # sin token al inicio
    reg, fake = _reg(tmp_path, token="")
    assert (await reg.dispatch("notion.health", {}))["connected"] is False
    out = await reg.dispatch("notion.connect", {"token": "secret-xyz"})
    assert out["connected"] is True
    # persistió en el home global de _reg → health ahora true
    assert (await reg.dispatch("notion.health", {}))["connected"] is True


@pytest.mark.asyncio
async def test_connect_invalid_token_not_persisted(tmp_path):
    # client_factory cuyo users.me() falla
    class _Bad:
        class _U:
            async def me(self): raise RuntimeError("401")
        @property
        def users(self): return self._U()
    (tmp_path / ".ide").mkdir(exist_ok=True)
    home = tmp_path / "home2"; (home / ".ide").mkdir(parents=True)
    from ide_server.plugins import Registry
    from ide_server.capabilities import notion as notion_cap
    reg = Registry(); notion_cap.register(reg, tmp_path, home=home, client_factory=lambda t: _Bad())
    out = await reg.dispatch("notion.connect", {"token": "bad"})
    assert out["connected"] is False
    assert not (home / ".ide" / "config.toml").exists() or "token" not in (home / ".ide" / "config.toml").read_text()


@pytest.mark.asyncio
async def test_connect_empty_token(tmp_path):
    reg, _ = _reg(tmp_path, token="")
    assert (await reg.dispatch("notion.connect", {"token": ""}))["connected"] is False


@pytest.mark.asyncio
async def test_disconnect_clears(tmp_path):
    reg, _ = _reg(tmp_path, token="preset")   # _reg escribe el token global
    assert (await reg.dispatch("notion.health", {}))["connected"] is True
    await reg.dispatch("notion.disconnect", {})
    assert (await reg.dispatch("notion.health", {}))["connected"] is False
