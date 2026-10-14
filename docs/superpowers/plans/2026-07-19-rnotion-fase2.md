# Notion Fase 2 (edición estructural) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que agregar/borrar bloques y editar el título de una página de Notion persistan de
verdad, sin remontar el editor en el camino feliz.

**Architecture:** Se extiende el paquete `notion/` de Fase 1. Una función pura nueva `diff_ops`
produce ops `append/delete/patch` a partir de `loaded`, `edited`, `unsupportedIds` y un mapa
`clientId→notionId`. La capability `notion.save` las aplica en orden por el `RateLimitedRunner`,
minteando ids de Notion para los bloques nuevos y resolviendo el `after` de nuevos consecutivos.
El front mantiene el mapa `idMap`, hace el título editable, y solo re-fetch+remonta si hubo
fallos.

**Tech Stack:** Python/FastAPI + `notion-client` (AsyncClient) en backend; React + TS + BlockNote
+ vitest en frontend. Tests: `cd server && uv run pytest`, `cd ui && npm test`.

## Global Constraints

- **Sin fallos silenciosos.** Errores de transporte → envelope. Fallos por-op de Notion (429,
  permiso) viajan en `failed`, no como excepción global; nunca se traga un error.
- **Alcance: agregar + borrar + editar título. SIN reordenar.** No se mueve ningún bloque
  existente. El orden de bloques nuevos se logra con el `after` del APPEND.
- **Bloques no soportados (unsupportedIds) protegidos de borrado.** `diff_ops` NUNCA emite
  DELETE para un id en `unsupported_ids`.
- **No remontar el editor en el camino feliz.** El mapa `clientId→notionId` bridgea la
  identidad; el remount (`syncKey++`) queda solo para el path de error (re-fetch de reconciliación).
- **Commits atómicos, en español, conventional commits.** Un commit por tarea.
- **Idioma del código/tests: español** en nombres de test y mensajes, consistente con Fase 1.

---

### Task 1: `diff_ops` — función pura de diff estructural

**Files:**
- Modify: `server/ide_server/notion/adapter.py` (agrega `diff_ops` y helper `_append_props`;
  deja `diff_text_ops` intacto por ahora — lo elimina Task 3)
- Test: `server/tests/test_notion_diff.py` (agrega tests de `diff_ops`)

**Interfaces:**
- Consumes: `_notion_type(bn_block)` e `inline_to_notion_richtext(inline)` ya existen en
  `adapter.py`.
- Produces: `diff_ops(loaded, edited, unsupported_ids, id_map=None) -> {"ops": [op, ...]}` donde
  cada `op` es:
  - `{"op":"patch","notionId":str,"notionType":str,"richText":list}`
  - `{"op":"append","clientId":str,"after":str|None,"notionType":str,"richText":list,"props":dict}`
  - `{"op":"delete","notionId":str}`
  `_append_props(bn_block) -> dict` (`{"checked":bool}` para checkListItem, `{"language":str}`
  para codeBlock, `{}` para el resto).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `server/tests/test_notion_diff.py`:

