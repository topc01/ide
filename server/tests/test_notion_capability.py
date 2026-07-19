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
    res = await reg.dispatch("notion.save", {"pageId": "b-page", "loaded": loaded, "edited": edited,
                                             "unsupportedIds": page["unsupportedIds"], "idMap": {}})
    assert res["patched"] == ["b1"] and res["failed"] == []
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
class _AuthError(RuntimeError):
    def __init__(self, status: int):
        super().__init__(str(status))
        self.status = status


@pytest.mark.asyncio
async def test_connect_invalid_token_not_persisted(tmp_path):
    # client_factory cuyo users.me() falla con un rechazo de auth (status 401)
    class _Bad:
        class _U:
            async def me(self): raise _AuthError(401)
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
async def test_connect_network_error_propagates(tmp_path):
    # error sin .status/.code (red/DNS caída) debe propagar, no confundirse con token inválido
    class _Bad:
        class _U:
            async def me(self): raise ConnectionError("network down")
        @property
        def users(self): return self._U()
    (tmp_path / ".ide").mkdir(exist_ok=True)
    home = tmp_path / "home3"; (home / ".ide").mkdir(parents=True)
    from ide_server.plugins import Registry
    from ide_server.capabilities import notion as notion_cap
    reg = Registry(); notion_cap.register(reg, tmp_path, home=home, client_factory=lambda t: _Bad())
    with pytest.raises(ConnectionError):
        await reg.dispatch("notion.connect", {"token": "x"})
    assert not (home / ".ide" / "config.toml").exists()


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


# --- Fase 2: save estructural + setTitle ---

def _registry_with_notion(tmp_path, client_factory, token="secret"):
    # Mismo mecanismo que `_reg`: token en home/.ide/config.toml + client_factory inyectado.
    (tmp_path / ".ide").mkdir(exist_ok=True)
    home = tmp_path / "home"; (home / ".ide").mkdir(parents=True)
    if token:
        (home / ".ide" / "config.toml").write_text(f'[notion]\ntoken="{token}"\n')
    reg = Registry()
    notion_cap.register(reg, tmp_path, home=home, client_factory=client_factory)
    return reg


def _p(bid, text):
    return {"id": bid, "type": "paragraph", "props": {},
            "content": [{"type": "text", "text": text, "styles": {}}]}


@pytest.mark.asyncio
async def test_save_aplica_append_delete_patch(tmp_path, monkeypatch):
    # Fake client que registra las llamadas y mintea ids incrementales
    calls = []

    class Children:
        async def append(self, **kw):
            calls.append(("append", kw.get("after")))
            return {"results": [{"id": f"mint{len(calls)}"}]}

    class Blocks:
        children = Children()
        async def update(self, **kw):
            calls.append(("patch", kw["block_id"]))
        async def delete(self, **kw):
            calls.append(("delete", kw["block_id"]))

    class Users:
        async def me(self):
            return {}

    class FakeClient:
        blocks = Blocks()
        users = Users()

    registry = _registry_with_notion(tmp_path, client_factory=lambda tok: FakeClient(),
                                      token="secret")  # helper del archivo; ver Fase 1
    loaded = [_p("n1", "uno"), _p("n2", "dos")]
    edited = [_p("n1", "UNO"), _p("c3", "tres")]        # patch n1, borra n2, agrega c3
    res = await registry.dispatch("notion.save", {
        "pageId": "pg", "loaded": loaded, "edited": edited, "unsupportedIds": [], "idMap": {}})
    assert res["patched"] == ["n1"]
    assert res["deleted"] == ["n2"]
    # diff_ops (ya implementado en Fase 2 Task 1) ordena los ops como
    # [patch n1, append c3, delete n2]; `calls` es compartida entre los tres
    # tipos de llamada del fake, así que al ejecutarse el append ya hubo 1
    # llamada previa (el patch) -> el id minteado es "mint2", no "mint1".
    assert res["appended"] == [{"clientId": "c3", "notionId": "mint2"}]
    assert res["failed"] == []


@pytest.mark.asyncio
async def test_save_encadena_after_de_nuevos_consecutivos(tmp_path):
    calls = []

    class Children:
        async def append(self, **kw):
            calls.append(kw.get("after"))
            return {"results": [{"id": f"mint{len(calls)}"}]}

    class Blocks:
        children = Children()
        async def update(self, **kw): ...
        async def delete(self, **kw): ...

    class Users:
        async def me(self): return {}

    class FakeClient:
        blocks = Blocks()
        users = Users()

    registry = _registry_with_notion(tmp_path, client_factory=lambda tok: FakeClient(),
                                      token="secret")
    loaded = [_p("n1", "uno")]
    edited = [_p("n1", "uno"), _p("c2", "dos"), _p("c3", "tres")]
    res = await registry.dispatch("notion.save", {
        "pageId": "pg", "loaded": loaded, "edited": edited, "unsupportedIds": [], "idMap": {}})
    # c2 -> after n1 ; c3 -> after el id minteado de c2 (mint1)
    assert calls == ["n1", "mint1"]
    assert res["appended"] == [{"clientId": "c2", "notionId": "mint1"},
                               {"clientId": "c3", "notionId": "mint2"}]


@pytest.mark.asyncio
async def test_save_op_fallida_no_corta_el_resto(tmp_path):
    class Blocks:
        async def update(self, **kw):
            raise RuntimeError("boom")
        async def delete(self, **kw): ...
        class children:
            @staticmethod
            async def append(**kw):
                return {"results": [{"id": "m"}]}

    class Users:
        async def me(self): return {}

    class FakeClient:
        blocks = Blocks()
        users = Users()

    registry = _registry_with_notion(tmp_path, client_factory=lambda tok: FakeClient(),
                                      token="secret")
    loaded = [_p("n1", "uno"), _p("n2", "dos")]
    edited = [_p("n1", "UNO"), _p("n2", "dos"), _p("c3", "tres")]  # patch falla, append ok
    res = await registry.dispatch("notion.save", {
        "pageId": "pg", "loaded": loaded, "edited": edited, "unsupportedIds": [], "idMap": {}})
    assert res["appended"] == [{"clientId": "c3", "notionId": "m"}]
    assert len(res["failed"]) == 1 and res["failed"][0]["op"] == "patch"


@pytest.mark.asyncio
async def test_set_title_llama_pages_update(tmp_path):
    captured = {}

    class Pages:
        async def update(self, **kw):
            captured.update(kw)

    class Users:
        async def me(self): return {}

    class FakeClient:
        pages = Pages()
        users = Users()

    registry = _registry_with_notion(tmp_path, client_factory=lambda tok: FakeClient(),
                                      token="secret")
    res = await registry.dispatch("notion.setTitle", {"pageId": "pg", "title": "Nuevo"})
    assert res == {"ok": True}
    assert captured["properties"]["title"]["title"][0]["text"]["content"] == "Nuevo"