```python
from ide_server.notion.adapter import diff_ops


def _p(bid, text):
    return {"id": bid, "type": "paragraph", "props": {},
            "content": [{"type": "text", "text": text, "styles": {}}]}


def test_diff_ops_patch_de_existente_cambiado():
    loaded = [_p("n1", "hola")]
    edited = [_p("n1", "chau")]
    ops = diff_ops(loaded, edited, [])["ops"]
    assert len(ops) == 1
    assert ops[0]["op"] == "patch" and ops[0]["notionId"] == "n1"


def test_diff_ops_sin_cambios_no_emite_nada():
    loaded = [_p("n1", "hola")]
    assert diff_ops(loaded, [_p("n1", "hola")], [])["ops"] == []


def test_diff_ops_append_con_after_del_previo():
    loaded = [_p("n1", "uno")]
    edited = [_p("n1", "uno"), _p("c2", "dos")]
    ops = diff_ops(loaded, edited, [])["ops"]
    assert len(ops) == 1
    assert ops[0]["op"] == "append"
    assert ops[0]["clientId"] == "c2"
    assert ops[0]["after"] == "n1"


def test_diff_ops_primer_bloque_nuevo_after_none():
    edited = [_p("c1", "solo")]
    ops = diff_ops([], edited, [])["ops"]
    assert ops[0]["op"] == "append" and ops[0]["after"] is None


def test_diff_ops_dos_nuevos_consecutivos_encadenan_after():
    loaded = [_p("n1", "uno")]
    edited = [_p("n1", "uno"), _p("c2", "dos"), _p("c3", "tres")]
    ops = [o for o in diff_ops(loaded, edited, [])["ops"] if o["op"] == "append"]
    assert ops[0]["clientId"] == "c2" and ops[0]["after"] == "n1"
    assert ops[1]["clientId"] == "c3" and ops[1]["after"] == "c2"


def test_diff_ops_delete_de_bloque_quitado():
    loaded = [_p("n1", "uno"), _p("n2", "dos")]
    edited = [_p("n1", "uno")]
    ops = diff_ops(loaded, edited, [])["ops"]
    assert ops == [{"op": "delete", "notionId": "n2"}]


def test_diff_ops_no_borra_bloque_no_soportado():
    loaded = [_p("n1", "uno"), _p("img1", "placeholder")]
    edited = [_p("n1", "uno")]           # el usuario "quitó" el placeholder
    ops = diff_ops(loaded, edited, ["img1"])["ops"]
    assert all(o.get("notionId") != "img1" for o in ops)
    assert ops == []


def test_diff_ops_id_map_resuelve_cliente_a_notion():
    # c2 ya se subió antes -> idMap lo mapea a n2; su edición es PATCH, no re-APPEND
    loaded = [_p("n1", "uno"), _p("n2", "dos")]
    edited = [_p("n1", "uno"), _p("c2", "DOS")]
    ops = diff_ops(loaded, edited, [], {"c2": "n2"})["ops"]
    assert len(ops) == 1
    assert ops[0]["op"] == "patch" and ops[0]["notionId"] == "n2"


def test_diff_ops_append_lleva_props_de_checklist():
    edited = [{"id": "c1", "type": "checkListItem", "props": {"checked": True},
              "content": [{"type": "text", "text": "x", "styles": {}}]}]
    op = diff_ops([], edited, [])["ops"][0]
    assert op["notionType"] == "to_do" and op["props"] == {"checked": True}
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `cd server && uv run pytest tests/test_notion_diff.py -q`
Expected: FAIL con `ImportError: cannot import name 'diff_ops'`.

- [ ] **Step 3: Implementar `diff_ops` y `_append_props`**

Agregar a `server/ide_server/notion/adapter.py` (después de `diff_text_ops`, sin tocarla):

```python
def _append_props(bn_block: dict) -> dict:
    t = bn_block["type"]
    props = bn_block.get("props") or {}
    if t == "checkListItem":
        return {"checked": bool(props.get("checked"))}
    if t == "codeBlock":
        return {"language": props.get("language", "")}
    return {}


def diff_ops(loaded: list[dict], edited: list[dict], unsupported_ids: list[str],
             id_map: dict[str, str] | None = None) -> dict:
    id_map = id_map or {}
    unsupported = set(unsupported_ids)
    loaded_by = {b["id"]: b for b in loaded}          # keyed por id de Notion
    ops: list[dict] = []
    seen_resolved: set[str] = set()
    prev_resolved: str | None = None                  # id resuelto del bloque previo (en orden)
    for eb in edited:
        bid = eb["id"]
        nid = id_map.get(bid, bid)                     # resolver cliente->notion si aplica
        seen_resolved.add(nid)
        if nid in loaded_by:
            if nid not in unsupported and eb.get("content") != loaded_by[nid].get("content"):
                ops.append({"op": "patch", "notionId": nid, "notionType": _notion_type(eb),
                            "richText": inline_to_notion_richtext(eb.get("content", []))})
            prev_resolved = nid
        else:
            ops.append({"op": "append", "clientId": bid, "after": prev_resolved,
                        "notionType": _notion_type(eb),
                        "richText": inline_to_notion_richtext(eb.get("content", [])),
                        "props": _append_props(eb)})
            prev_resolved = bid                        # el próximo nuevo se ancla a este clientId
    for nid in loaded_by:
        if nid not in seen_resolved and nid not in unsupported:
            ops.append({"op": "delete", "notionId": nid})
    return {"ops": ops}
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `cd server && uv run pytest tests/test_notion_diff.py -q`
Expected: PASS (todos, incluidos los de `diff_text_ops` que siguen intactos).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/notion/adapter.py server/tests/test_notion_diff.py
git commit -m "feat(notion): diff_ops (append/delete/patch con id_map, protege no-soportados)"
```

---

### Task 2: Cliente Notion — `append_block`, `delete_block`, `set_page_title`

**Files:**
- Modify: `server/ide_server/notion/client.py` (agrega 3 funciones + helper `_reraise_rate_limit`;
  refactoriza `patch_block_text` para usar el helper)
- Test: `server/tests/test_notion_client.py` (agrega tests de las 3 funciones nuevas)

**Interfaces:**
- Consumes: `RateLimited` de `ide_server.notion.queue` (ya importado en el módulo).
- Produces:
  - `async append_block(client, parent_id, after, notion_type, rich_text, props) -> str`
    (devuelve el id del bloque creado)
  - `async delete_block(client, notion_id) -> None`
  - `async set_page_title(client, page_id, title) -> None`
  - `_reraise_rate_limit(e)` (helper interno; re-lanza `RateLimited` en 429, sino re-lanza `e`)

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `server/tests/test_notion_client.py` (revisa arriba del archivo el estilo de
fakes existentes y reutilízalo; estos fakes son autocontenidos):

```python
import pytest
from ide_server.notion import client as nclient
from ide_server.notion.queue import RateLimited


class _FakeAppend:
    def __init__(self):
        self.calls = []
    class blocks:
        pass


@pytest.mark.asyncio
async def test_append_block_arma_bloque_y_devuelve_id():
    captured = {}

    class Children:
        async def append(self, **kwargs):
            captured.update(kwargs)
            return {"results": [{"id": "new-id"}]}

    class Blocks:
        children = Children()

    class Client:
        blocks = Blocks()

    new_id = await nclient.append_block(
        Client(), "parent", "after-id", "paragraph",
        [{"type": "text", "text": {"content": "x"}, "annotations": {}}], {})
    assert new_id == "new-id"
    assert captured["block_id"] == "parent"
    assert captured["after"] == "after-id"
    assert captured["children"][0]["type"] == "paragraph"
    assert "rich_text" in captured["children"][0]["paragraph"]


@pytest.mark.asyncio
async def test_append_block_omite_after_si_none():
    captured = {}

    class Children:
        async def append(self, **kwargs):
            captured.update(kwargs)
            return {"results": [{"id": "n"}]}

    class Client:
        class blocks:
            children = Children()

    await nclient.append_block(Client(), "parent", None, "paragraph", [], {})
    assert "after" not in captured


@pytest.mark.asyncio
async def test_append_block_checklist_pone_checked():
    captured = {}

    class Children:
        async def append(self, **kwargs):
            captured.update(kwargs)
            return {"results": [{"id": "n"}]}

    class Client:
        class blocks:
            children = Children()

    await nclient.append_block(Client(), "p", None, "to_do", [], {"checked": True})
    assert captured["children"][0]["to_do"]["checked"] is True


@pytest.mark.asyncio
async def test_append_block_429_a_ratelimited():
    class Err(Exception):
        status = 429
        headers = {"Retry-After": "2"}

    class Children:
        async def append(self, **kwargs):
            raise Err()

    class Client:
        class blocks:
            children = Children()

    with pytest.raises(RateLimited) as ei:
        await nclient.append_block(Client(), "p", None, "paragraph", [], {})
    assert ei.value.retry_after == 2.0


@pytest.mark.asyncio
async def test_delete_block_llama_delete():
    captured = {}

    class Blocks:
        async def delete(self, **kwargs):
            captured.update(kwargs)

    class Client:
        blocks = Blocks()

    await nclient.delete_block(Client(), "n7")
    assert captured["block_id"] == "n7"


@pytest.mark.asyncio
async def test_delete_block_429_a_ratelimited():
    class Err(Exception):
        code = "rate_limited"
        headers = {}

    class Blocks:
        async def delete(self, **kwargs):
            raise Err()

    class Client:
        blocks = Blocks()

    with pytest.raises(RateLimited):
        await nclient.delete_block(Client(), "n7")


@pytest.mark.asyncio
async def test_set_page_title_arma_properties():
    captured = {}

    class Pages:
        async def update(self, **kwargs):
            captured.update(kwargs)

    class Client:
        pages = Pages()

    await nclient.set_page_title(Client(), "pg", "Nuevo")
    assert captured["page_id"] == "pg"
    assert captured["properties"]["title"]["title"][0]["text"]["content"] == "Nuevo"
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `cd server && uv run pytest tests/test_notion_client.py -q`
Expected: FAIL con `AttributeError: module ... has no attribute 'append_block'`.

- [ ] **Step 3: Implementar**

En `server/ide_server/notion/client.py`, reemplazar el cuerpo de `patch_block_text` para usar un
helper y agregar las 3 funciones nuevas:

```python
def _reraise_rate_limit(e: Exception):
    if getattr(e, "status", None) == 429 or getattr(e, "code", None) == "rate_limited":
        headers = getattr(e, "headers", {}) or {}
        retry_after = headers.get("Retry-After", headers.get("retry-after", 1.0))
        raise RateLimited(float(retry_after)) from e
    raise


async def patch_block_text(client, notion_id: str, notion_type: str, rich_text: list[dict]) -> None:
    try:
        await client.blocks.update(block_id=notion_id, **{notion_type: {"rich_text": rich_text}})
    except Exception as e:                                # noqa: BLE001
        _reraise_rate_limit(e)


def _build_block(notion_type: str, rich_text: list[dict], props: dict) -> dict:
    block = {"type": notion_type, notion_type: {"rich_text": rich_text}}
    if notion_type == "to_do":
        block["to_do"]["checked"] = bool(props.get("checked"))
    elif notion_type == "code":
        block["code"]["language"] = props.get("language") or "plain text"
    return block


async def append_block(client, parent_id: str, after: str | None, notion_type: str,
                       rich_text: list[dict], props: dict) -> str:
    kwargs = {"block_id": parent_id, "children": [_build_block(notion_type, rich_text, props)]}
    if after:
        kwargs["after"] = after
    try:
        resp = await client.blocks.children.append(**kwargs)
    except Exception as e:                                # noqa: BLE001
        _reraise_rate_limit(e)
    return resp["results"][0]["id"]


async def delete_block(client, notion_id: str) -> None:
    try:
        await client.blocks.delete(block_id=notion_id)
    except Exception as e:                                # noqa: BLE001
        _reraise_rate_limit(e)


async def set_page_title(client, page_id: str, title: str) -> None:
    try:
        await client.pages.update(
            page_id=page_id,
            properties={"title": {"title": [{"text": {"content": title}}]}})
    except Exception as e:                                # noqa: BLE001
        _reraise_rate_limit(e)
```

Nota: `_reraise_rate_limit` siempre re-lanza (nunca retorna normal); por eso en `append_block` la
línea `return resp[...]` solo se alcanza si no hubo excepción.

- [ ] **Step 4: Correr y verificar que pasan**

Run: `cd server && uv run pytest tests/test_notion_client.py -q`
Expected: PASS (nuevos + los de Fase 1 que siguen).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/notion/client.py server/tests/test_notion_client.py
git commit -m "feat(notion): append_block/delete_block/set_page_title (429->RateLimited)"
```

---

### Task 3: Capability `notion.save` reescrito + `notion.setTitle`

**Files:**
- Modify: `server/ide_server/capabilities/notion.py` (reescribe `save`, agrega `setTitle`, registra
  el canal)
- Modify: `server/ide_server/notion/adapter.py` (elimina `diff_text_ops`, ya sin uso)
- Modify: `server/tests/test_notion_diff.py` (elimina los tests de `diff_text_ops`)
- Test: `server/tests/test_notion_capability.py` (agrega tests de `save` estructural y `setTitle`)

**Interfaces:**
- Consumes: `adapter.diff_ops` (Task 1); `nclient.append_block/delete_block/set_page_title`
  (Task 2); `nclient.patch_block_text`; `RateLimitedRunner.run` (ya usado en el `save` de Fase 1:
  `await runner.run(lambda: coro())`).
- Produces: canal `notion.save` devuelve `{"appended":[{"clientId","notionId"}],"deleted":[...],
  "patched":[...],"failed":[{"op","id","message"}]}`; canal `notion.setTitle` devuelve `{"ok":True}`.

- [ ] **Step 1: Escribir los tests que fallan**

Mira cómo `test_notion_capability.py` arma el registry y el fake client de Fase 1 y reutiliza ese
patrón. Agregar tests (adapta el nombre del fake/registry al del archivo):

```python
# --- Fase 2: save estructural + setTitle ---

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
    assert res["appended"] == [{"clientId": "c3", "notionId": "mint1"}]
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
```

Nota al implementador: si `test_notion_capability.py` no tiene un helper `_registry_with_notion`
que acepte `client_factory` y `token`, crea uno arriba del archivo siguiendo cómo los tests de
Fase 1 construyen el registry con token configurado (por ej. escribiendo el token en
`tmp_path/.ide/config.toml` o pasando `home=tmp_path` a `register`). Reutiliza exactamente el
mecanismo existente; no inventes uno nuevo.

- [ ] **Step 2: Correr y verificar que fallan**

Run: `cd server && uv run pytest tests/test_notion_capability.py -q`
Expected: FAIL (`notion.setTitle` no registrado / `save` devuelve el shape viejo).

- [ ] **Step 3: Reescribir `save`, agregar `setTitle`, borrar `diff_text_ops`**

En `server/ide_server/capabilities/notion.py`, reemplazar la función `save` (líneas ~49-60) por:

```python
    async def save(p: dict) -> dict:
        diff = adapter.diff_ops(p["loaded"], p["edited"],
                                p.get("unsupportedIds", []), p.get("idMap") or {})
        cl = _client()
        page_id = p["pageId"]
        minted: dict[str, str] = {}
        appended, deleted, patched, failed = [], [], [], []
        for op in diff["ops"]:
            try:
                if op["op"] == "patch":
                    await runner.run(lambda op=op: nclient.patch_block_text(
                        cl, op["notionId"], op["notionType"], op["richText"]))
                    patched.append(op["notionId"])
                elif op["op"] == "delete":
                    await runner.run(lambda op=op: nclient.delete_block(cl, op["notionId"]))
                    deleted.append(op["notionId"])
                elif op["op"] == "append":
                    after = minted.get(op["after"], op["after"])  # resolver clientId->notion si aplica
                    new_id = await runner.run(lambda op=op, after=after: nclient.append_block(
                        cl, page_id, after, op["notionType"], op["richText"], op["props"]))
                    minted[op["clientId"]] = new_id
                    appended.append({"clientId": op["clientId"], "notionId": new_id})
            except Exception as exc:                       # noqa: BLE001 — se reporta, no se traga
                failed.append({"op": op["op"],
                               "id": op.get("notionId") or op.get("clientId"),
                               "message": str(exc)})
        return {"appended": appended, "deleted": deleted, "patched": patched, "failed": failed}

    async def set_title(p: dict) -> dict:
        await runner.run(lambda: nclient.set_page_title(_client(), p["pageId"], p["title"]))
        return {"ok": True}
```

Registrar el canal nuevo: en la lista de `register` agregar `("setTitle", set_title)`:

```python
    for name, fn in [("health", health), ("list", list_), ("add", add),
                     ("remove", remove), ("page", page), ("save", save),
                     ("setTitle", set_title),
                     ("connect", connect), ("disconnect", disconnect)]:
        registry.register(f"notion.{name}", fn)
```

En `server/ide_server/notion/adapter.py`, **eliminar** la función `diff_text_ops` (ya sin
llamadores). En `server/tests/test_notion_diff.py`, eliminar el `import` de `diff_text_ops` y sus
tests (los que usan `diff_text_ops(...)`), dejando solo los de `diff_ops`.

- [ ] **Step 4: Correr y verificar que pasan**

Run: `cd server && uv run pytest tests/test_notion_capability.py tests/test_notion_diff.py -q`
Expected: PASS.
Luego la suite completa: `cd server && uv run pytest -q` → PASS (verificar que nada más
importaba `diff_text_ops`).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/notion.py server/ide_server/notion/adapter.py server/tests/test_notion_capability.py server/tests/test_notion_diff.py
git commit -m "feat(notion): save estructural (append/delete/patch + minted after) y setTitle"
```

---

### Task 4: Transport frontend — `savePage` nuevo shape + `setTitle`

**Files:**
- Modify: `ui/src/transport/notionChannel.ts`
- Test: `ui/src/transport/notionChannel.test.ts`

**Interfaces:**
- Produces:
  - `savePage(ws, id, loaded, edited, unsupportedIds, idMap) -> Promise<SaveResult>` donde
    `SaveResult = { appended: {clientId,notionId}[]; deleted: string[]; patched: string[];
    failed: {op,id,message}[] }`. Manda `{ pageId: id, loaded, edited, unsupportedIds, idMap }`.
  - `setTitle(ws, id, title) -> Promise<void>` (manda `{ pageId: id, title }`).

- [ ] **Step 1: Actualizar el test de `savePage` y agregar el de `setTitle`**

En `ui/src/transport/notionChannel.test.ts`, reemplazar el test "savePage manda ..." y agregar
`setTitle`:

```ts
  it("savePage manda pageId/loaded/edited/unsupportedIds/idMap", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ appended: [], deleted: [], patched: [], failed: [] }) } as any;
    await savePage(ws, "id", [{ id: "b1" }], [{ id: "b1" }], ["u1"], { c: "n" });
    expect(ws.request).toHaveBeenCalledWith("notion.save",
      { pageId: "id", loaded: [{ id: "b1" }], edited: [{ id: "b1" }], unsupportedIds: ["u1"], idMap: { c: "n" } });
  });
  it("setTitle manda pageId y title", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ ok: true }) } as any;
    await setTitle(ws, "id", "Nuevo");
    expect(ws.request).toHaveBeenCalledWith("notion.setTitle", { pageId: "id", title: "Nuevo" });
  });
```

Agregar `setTitle` al import de la primera línea del archivo.

- [ ] **Step 2: Correr y verificar que fallan**

Run: `cd ui && npm test -- notionChannel`
Expected: FAIL (`setTitle` no existe; `savePage` manda el shape viejo).

- [ ] **Step 3: Implementar**

En `ui/src/transport/notionChannel.ts`, reemplazar `SaveResult` y `savePage`, agregar `setTitle`:

```ts
export interface SaveResult {
  appended: { clientId: string; notionId: string }[];
  deleted: string[];
  patched: string[];
  failed: { op: string; id: string; message: string }[];
}

export async function savePage(
  ws: WsClient, id: string, loaded: BlockNoteDoc, edited: BlockNoteDoc,
  unsupportedIds: string[], idMap: Record<string, string>,
): Promise<SaveResult> {
  return ws.request("notion.save", { pageId: id, loaded, edited, unsupportedIds, idMap });
}

export async function setTitle(ws: WsClient, id: string, title: string): Promise<void> {
  await ws.request("notion.setTitle", { pageId: id, title });
}
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `cd ui && npm test -- notionChannel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/notionChannel.ts ui/src/transport/notionChannel.test.ts
git commit -m "feat(notion): transport savePage con idMap + setTitle"
```

---

### Task 5: `NotionPageTab` — idMap, título editable, sin banner ni remount en happy path

**Files:**
- Modify: `ui/src/main/NotionPageTab.tsx`
- Test: `ui/src/main/NotionPageTab.test.tsx`

**Interfaces:**
- Consumes: `savePage(ws, id, loaded, edited, unsupportedIds, idMap)`, `setTitle(ws, id, title)`,
  `fetchPage` (Task 4 + Fase 1).
- Comportamiento: mantiene `idMap` (`Record<string,string>`). En `onChange` (debounce 800ms)
  llama `savePage(..., idMap)`. Si `res.failed.length` → re-fetch de reconciliación (`syncKey++`,
  `idMap={}`, status error). Si no → fusiona `appended` en `idMap`, setea `loaded = edited`
  rekey-ado por el idMap fusionado, status "saved", **sin** `syncKey++`. El título es un input
  editable que en `onBlur` llama `setTitle`. Se elimina el banner de "Fase 2".

- [ ] **Step 1: Reescribir los tests**

Reemplazar `ui/src/main/NotionPageTab.test.tsx` por (mantiene el mock del editor; agrega mock de
`setTitle`; cubre idMap-merge, no-remount y título):

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchPage = vi.fn(), savePage = vi.fn(), setTitle = vi.fn();
vi.mock("../transport/notionChannel", () => ({
  fetchPage: (...a: any[]) => fetchPage(...a),
  savePage: (...a: any[]) => savePage(...a),
  setTitle: (...a: any[]) => setTitle(...a),
}));
// El mock del editor dispara onChange con un doc que agrega un bloque nuevo "c2".
vi.mock("./NotionEditor", () => ({
  NotionEditor: ({ onChange }: any) => (
    <button onClick={() => onChange([
      { id: "b1", type: "paragraph", content: [] },
      { id: "c2", type: "paragraph", content: [{ type: "text", text: "z", styles: {} }] },
    ])}>edit</button>
  ),
}));
import { NotionPageTab } from "./NotionPageTab";

beforeEach(() => { fetchPage.mockReset(); savePage.mockReset(); setTitle.mockReset(); vi.useFakeTimers(); });

describe("NotionPageTab Fase 2", () => {
  it("guarda con idMap y fusiona appended sin remontar (happy path)", async () => {
    fetchPage.mockResolvedValue({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: ["u1"] });
    savePage.mockResolvedValue({ appended: [{ clientId: "c2", notionId: "n2" }], deleted: [], patched: [], failed: [] });
    render(<NotionPageTab id="notion:pageX" />);
    await vi.waitFor(() => screen.getByText("edit"));

    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    // primer save: idMap vacío
    expect(savePage).toHaveBeenLastCalledWith(expect.anything(), "pageX",
      expect.any(Array), expect.any(Array), ["u1"], {});

    // segunda edición del mismo doc: ahora idMap debe mapear c2->n2
    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    expect(savePage).toHaveBeenLastCalledWith(expect.anything(), "pageX",
      expect.any(Array), expect.any(Array), ["u1"], { c2: "n2" });
    // happy path: no hubo re-fetch de reconciliación (solo el fetch inicial)
    expect(fetchPage).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("re-fetch de reconciliación cuando una op falla", async () => {
    fetchPage
      .mockResolvedValueOnce({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: [] })
      .mockResolvedValueOnce({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: [] });
    savePage.mockResolvedValue({ appended: [], deleted: [], patched: [], failed: [{ op: "append", id: "c2", message: "boom" }] });
    render(<NotionPageTab id="notion:pageX" />);
    await vi.waitFor(() => screen.getByText("edit"));
    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    await vi.waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(2));
    vi.useRealTimers();
  });

  it("editar el título llama setTitle en blur", async () => {
    fetchPage.mockResolvedValue({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: [] });
    setTitle.mockResolvedValue(undefined);
    render(<NotionPageTab id="notion:pageX" />);
    const input = await vi.waitFor(() => screen.getByDisplayValue("T"));
    fireEvent.change(input, { target: { value: "Nuevo" } });
    fireEvent.blur(input);
    expect(setTitle).toHaveBeenCalledWith(expect.anything(), "pageX", "Nuevo");
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `cd ui && npm test -- NotionPageTab`
Expected: FAIL.

- [ ] **Step 3: Reescribir el componente**

Reemplazar `ui/src/main/NotionPageTab.tsx` por:

```tsx
import { useEffect, useRef, useState } from "react";
import { fetchPage, savePage, setTitle as setTitleReq, type BlockNoteDoc } from "../transport/notionChannel";
import { getWs } from "../transport/wsClient";
import { NotionEditor } from "./NotionEditor";

type Status = "idle" | "saving" | "saved" | "error";

export function NotionPageTab({ id }: { id: string }) {
  const pageId = id.slice("notion:".length);
  const [title, setTitle] = useState("");
  const [loaded, setLoaded] = useState<BlockNoteDoc | null>(null);
  const [unsupported, setUnsupported] = useState<string[]>([]);
  const [idMap, setIdMap] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [syncKey, setSyncKey] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    fetchPage(getWs(), pageId)
      .then((d) => { if (!cancelled) { setTitle(d.title); setLoaded(d.blocks); setUnsupported(d.unsupportedIds); setIdMap({}); setSyncKey((k) => k + 1); } })
      .catch((e) => { if (!cancelled) setError((e as { message?: string })?.message ?? "desconectado"); });
    return () => { cancelled = true; };
  }, [pageId]);

  function onChange(edited: BlockNoteDoc) {
    if (!loaded) return;
    clearTimeout(timer.current);
    setStatus("saving");
    timer.current = setTimeout(async () => {
      try {
        const res = await savePage(getWs(), pageId, loaded, edited, unsupported, idMap);
        if (res.failed.length) {
          setStatus("error");
          const d = await fetchPage(getWs(), pageId);     // reconciliar a la verdad de Notion
          setLoaded(d.blocks); setUnsupported(d.unsupportedIds); setIdMap({}); setSyncKey((k) => k + 1);
        } else {
          const merged = { ...idMap };
          for (const a of res.appended) merged[a.clientId] = a.notionId;
          setIdMap(merged);
          setLoaded(edited.map((b) => ({ ...b, id: merged[b.id] ?? b.id })));  // rekey a ids de Notion
          setStatus("saved");
        }
      } catch (e) { setStatus("error"); setError((e as { message?: string })?.message ?? "error"); }
    }, 800);
  }

  async function commitTitle() {
    try { await setTitleReq(getWs(), pageId, title); }
    catch (e) { setStatus("error"); setError((e as { message?: string })?.message ?? "error"); }
  }

  if (error) return <div className="p-4 text-sm text-destructive">no se pudo abrir la página — {error}</div>;
  if (!loaded) return <div className="p-4 text-sm text-muted-foreground">cargando…</div>;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-5 py-3">
        <input
          className="flex-1 bg-transparent text-lg font-bold text-foreground outline-none"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={commitTitle}
        />
        <span className="text-[10px] text-muted-foreground">
          {status === "saving" ? "guardando…" : status === "saved" ? "guardado" : status === "error" ? "error al guardar" : ""}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <NotionEditor key={syncKey} initial={loaded} onChange={onChange} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `cd ui && npm test -- NotionPageTab`
Expected: PASS. Luego suite completa: `cd ui && npm test` → PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/main/NotionPageTab.tsx ui/src/main/NotionPageTab.test.tsx
git commit -m "feat(notion): NotionPageTab con idMap, título editable y sin remount en happy path"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** agregar (Task 1 append + Task 2 append_block + Task 3 minted after +
  Task 5 idMap); borrar (Task 1 delete + Task 2 delete_block + Task 3); título (Task 2
  set_page_title + Task 3 setTitle + Task 4 + Task 5 input); no-remount + idMap (Task 5);
  protección de no-soportados (Task 1 `test_diff_ops_no_borra_bloque_no_soportado`). ✓
- **Consistencia de tipos:** `SaveResult {appended,deleted,patched,failed}` idéntico en Task 3
  (backend), Task 4 (transport) y Task 5 (consumidor). `diff_ops(loaded, edited, unsupported_ids,
  id_map)` firma única. Payload `save` usa `pageId` en Task 3/4/5 (cambio desde `id` de Fase 1).
- **Sin placeholders:** todo el código está completo en cada step. ✓
- **Limitación conocida documentada:** un bloque nuevo insertado *antes* del primer bloque
  existente cae al final (Notion no tiene "prepend"; `after=None` → append al final). Fuera del
  camino común (escribir de corrido / al final). Aceptado en el spec ("sin reordenar").
```
