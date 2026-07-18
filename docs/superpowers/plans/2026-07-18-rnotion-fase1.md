# R-Notion Fase 1 — lectura + edición de texto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar el ítem "Notion" del rail: lista curada de páginas por URL, render con BlockNote fiel a Notion, y edición del **texto de bloques existentes** sincronizada a la **API oficial** de Notion respetando ~3 rps.

**Architecture:** Backend Python = proxy/orquestador con SDK oficial `notion-client` + cola de rate-limit; adaptador puro Notion-blocks↔BlockNote (la carne, testeable). Frontend = editor BlockNote. Molde de plugin de R4/R5a (capability + transport + store + módulo del rail + tab). **Clave:** cada bloque BlockNote lleva `id` = id del bloque de Notion → el diff correlaciona por id sin id-map extra.

**Tech Stack:** Backend Python/FastAPI (`uv`, `pytest`, `notion-client>=3.1`); frontend React + Vite + TS (Zustand, `@blocknote/core|react|mantine`@0.51.4, Vitest).

## Global Constraints

- **Sin fallos silenciosos:** errores de red/API/token viajan como envelope `{type:"error",payload:{code,message}}` (bus.py envuelve cualquier Exception en `handler_error`). Token ausente/inválido → `notion.health connected:false` → panel "conectá Notion", nunca datos falsos. Fallo parcial de save → `failed` reportado, el front re-fetchea. Cambio estructural en Fase 1 → banner explícito + re-sync, jamás drop silencioso.
- **TDD estricto:** test que falla → implementación mínima → test que pasa → commit. Un commit por tarea.
- **Conventional commits en español**, atómicos.
- **Rate limit ~3 rps:** cola serializada en backend con backoff en 429 (`Retry-After`). Los tests **mockean el SDK** (nunca se pega a Notion en CI).
- **Set de bloques soportado (Fase 1):** paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item, to_do, quote, code. Todo lo demás (divider incluido, synced/DB/embed/columnas/toggles/callouts/imágenes) → placeholder inerte, `id` en `unsupportedIds`, el diff nunca le emite ops.
- **Token:** `~/.ide/config.toml [notion].token` (global), override local `.ide/config.toml` y env `NOTION_TOKEN`.
- **BlockNote id = Notion block id.** Título read-only en Fase 1. Estructural (add/del/reorder) y editar título → Fase 2 (avisados, no sincronizados).
- **Tests:** backend `cd server && uv run pytest -q`; frontend `cd ui && npm test`.
- **Verificar contra la versión instalada:** el shape exacto de BlockNote 0.51.4 (nombres de `type`, keys de `styles`) manda; si un test del adapter no matchea la lib real, ajustar el shape esperado del test a la lib (no al revés) y anotarlo.

---

### Task 1: `notion/config.py` — resolución de token + dependencia

**Files:**
- Create: `server/ide_server/notion/__init__.py` (vacío)
- Create: `server/ide_server/notion/config.py`
- Modify: `server/pyproject.toml` (agregar `notion-client>=3.1`)
- Test: `server/tests/test_notion_config.py`

**Interfaces:**
- Produces: `notion_token(home: Path, root: Path) -> str | None` — env `NOTION_TOKEN` → `root/.ide/config.toml [notion].token` → `home/.ide/config.toml [notion].token` → `None`.

- [ ] **Step 1: Add the dependency**

Run: `cd server && uv add "notion-client>=3.1"`
Expected: `pyproject.toml` gains `notion-client`, lockfile updated, `import notion_client` resolvable.

- [ ] **Step 2: Write the failing test**

```python
# server/tests/test_notion_config.py
import tomllib
from pathlib import Path
from ide_server.notion.config import notion_token


def _write(p: Path, token: str) -> None:
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.toml").write_text(f'[notion]\ntoken = "{token}"\n')


def test_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "env-tok")
    assert notion_token(tmp_path / "home", tmp_path / "root") == "env-tok"


def test_local_over_global(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    _write(tmp_path / "home" / ".ide", "global-tok")
    _write(tmp_path / "root" / ".ide", "local-tok")
    assert notion_token(tmp_path / "home", tmp_path / "root") == "local-tok"


def test_global_fallback_and_none(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    _write(tmp_path / "home" / ".ide", "global-tok")
    assert notion_token(tmp_path / "home", tmp_path / "root") == "global-tok"
    assert notion_token(tmp_path / "empty-home", tmp_path / "empty-root") is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_config.py -q`
Expected: FAIL (`ModuleNotFoundError: ide_server.notion.config`)

- [ ] **Step 4: Write minimal implementation**

```python
# server/ide_server/notion/config.py
from __future__ import annotations
import os
import tomllib
from pathlib import Path


def _token_from(cfg: Path) -> str | None:
    if not cfg.is_file():
        return None
    try:
        data = tomllib.loads(cfg.read_text())
    except tomllib.TOMLDecodeError:
        return None
    tok = (data.get("notion") or {}).get("token")
    return tok or None


def notion_token(home: Path, root: Path) -> str | None:
    env = os.environ.get("NOTION_TOKEN")
    if env:
        return env
    return (_token_from(root / ".ide" / "config.toml")
            or _token_from(home / ".ide" / "config.toml"))
```

(`server/ide_server/notion/__init__.py` is an empty file.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_config.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add server/ide_server/notion/__init__.py server/ide_server/notion/config.py server/pyproject.toml server/uv.lock server/tests/test_notion_config.py
git commit -m "feat(notion): resolución de token (env/local/global) + dep notion-client"
```

---

### Task 2: `notion/refs.py` — parse de URL + lista curada

**Files:**
- Create: `server/ide_server/notion/refs.py`
- Test: `server/tests/test_notion_refs.py`

**Interfaces:**
- Produces:
  - `parse_page_id(url_or_id: str) -> str` — extrae el UUID (32 hex → formateado con guiones). `ValueError` si no matchea.
  - `list_refs(root: Path) -> list[dict]` → `[{id, title}]` desde `<root>/.ide/notion.json`.
  - `add_ref(root, id, title) -> None` / `remove_ref(root, id) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_notion_refs.py
import pytest
from pathlib import Path
from ide_server.notion.refs import parse_page_id, list_refs, add_ref, remove_ref


def test_parse_page_id_from_url_and_raw():
    raw = "1234567890abcdef1234567890abcdef"
    dashed = "12345678-90ab-cdef-1234-567890abcdef"
    assert parse_page_id(f"https://www.notion.so/My-Page-{raw}") == dashed
    assert parse_page_id(f"https://notion.so/{raw}?v=abc") == dashed
    assert parse_page_id(dashed) == dashed
    with pytest.raises(ValueError):
        parse_page_id("https://example.com/no-id-here")


def test_curated_list_crud(tmp_path):
    (tmp_path / ".ide").mkdir()
    assert list_refs(tmp_path) == []
    add_ref(tmp_path, "id-a", "Página A")
    add_ref(tmp_path, "id-b", "Página B")
    add_ref(tmp_path, "id-a", "Página A dup")   # no duplica; actualiza título
    refs = list_refs(tmp_path)
    assert [r["id"] for r in refs] == ["id-a", "id-b"]
    assert refs[0]["title"] == "Página A dup"
    remove_ref(tmp_path, "id-a")
    assert [r["id"] for r in list_refs(tmp_path)] == ["id-b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_refs.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/notion/refs.py
from __future__ import annotations
import json
import re
from pathlib import Path

_HEX32 = re.compile(r"([0-9a-fA-F]{32})")
_DASHED = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


def parse_page_id(url_or_id: str) -> str:
    m = _DASHED.search(url_or_id)
    if m:
        return m.group(1).lower()
    m = _HEX32.search(url_or_id.replace("-", ""))
    if not m:
        raise ValueError(f"no se encontró un page id en: {url_or_id}")
    h = m.group(1).lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _path(root: Path) -> Path:
    return root / ".ide" / "notion.json"


def list_refs(root: Path) -> list[dict]:
    p = _path(root)
    if not p.is_file():
        return []
    try:
        return json.loads(p.read_text()).get("pages", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save(root: Path, pages: list[dict]) -> None:
    p = _path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pages": pages}, ensure_ascii=False, indent=2))


def add_ref(root: Path, id: str, title: str) -> None:
    # update in-place si ya existe (conserva su posición), si no lo agrega al final
    pages = list_refs(root)
    for r in pages:
        if r["id"] == id:
            r["title"] = title
            _save(root, pages)
            return
    pages.append({"id": id, "title": title})
    _save(root, pages)


def remove_ref(root: Path, id: str) -> None:
    _save(root, [r for r in list_refs(root) if r["id"] != id])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_refs.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/notion/refs.py server/tests/test_notion_refs.py
git commit -m "feat(notion): parse_page_id + lista curada en .ide/notion.json"
```

---

### Task 3: `notion/adapter.py` — rich text inline (bidireccional)

**Files:**
- Create: `server/ide_server/notion/adapter.py`
- Test: `server/tests/test_notion_inline.py`

**Interfaces:**
- Produces:
  - `notion_richtext_to_inline(rich_text: list[dict]) -> list[dict]` — Notion rich_text → BlockNote inline content.
  - `inline_to_notion_richtext(inline: list[dict]) -> list[dict]` — inverso.
- Mapeo de estilos: Notion `annotations{bold,italic,strikethrough,underline,code,color}` ↔ BlockNote `styles{bold,italic,strike,underline,code,textColor}` (solo se incluye lo `true`/no-default). Link: Notion `text.link.url` ↔ BlockNote `{type:"link", href, content:[...]}`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_notion_inline.py
from ide_server.notion.adapter import notion_richtext_to_inline, inline_to_notion_richtext


def _rt(content, *, bold=False, italic=False, strike=False, code=False, link=None):
    return {
        "type": "text",
        "text": {"content": content, "link": ({"url": link} if link else None)},
        "annotations": {"bold": bold, "italic": italic, "strikethrough": strike,
                        "underline": False, "code": code, "color": "default"},
        "plain_text": content,
        "href": link,
    }


def test_plain_and_styled_to_inline():
    rt = [_rt("Hola "), _rt("mundo", bold=True, italic=True)]
    inline = notion_richtext_to_inline(rt)
    assert inline[0] == {"type": "text", "text": "Hola ", "styles": {}}
    assert inline[1] == {"type": "text", "text": "mundo", "styles": {"bold": True, "italic": True}}


def test_link_to_inline():
    rt = [_rt("acá", link="https://x.com")]
    inline = notion_richtext_to_inline(rt)
    assert inline[0] == {
        "type": "link", "href": "https://x.com",
        "content": [{"type": "text", "text": "acá", "styles": {}}]}


def test_roundtrip_inline_to_notion():
    inline = [
        {"type": "text", "text": "n ", "styles": {}},
        {"type": "text", "text": "code", "styles": {"code": True}},
        {"type": "link", "href": "https://y.com", "content": [{"type": "text", "text": "l", "styles": {"bold": True}}]},
    ]
    rt = inline_to_notion_richtext(inline)
    assert rt[0]["text"]["content"] == "n " and rt[0]["annotations"]["code"] is False
    assert rt[1]["annotations"]["code"] is True
    assert rt[2]["text"]["content"] == "l" and rt[2]["text"]["link"] == {"url": "https://y.com"}
    assert rt[2]["annotations"]["bold"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_inline.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/notion/adapter.py
from __future__ import annotations

# Notion annotation -> BlockNote style key
_ANNOT_TO_STYLE = {"bold": "bold", "italic": "italic", "strikethrough": "strike",
                   "underline": "underline", "code": "code"}
_STYLE_TO_ANNOT = {v: k for k, v in _ANNOT_TO_STYLE.items()}


def _styles_from_annotations(a: dict) -> dict:
    styles = {}
    for annot, style in _ANNOT_TO_STYLE.items():
        if a.get(annot):
            styles[style] = True
    if a.get("color") and a["color"] != "default":
        styles["textColor"] = a["color"]
    return styles


def _annotations_from_styles(styles: dict) -> dict:
    a = {"bold": False, "italic": False, "strikethrough": False,
         "underline": False, "code": False, "color": "default"}
    for style, val in styles.items():
        if style in _STYLE_TO_ANNOT and val:
            a[_STYLE_TO_ANNOT[style]] = True
        elif style == "textColor" and val:
            a["color"] = val
    return a


def notion_richtext_to_inline(rich_text: list[dict]) -> list[dict]:
    out = []
    for rt in rich_text:
        text = (rt.get("text") or {}).get("content", rt.get("plain_text", ""))
        styles = _styles_from_annotations(rt.get("annotations") or {})
        link = (rt.get("text") or {}).get("link")
        node = {"type": "text", "text": text, "styles": styles}
        if link and link.get("url"):
            out.append({"type": "link", "href": link["url"], "content": [node]})
        else:
            out.append(node)
    return out


def _notion_text(content: str, styles: dict, url: str | None) -> dict:
    return {
        "type": "text",
        "text": {"content": content, "link": ({"url": url} if url else None)},
        "annotations": _annotations_from_styles(styles),
    }


def inline_to_notion_richtext(inline: list[dict]) -> list[dict]:
    out = []
    for node in inline:
        if node.get("type") == "link":
            for inner in node.get("content", []):
                out.append(_notion_text(inner.get("text", ""), inner.get("styles", {}), node.get("href")))
        else:
            out.append(_notion_text(node.get("text", ""), node.get("styles", {}), None))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_inline.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/notion/adapter.py server/tests/test_notion_inline.py
git commit -m "feat(notion): adapter inline rich_text <-> BlockNote (bidireccional)"
```

---

### Task 4: `notion/adapter.py` — bloques Notion → BlockNote (+ inertes)

**Files:**
- Modify: `server/ide_server/notion/adapter.py` (append)
- Test: `server/tests/test_notion_blocks.py`

**Interfaces:**
- Consumes: `notion_richtext_to_inline` (Task 3).
- Produces: `notion_blocks_to_blocknote(blocks: list[dict]) -> dict` → `{"blocks": [...], "unsupportedIds": [...]}`. Cada bloque BlockNote lleva `id` = id del bloque de Notion. Soportados: paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item, to_do, quote, code. Cualquier otro → placeholder `{id, type:"paragraph", props:{}, content:[{type:"text", text:f"[bloque no soportado: {ntype}]", styles:{"italic":True}}]}` y su id va en `unsupportedIds`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_notion_blocks.py
from ide_server.notion.adapter import notion_blocks_to_blocknote


def _blk(bid, ntype, text, **extra):
    body = {"rich_text": [{"type": "text", "text": {"content": text, "link": None},
            "annotations": {"bold": False, "italic": False, "strikethrough": False,
            "underline": False, "code": False, "color": "default"}, "plain_text": text}]}
    body.update(extra)
    return {"id": bid, "type": ntype, ntype: body, "has_children": False}


def test_supported_blocks_map_with_notion_id():
    blocks = [
        _blk("p1", "paragraph", "hola"),
        _blk("h1", "heading_2", "título"),
        _blk("b1", "bulleted_list_item", "item"),
        _blk("t1", "to_do", "tarea", checked=True),
        _blk("c1", "code", "print(1)", language="python"),
    ]
    out = notion_blocks_to_blocknote(blocks)
    by = {b["id"]: b for b in out["blocks"]}
    assert by["p1"]["type"] == "paragraph"
    assert by["h1"]["type"] == "heading" and by["h1"]["props"]["level"] == 2
    assert by["b1"]["type"] == "bulletListItem"
    assert by["t1"]["type"] == "checkListItem" and by["t1"]["props"]["checked"] is True
    assert by["c1"]["type"] == "codeBlock" and by["c1"]["props"]["language"] == "python"
    assert out["unsupportedIds"] == []


def test_unsupported_block_is_inert_placeholder():
    blocks = [{"id": "img1", "type": "image", "image": {}, "has_children": False}]
    out = notion_blocks_to_blocknote(blocks)
    assert out["unsupportedIds"] == ["img1"]
    ph = out["blocks"][0]
    assert ph["id"] == "img1" and ph["type"] == "paragraph"
    assert "no soportado" in ph["content"][0]["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_blocks.py -q`
Expected: FAIL (`ImportError: cannot import name 'notion_blocks_to_blocknote'`)

- [ ] **Step 3: Write minimal implementation** (append a `adapter.py`)

```python
_HEADINGS = {"heading_1": 1, "heading_2": 2, "heading_3": 3}


def _content(block: dict, ntype: str) -> list[dict]:
    rt = (block.get(ntype) or {}).get("rich_text", [])
    return notion_richtext_to_inline(rt)


def _placeholder(bid: str, ntype: str) -> dict:
    return {"id": bid, "type": "paragraph", "props": {},
            "content": [{"type": "text", "text": f"[bloque no soportado: {ntype}]",
                         "styles": {"italic": True}}]}


def notion_blocks_to_blocknote(blocks: list[dict]) -> dict:
    out: list[dict] = []
    unsupported: list[str] = []
    for b in blocks:
        bid, ntype = b["id"], b["type"]
        if ntype == "paragraph":
            out.append({"id": bid, "type": "paragraph", "props": {}, "content": _content(b, ntype)})
        elif ntype in _HEADINGS:
            out.append({"id": bid, "type": "heading", "props": {"level": _HEADINGS[ntype]},
                        "content": _content(b, ntype)})
        elif ntype == "bulleted_list_item":
            out.append({"id": bid, "type": "bulletListItem", "props": {}, "content": _content(b, ntype)})
        elif ntype == "numbered_list_item":
            out.append({"id": bid, "type": "numberedListItem", "props": {}, "content": _content(b, ntype)})
        elif ntype == "to_do":
            out.append({"id": bid, "type": "checkListItem",
                        "props": {"checked": bool((b.get("to_do") or {}).get("checked"))},
                        "content": _content(b, ntype)})
        elif ntype == "quote":
            out.append({"id": bid, "type": "quote", "props": {}, "content": _content(b, ntype)})
        elif ntype == "code":
            out.append({"id": bid, "type": "codeBlock",
                        "props": {"language": (b.get("code") or {}).get("language", "")},
                        "content": _content(b, ntype)})
        else:
            out.append(_placeholder(bid, ntype))
            unsupported.append(bid)
    return {"blocks": out, "unsupportedIds": unsupported}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_blocks.py -q`
Expected: PASS (2 passed). Si BlockNote 0.51.4 usa nombres de `type` distintos (p.ej. no existe `quote`/`codeBlock`), ajustá el shape esperado del test a lo que la lib acepta y anotalo en el report.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/notion/adapter.py server/tests/test_notion_blocks.py
git commit -m "feat(notion): adapter bloques Notion -> BlockNote (id preservado + inertes)"
```

---

### Task 5: `notion/adapter.py` — `diff_text_ops`

**Files:**
- Modify: `server/ide_server/notion/adapter.py` (append)
- Test: `server/tests/test_notion_diff.py`

**Interfaces:**
- Consumes: `inline_to_notion_richtext` (Task 3).
- Produces: `diff_text_ops(loaded: list[dict], edited: list[dict], unsupported_ids: list[str]) -> dict` → `{"ops":[{notionId, notionType, richText}], "structural": bool}`. Correlaciona por `id`. Si el conjunto de ids difiere (alta/baja) → `structural=True` (y solo se emiten ops de los ids que sobreviven). Bloques cuyo `id` está en `unsupported_ids` nunca generan op. `notionType` se deriva del bloque BlockNote (type + props.level).

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_notion_diff.py
from ide_server.notion.adapter import diff_text_ops


def _bn(bid, typ, text, **props):
    return {"id": bid, "type": typ, "props": props,
            "content": [{"type": "text", "text": text, "styles": {}}]}


def test_text_change_emits_patch_op():
    loaded = [_bn("p1", "paragraph", "hola"), _bn("h1", "heading", "t", level=2)]
    edited = [_bn("p1", "paragraph", "hola mundo"), _bn("h1", "heading", "t", level=2)]
    res = diff_text_ops(loaded, edited, [])
    assert res["structural"] is False
    assert len(res["ops"]) == 1
    op = res["ops"][0]
    assert op["notionId"] == "p1" and op["notionType"] == "paragraph"
    assert op["richText"][0]["text"]["content"] == "hola mundo"


def test_heading_op_uses_notion_type_from_level():
    loaded = [_bn("h1", "heading", "a", level=3)]
    edited = [_bn("h1", "heading", "b", level=3)]
    op = diff_text_ops(loaded, edited, [])["ops"][0]
    assert op["notionType"] == "heading_3"


def test_structural_change_flagged_and_survivors_only():
    loaded = [_bn("p1", "paragraph", "uno")]
    edited = [_bn("p1", "paragraph", "uno!"), _bn("NEW", "paragraph", "dos")]
    res = diff_text_ops(loaded, edited, [])
    assert res["structural"] is True
    assert [o["notionId"] for o in res["ops"]] == ["p1"]   # NEW no genera op


def test_unsupported_never_emits_op():
    loaded = [_bn("img1", "paragraph", "[bloque no soportado: image]")]
    edited = [_bn("img1", "paragraph", "editado")]
    res = diff_text_ops(loaded, edited, ["img1"])
    assert res["ops"] == [] and res["structural"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_diff.py -q`
Expected: FAIL (`ImportError`)

- [ ] **Step 3: Write minimal implementation** (append a `adapter.py`)

```python
_BN_TO_NOTION = {"paragraph": "paragraph", "bulletListItem": "bulleted_list_item",
                 "numberedListItem": "numbered_list_item", "checkListItem": "to_do",
                 "quote": "quote", "codeBlock": "code"}


def _notion_type(bn_block: dict) -> str:
    t = bn_block["type"]
    if t == "heading":
        return f"heading_{(bn_block.get('props') or {}).get('level', 1)}"
    return _BN_TO_NOTION.get(t, "paragraph")


def diff_text_ops(loaded: list[dict], edited: list[dict], unsupported_ids: list[str]) -> dict:
    unsupported = set(unsupported_ids)
    loaded_by = {b["id"]: b for b in loaded}
    edited_by = {b["id"]: b for b in edited}
    structural = set(loaded_by) != set(edited_by)
    ops = []
    for bid, eb in edited_by.items():
        if bid in unsupported or bid not in loaded_by:
            continue
        if eb.get("content") != loaded_by[bid].get("content"):
            ops.append({"notionId": bid, "notionType": _notion_type(eb),
                        "richText": inline_to_notion_richtext(eb.get("content", []))})
    return {"ops": ops, "structural": structural}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_diff.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/notion/adapter.py server/tests/test_notion_diff.py
git commit -m "feat(notion): diff_text_ops (PATCH por texto + flag estructural)"
```

---

### Task 6: `notion/queue.py` — cola de rate-limit

**Files:**
- Create: `server/ide_server/notion/queue.py`
- Test: `server/tests/test_notion_queue.py`

**Interfaces:**
- Produces: `class RateLimitedRunner` con `__init__(self, rate_per_sec=3.0, sleep=asyncio.sleep, now=time.monotonic)` y `async run(self, coro_fn)` — serializa las llamadas y garantiza ≥ `1/rate_per_sec` entre despachos. Reintenta ante `RateLimited` (una excepción con `.retry_after`) respetando el backoff.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_notion_queue.py
import pytest
from ide_server.notion.queue import RateLimitedRunner, RateLimited


@pytest.mark.asyncio
async def test_serializes_and_spaces(monkeypatch):
    clock = {"t": 0.0}
    slept = []

    async def fake_sleep(s):
        slept.append(s)
        clock["t"] += s

    runner = RateLimitedRunner(rate_per_sec=3.0, sleep=fake_sleep, now=lambda: clock["t"])
    order = []

    async def op(n):
        order.append(n)
        return n

    assert await runner.run(lambda: op(1)) == 1
    assert await runner.run(lambda: op(2)) == 2
    assert order == [1, 2]
    # el 2º despacho esperó ~1/3 s porque el reloj no avanzó solo
    assert any(abs(s - (1 / 3)) < 1e-6 for s in slept)


@pytest.mark.asyncio
async def test_retries_on_rate_limited():
    calls = {"n": 0}

    async def fake_sleep(s):
        pass

    runner = RateLimitedRunner(rate_per_sec=1000.0, sleep=fake_sleep, now=lambda: 0.0)

    async def op():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimited(retry_after=0.01)
        return "ok"

    assert await runner.run(op) == "ok"
    assert calls["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_queue.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/notion/queue.py
from __future__ import annotations
import asyncio
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class RateLimited(Exception):
    def __init__(self, retry_after: float = 1.0) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after


class RateLimitedRunner:
    def __init__(self, rate_per_sec: float = 3.0, sleep=asyncio.sleep, now=time.monotonic) -> None:
        self._min_gap = 1.0 / rate_per_sec
        self._sleep = sleep
        self._now = now
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def run(self, coro_fn: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:                       # serializa
            gap = self._min_gap - (self._now() - self._last)
            if gap > 0:
                await self._sleep(gap)
            while True:
                try:
                    result = await coro_fn()
                    self._last = self._now()
                    return result
                except RateLimited as exc:
                    await self._sleep(exc.retry_after)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_queue.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/notion/queue.py server/tests/test_notion_queue.py
git commit -m "feat(notion): RateLimitedRunner (serializa <=3 rps + backoff 429)"
```

---

### Task 7: `notion/client.py` — fetch_page + patch_block_text (SDK mockeado)

**Files:**
- Create: `server/ide_server/notion/client.py`
- Test: `server/tests/test_notion_client.py`

**Interfaces:**
- Produces:
  - `async_client(token: str)` → `AsyncClient` del SDK oficial.
  - `async fetch_page(client, page_id) -> {title, blocks}` — `pages.retrieve` (título de la propiedad title) + `blocks.children.list` paginado (sigue `next_cursor`/`has_more`). (Fase 1: no recursión profunda — sub-bloques de bloques soportados se ignoran; los con `has_children` se traen igual a nivel raíz.)
  - `async patch_block_text(client, notion_id, notion_type, rich_text) -> None` — `blocks.update(block_id=notion_id, **{notion_type: {"rich_text": rich_text}})`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_notion_client.py
import pytest
from ide_server.notion.client import fetch_page, patch_block_text


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_client.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/notion/client.py
from __future__ import annotations


def async_client(token: str):
    from notion_client import AsyncClient
    return AsyncClient(auth=token)


def _title_of(page: dict) -> str:
    props = page.get("properties") or {}
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title") or []
            return "".join(p.get("plain_text", "") for p in parts) or "(sin título)"
    return "(sin título)"


async def fetch_page(client, page_id: str) -> dict:
    page = await client.pages.retrieve(page_id=page_id)
    blocks: list[dict] = []
    cursor = None
    while True:
        resp = await client.blocks.children.list(block_id=page_id, start_cursor=cursor, page_size=100)
        blocks.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return {"title": _title_of(page), "blocks": blocks}


async def patch_block_text(client, notion_id: str, notion_type: str, rich_text: list[dict]) -> None:
    await client.blocks.update(block_id=notion_id, **{notion_type: {"rich_text": rich_text}})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_notion_client.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/notion/client.py server/tests/test_notion_client.py
git commit -m "feat(notion): client fetch_page (paginado) + patch_block_text"
```

---

### Task 8: Capability `notion` + wiring en `app.py`

**Files:**
- Create: `server/ide_server/capabilities/notion.py`
- Modify: `server/ide_server/app.py` (import + register, pasando `home`)
- Test: `server/tests/test_notion_capability.py`

**Interfaces:**
- Consumes: `notion.config.notion_token`, `notion.refs.*`, `notion.adapter.*`, `notion.client.*`, `notion.queue.RateLimitedRunner`.
- Produces: `register(registry, root, home=None)` con `notion.health`, `notion.list`, `notion.add {url}`, `notion.remove {id}`, `notion.page {id}`, `notion.save {id, loaded, edited}`. Inyectable: `register` acepta `client_factory` (default `async_client`) para testear sin SDK real.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_notion_capability.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_notion_capability.py -q`
Expected: FAIL (`ModuleNotFoundError: ...capabilities.notion`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/capabilities/notion.py
from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.notion.config import notion_token
from ide_server.notion import refs, adapter, client as nclient
from ide_server.notion.queue import RateLimitedRunner, RateLimited


def register(registry: Registry, root: Path, home: Path | None = None, client_factory=None) -> None:
    home = home or Path.home()
    make_client = client_factory or nclient.async_client
    runner = RateLimitedRunner()

    def _client():
        token = notion_token(home, root)
        if not token:
            raise RuntimeError("Notion sin token: configurá ~/.ide/config.toml [notion].token")
        return make_client(token)

    async def health(_p: dict) -> dict:
        return {"connected": notion_token(home, root) is not None}

    async def list_(_p: dict) -> dict:
        return {"pages": refs.list_refs(root)}

    async def add(p: dict) -> dict:
        pid = refs.parse_page_id(p["url"])
        page = await nclient.fetch_page(_client(), pid)
        refs.add_ref(root, pid, page["title"])
        return {"page": {"id": pid, "title": page["title"]}}

    async def remove(p: dict) -> dict:
        refs.remove_ref(root, p["id"])
        return {"ok": True}

    async def page(p: dict) -> dict:
        data = await nclient.fetch_page(_client(), p["id"])
        conv = adapter.notion_blocks_to_blocknote(data["blocks"])
        return {"title": data["title"], "blocks": conv["blocks"],
                "unsupportedIds": conv["unsupportedIds"]}

    async def save(p: dict) -> dict:
        # el front reenvía los unsupportedIds que recibió en notion.page (no re-detectar)
        diff = adapter.diff_text_ops(p["loaded"], p["edited"], p.get("unsupportedIds", []))
        cl = _client()
        failed = []
        for op in diff["ops"]:
            try:
                await runner.run(lambda op=op: nclient.patch_block_text(
                    cl, op["notionId"], op["notionType"], op["richText"]))
            except Exception as exc:                   # noqa: BLE001 — se reporta, no se traga
                failed.append({"notionId": op["notionId"], "error": str(exc)})
        return {"applied": len(diff["ops"]) - len(failed), "structural": diff["structural"], "failed": failed}

    for name, fn in [("health", health), ("list", list_), ("add", add),
                     ("remove", remove), ("page", page), ("save", save)]:
        registry.register(f"notion.{name}", fn)
```

El test de `notion.save` (Step 1) manda `unsupportedIds: page["unsupportedIds"]` en el payload.

Wire en `server/ide_server/app.py`: importá `from ide_server.capabilities import notion as notion_cap` y registrá `notion_cap.register(registry, root)` después de `graphite_cap.register(registry, root)`. (Nota: `create_app` no recibe `home`; `register` usa `Path.home()` por default — correcto en producción.)

- [ ] **Step 4: Run test to verify it passes** (capability + app arranca)

Run: `cd server && uv run pytest tests/test_notion_capability.py tests/test_app.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/notion.py server/ide_server/app.py server/tests/test_notion_capability.py
git commit -m "feat(notion): capability health/list/add/remove/page/save + wiring"
```

---

### Task 9: Transport `notionChannel.ts`

**Files:**
- Create: `ui/src/transport/notionChannel.ts`
- Test: `ui/src/transport/notionChannel.test.ts`

**Interfaces:**
- Produces:
  - `interface NotionRef { id: string; title: string }`
  - `type BlockNoteDoc = any[]`
  - `checkHealth(ws) -> Promise<boolean>`
  - `fetchPages(ws) -> Promise<NotionRef[]>`
  - `addPage(ws, url) -> Promise<NotionRef>`
  - `removePage(ws, id) -> Promise<void>`
  - `fetchPage(ws, id) -> Promise<{title, blocks, unsupportedIds}>`
  - `savePage(ws, id, loaded, edited, unsupportedIds) -> Promise<{applied, structural, failed}>`

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/transport/notionChannel.test.ts
import { describe, it, expect, vi } from "vitest";
import { checkHealth, fetchPages, addPage, fetchPage, savePage } from "./notionChannel";

describe("notionChannel", () => {
  it("checkHealth devuelve connected", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ connected: true }) } as any;
    expect(await checkHealth(ws)).toBe(true);
    expect(ws.request).toHaveBeenCalledWith("notion.health", {});
  });
  it("fetchPages devuelve pages", async () => {
    const pages = [{ id: "a", title: "A" }];
    const ws = { request: vi.fn().mockResolvedValue({ pages }) } as any;
    expect(await fetchPages(ws)).toBe(pages);
  });
  it("addPage manda la url", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ page: { id: "a", title: "A" } }) } as any;
    await addPage(ws, "http://n/x");
    expect(ws.request).toHaveBeenCalledWith("notion.add", { url: "http://n/x" });
  });
  it("fetchPage devuelve el doc", async () => {
    const res = { title: "T", blocks: [], unsupportedIds: [] };
    const ws = { request: vi.fn().mockResolvedValue(res) } as any;
    expect(await fetchPage(ws, "id")).toBe(res);
  });
  it("savePage manda loaded/edited/unsupportedIds", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ applied: 1, structural: false, failed: [] }) } as any;
    await savePage(ws, "id", [{ id: "b1" }], [{ id: "b1" }], ["u1"]);
    expect(ws.request).toHaveBeenCalledWith("notion.save",
      { id: "id", loaded: [{ id: "b1" }], edited: [{ id: "b1" }], unsupportedIds: ["u1"] });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- notionChannel`
Expected: FAIL (no existe `./notionChannel`)

- [ ] **Step 3: Write minimal implementation**

```typescript
// ui/src/transport/notionChannel.ts
import type { WsClient } from "./ws";

export interface NotionRef { id: string; title: string }
export type BlockNoteDoc = any[];
export interface PageData { title: string; blocks: BlockNoteDoc; unsupportedIds: string[] }
export interface SaveResult { applied: number; structural: boolean; failed: { notionId: string; error: string }[] }

export async function checkHealth(ws: WsClient): Promise<boolean> {
  return (await ws.request("notion.health", {})).connected;
}
export async function fetchPages(ws: WsClient): Promise<NotionRef[]> {
  return (await ws.request("notion.list", {})).pages;
}
export async function addPage(ws: WsClient, url: string): Promise<NotionRef> {
  return (await ws.request("notion.add", { url })).page;
}
export async function removePage(ws: WsClient, id: string): Promise<void> {
  await ws.request("notion.remove", { id });
}
export async function fetchPage(ws: WsClient, id: string): Promise<PageData> {
  return ws.request("notion.page", { id });
}
export async function savePage(
  ws: WsClient, id: string, loaded: BlockNoteDoc, edited: BlockNoteDoc, unsupportedIds: string[],
): Promise<SaveResult> {
  return ws.request("notion.save", { id, loaded, edited, unsupportedIds });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- notionChannel`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/notionChannel.ts ui/src/transport/notionChannel.test.ts
git commit -m "feat(notion): transport notionChannel"
```

---

### Task 10: State `notion.ts` (lista)

**Files:**
- Create: `ui/src/state/notion.ts`
- Test: `ui/src/state/notion.test.ts`

**Interfaces:**
- Consumes: `checkHealth`, `fetchPages`, `addPage`, `removePage` (Task 9), `getWs`.
- Produces: `useNotion` con `{ connected: boolean, pages: NotionRef[], loading: boolean, error: string | null, load(), add(url), remove(id) }`. En error limpia y setea error.

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/state/notion.test.ts
import { describe, it, expect, beforeEach, vi } from "vitest";
vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const checkHealth = vi.fn(), fetchPages = vi.fn(), addPage = vi.fn(), removePage = vi.fn();
vi.mock("../transport/notionChannel", () => ({
  checkHealth: (...a: any[]) => checkHealth(...a),
  fetchPages: (...a: any[]) => fetchPages(...a),
  addPage: (...a: any[]) => addPage(...a),
  removePage: (...a: any[]) => removePage(...a),
}));
import { useNotion } from "./notion";

beforeEach(() => {
  checkHealth.mockReset(); fetchPages.mockReset(); addPage.mockReset(); removePage.mockReset();
  useNotion.setState({ connected: false, pages: [], loading: false, error: null });
});

describe("state/notion", () => {
  it("load setea connected + pages", async () => {
    checkHealth.mockResolvedValue(true);
    fetchPages.mockResolvedValue([{ id: "a", title: "A" }]);
    await useNotion.getState().load();
    expect(useNotion.getState().connected).toBe(true);
    expect(useNotion.getState().pages).toEqual([{ id: "a", title: "A" }]);
  });
  it("load con error setea error", async () => {
    checkHealth.mockRejectedValue({ message: "boom" });
    await useNotion.getState().load();
    expect(useNotion.getState().error).toBe("boom");
  });
  it("add refresca la lista", async () => {
    checkHealth.mockResolvedValue(true);
    addPage.mockResolvedValue({ id: "b", title: "B" });
    fetchPages.mockResolvedValue([{ id: "b", title: "B" }]);
    await useNotion.getState().add("http://n/b");
    expect(addPage).toHaveBeenCalled();
    expect(useNotion.getState().pages).toEqual([{ id: "b", title: "B" }]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- state/notion`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```typescript
// ui/src/state/notion.ts
import { create } from "zustand";
import type { NotionRef } from "../transport/notionChannel";
import { checkHealth, fetchPages, addPage, removePage } from "../transport/notionChannel";
import { getWs } from "../transport/wsClient";

interface NotionState {
  connected: boolean; pages: NotionRef[]; loading: boolean; error: string | null;
  load: () => Promise<void>;
  add: (url: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}
const msg = (e: unknown) => (e as { message?: string })?.message ?? "desconectado";

export const useNotion = create<NotionState>((set, get) => ({
  connected: false, pages: [], loading: false, error: null,
  load: async () => {
    set({ loading: true });
    try {
      const connected = await checkHealth(getWs());
      const pages = connected ? await fetchPages(getWs()) : [];
      set({ connected, pages, loading: false, error: null });
    } catch (e) { set({ loading: false, error: msg(e) }); }
  },
  add: async (url) => {
    try { await addPage(getWs(), url); set({ pages: await fetchPages(getWs()), error: null }); }
    catch (e) { set({ error: msg(e) }); }
  },
  remove: async (id) => {
    try { await removePage(getWs(), id); set({ pages: await fetchPages(getWs()) }); }
    catch (e) { set({ error: msg(e) }); }
  },
}));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- state/notion`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ui/src/state/notion.ts ui/src/state/notion.test.ts
git commit -m "feat(notion): store zustand (health + lista + add/remove)"
```

---

### Task 11: `NotionPanel` + registro del módulo

**Files:**
- Create: `ui/src/modules/notion/NotionPanel.tsx`
- Create: `ui/src/modules/notion/register.tsx`
- Create: `ui/src/modules/notion/NotionPanel.test.tsx`
- Create: `ui/src/modules/notion/register.test.ts`
- Modify: `ui/src/modules/stubs.tsx` (quitar `notion`; quitar `BookOpen` si queda sin uso)
- Modify: `ui/src/App.tsx` (`import "./modules/notion/register";`)
- Modify: `ui/src/modules/registry.test.ts` (`import "./notion/register";`)

**Interfaces:**
- Consumes: `useNotion` (Task 10), `useStore` (`openTab`).
- Produces: `NotionPanel`; módulo `id:"notion"`. Click página → `openTab({id:'notion:'+id, type:'page', label:title})`. "+ Nueva" → input de URL → `add`. Estado "conectá Notion" si `!connected`.

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/modules/notion/NotionPanel.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useNotion } from "../../state/notion";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const load = vi.fn(), add = vi.fn(), remove = vi.fn();
import { NotionPanel } from "./NotionPanel";

function setState(over: any) {
  useNotion.setState({ connected: true, pages: [], loading: false, error: null, load, add, remove, ...over });
}
beforeEach(() => {
  load.mockReset(); add.mockReset();
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
  setState({});
});

describe("NotionPanel", () => {
  it("sin conexión muestra 'conectá Notion'", () => {
    setState({ connected: false });
    render(<NotionPanel />);
    expect(screen.getByText(/conectá notion/i)).toBeInTheDocument();
  });
  it("lista páginas y abre tab al click", () => {
    setState({ pages: [{ id: "p1", title: "Mi Página" }] });
    render(<NotionPanel />);
    fireEvent.click(screen.getByText("Mi Página"));
    expect(useStore.getState().openTabs[0]).toMatchObject({ id: "notion:p1", type: "page", label: "Mi Página" });
  });
  it("+ Nueva agrega por URL", () => {
    setState({ pages: [] });
    render(<NotionPanel />);
    fireEvent.click(screen.getByText(/nueva/i));
    fireEvent.change(screen.getByPlaceholderText(/url/i), { target: { value: "http://notion.so/x" } });
    fireEvent.keyDown(screen.getByPlaceholderText(/url/i), { key: "Enter" });
    expect(add).toHaveBeenCalledWith("http://notion.so/x");
  });
});
```

```typescript
// ui/src/modules/notion/register.test.ts
import { describe, it, expect } from "vitest";
import "../stubs";
import "./register";
import { getModules } from "../registry";
import { NotionPanel } from "./NotionPanel";
describe("registro notion", () => {
  it("usa el NotionPanel real", () => {
    expect(getModules().find((m) => m.id === "notion")?.Panel).toBe(NotionPanel);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- notion`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/modules/notion/NotionPanel.tsx
import { useEffect, useState } from "react";
import { Plus, RefreshCw, FileText } from "lucide-react";
import { useNotion } from "../../state/notion";
import { useStore } from "../../state/store";

export function NotionPanel() {
  const { connected, pages, error, load, add } = useNotion();
  const openTab = useStore((s) => s.openTab);
  const [adding, setAdding] = useState(false);
  const [url, setUrl] = useState("");

  useEffect(() => { load(); }, [load]);

  if (!connected && !error) {
    return <div className="p-3 text-xs text-muted-foreground">conectá Notion — configurá el token en <code>~/.ide/config.toml</code></div>;
  }
  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Notion</span>
        <div className="flex items-center gap-1">
          <button aria-label="refrescar" onClick={() => load()} className="text-muted-foreground hover:text-foreground"><RefreshCw size={13} /></button>
          <button onClick={() => setAdding(true)} className="flex items-center gap-1 text-[11px] font-semibold text-[#e0863f]"><Plus size={12} />Nueva</button>
        </div>
      </div>
      {adding && (
        <input autoFocus placeholder="URL de la página de Notion" value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && url) { add(url); setUrl(""); setAdding(false); } if (e.key === "Escape") setAdding(false); }}
          className="mb-2 w-full rounded border border-border bg-background px-2 py-1 font-mono text-[11.5px]" />
      )}
      {error && <div className="px-1 py-2 text-xs text-destructive">desconectado — {error}</div>}
      {pages.map((p) => (
        <button key={p.id} onClick={() => openTab({ id: `notion:${p.id}`, type: "page", label: p.title })}
          className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left hover:bg-accent">
          <FileText size={13} className="mt-0.5 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-foreground">{p.title}</span>
        </button>
      ))}
    </div>
  );
}
```

```tsx
// ui/src/modules/notion/register.tsx
import { BookOpen } from "lucide-react";
import { registerModule } from "../registry";
import { NotionPanel } from "./NotionPanel";
registerModule({ id: "notion", title: "Notion", icon: BookOpen, Panel: NotionPanel });
```

Editá `stubs.tsx` (quitar la línea `notion` y `BookOpen` del import si queda sin uso), `App.tsx` (agregar el import del register) y `registry.test.ts` (agregar `import "./notion/register";`), igual que se hizo con changes/graphite.

- [ ] **Step 4: Run test to verify it passes** (notion + tsc + suite)

Run: `cd ui && npm test -- notion && cd ui && npx tsc --noEmit && npm test`
Expected: PASS; tsc limpio; suite verde

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/notion ui/src/modules/stubs.tsx ui/src/App.tsx ui/src/modules/registry.test.ts
git commit -m "feat(notion): NotionPanel en el rail (lista + agregar por URL)"
```

---

### Task 12: `NotionPageTab` — editor BlockNote + save con debounce

**Files:**
- Create: `ui/src/main/NotionPageTab.tsx`
- Create: `ui/src/main/NotionPageTab.test.tsx`
- Modify: `ui/src/layout/MainPanel.tsx` (rutear `type==="page"`)
- Modify: `ui/package.json` (deps BlockNote)

**Interfaces:**
- Consumes: `fetchPage`, `savePage` (Task 9), `getWs`. Recibe `id:"notion:<pageId>"`.
- Produces: `NotionPageTab({ id })` — carga la página, monta BlockNote con `initialContent=blocks`, `onChange` con debounce ~800ms → `savePage(loaded, edited, unsupportedIds)`; indicador de estado (guardado/guardando/error); banner si `structural`.

- [ ] **Step 1: Add BlockNote deps**

Run: `cd ui && npm install @blocknote/core@0.51.4 @blocknote/react@0.51.4 @blocknote/mantine@0.51.4`
Expected: packages added to `package.json`.

- [ ] **Step 2: Write the failing test** (BlockNote se **mockea** — ProseMirror no monta limpio en jsdom; se testea el wiring)

```typescript
// ui/src/main/NotionPageTab.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchPage = vi.fn(), savePage = vi.fn();
vi.mock("../transport/notionChannel", () => ({
  fetchPage: (...a: any[]) => fetchPage(...a),
  savePage: (...a: any[]) => savePage(...a),
}));
// Mock del editor: expone un botón que dispara onChange con un doc editado.
vi.mock("./NotionEditor", () => ({
  NotionEditor: ({ onChange }: any) => (
    <button onClick={() => onChange([{ id: "b1", type: "paragraph", content: [{ type: "text", text: "z", styles: {} }] }])}>edit</button>
  ),
}));
import { NotionPageTab } from "./NotionPageTab";

beforeEach(() => { fetchPage.mockReset(); savePage.mockReset(); vi.useFakeTimers(); });

describe("NotionPageTab", () => {
  it("carga la página y guarda (debounce) al editar", async () => {
    fetchPage.mockResolvedValue({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: ["u1"] });
    savePage.mockResolvedValue({ applied: 1, structural: false, failed: [] });
    render(<NotionPageTab id="notion:pageX" />);
    await vi.waitFor(() => screen.getByText("edit"));
    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    expect(savePage).toHaveBeenCalledWith(expect.anything(), "pageX",
      [{ id: "b1", type: "paragraph", content: [] }], expect.any(Array), ["u1"]);
    vi.useRealTimers();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ui && npm test -- NotionPageTab`
Expected: FAIL (no existen `./NotionPageTab` / `./NotionEditor`)

- [ ] **Step 4: Write minimal implementation**

`NotionEditor.tsx` aísla BlockNote (así el tab es testeable con el editor mockeado):

```tsx
// ui/src/main/NotionEditor.tsx
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import "@blocknote/mantine/style.css";
import type { BlockNoteDoc } from "../transport/notionChannel";

export function NotionEditor({ initial, onChange }: { initial: BlockNoteDoc; onChange: (doc: BlockNoteDoc) => void }) {
  const editor = useCreateBlockNote({ initialContent: initial.length ? (initial as any) : undefined });
  return <BlockNoteView editor={editor} onChange={() => onChange(editor.document as any)} />;
}
```

```tsx
// ui/src/main/NotionPageTab.tsx
import { useEffect, useRef, useState } from "react";
import { fetchPage, savePage, type BlockNoteDoc } from "../transport/notionChannel";
import { getWs } from "../transport/wsClient";
import { NotionEditor } from "./NotionEditor";

type Status = "idle" | "saving" | "saved" | "error";

export function NotionPageTab({ id }: { id: string }) {
  const pageId = id.slice("notion:".length);
  const [title, setTitle] = useState("");
  const [loaded, setLoaded] = useState<BlockNoteDoc | null>(null);
  const [unsupported, setUnsupported] = useState<string[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [structural, setStructural] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    let cancelled = false;
    fetchPage(getWs(), pageId)
      .then((d) => { if (!cancelled) { setTitle(d.title); setLoaded(d.blocks); setUnsupported(d.unsupportedIds); } })
      .catch((e) => { if (!cancelled) setError((e as { message?: string })?.message ?? "desconectado"); });
    return () => { cancelled = true; };
  }, [pageId]);

  function onChange(edited: BlockNoteDoc) {
    if (!loaded) return;
    clearTimeout(timer.current);
    setStatus("saving");
    timer.current = setTimeout(async () => {
      try {
        const res = await savePage(getWs(), pageId, loaded, edited, unsupported);
        setStructural(res.structural);
        if (res.failed.length) { setStatus("error"); }
        else { setStatus("saved"); if (!res.structural) setLoaded(edited); }
        if (res.structural) {
          const d = await fetchPage(getWs(), pageId);      // re-sync tras estructural
          setLoaded(d.blocks); setUnsupported(d.unsupportedIds);
        }
      } catch (e) { setStatus("error"); setError((e as { message?: string })?.message ?? "error"); }
    }, 800);
  }

  if (error) return <div className="p-4 text-sm text-destructive">no se pudo abrir la página — {error}</div>;
  if (!loaded) return <div className="p-4 text-sm text-muted-foreground">cargando…</div>;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-5 py-3">
        <span className="text-lg font-bold text-foreground">{title}</span>
        <span className="text-[10px] text-muted-foreground">
          {status === "saving" ? "guardando…" : status === "saved" ? "guardado" : status === "error" ? "error al guardar" : ""}
        </span>
      </div>
      {structural && (
        <div className="border-b border-border bg-[#2e2820] px-5 py-2 text-[11px] text-[#e0863f]">
          Los cambios de estructura (agregar/quitar bloques) llegan en Fase 2; se guardaron solo las ediciones de texto.
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        <NotionEditor initial={loaded} onChange={onChange} />
      </div>
    </div>
  );
}
```

Rutea en `ui/src/layout/MainPanel.tsx`: agregá una rama `active?.type === "page" ? <NotionPageTab id={active.id} /> : …` (importá `NotionPageTab`), conservando terminal/file/placeholder/ChatView.

- [ ] **Step 5: Run test + tsc + build + suite**

Run: `cd ui && npm test -- NotionPageTab && cd ui && npx tsc --noEmit && npm run build && npm test`
Expected: PASS; tsc limpio; build ok; suite verde. (Si el build/tsc se queja por tipos de BlockNote, ajustá los `as any` mínimos necesarios en `NotionEditor.tsx`.)

- [ ] **Step 6: Commit**

```bash
git add ui/src/main/NotionPageTab.tsx ui/src/main/NotionEditor.tsx ui/src/main/NotionPageTab.test.tsx ui/src/layout/MainPanel.tsx ui/package.json ui/package-lock.json
git commit -m "feat(notion): NotionPageTab con editor BlockNote + save debounced"
```

---

## Verificación final (post Task 12)

- [ ] Backend: `cd server && uv run pytest -q` → verde (125 previos + nuevos).
- [ ] Frontend: `cd ui && npm test` → verde; `npx tsc --noEmit` limpio; `npm run build` ok.
- [ ] E2E manual: token real en `~/.ide/config.toml [notion].token`, compartir una página con la integración, agregarla por URL, abrirla (render BlockNote), editar texto, ver "guardado" y confirmar el cambio en Notion.
- [ ] Actualizar `docs/superpowers/HANDOFF.md`: R-Notion Fase 1 cerrado; Fase 2 (estructural + título) y Tasks como próximos.

## Self-Review (notas del plan)

- **Cobertura del spec:** config/token (T1), refs+URL (T2), adapter inline (T3), bloques+inertes (T4), diff (T5), cola rate-limit (T6), client SDK (T7), capability (T8), transport (T9), store (T10), panel (T11), tab+BlockNote (T12). Fuera de alcance (estructural, título, no-soportados activos, crear páginas) no se implementa.
- **Sin fallos silenciosos:** token ausente → `connected:false` → "conectá Notion"; API error → envelope; `failed` reportado + re-fetch; estructural → banner + re-sync; inertes nunca reciben op.
- **BlockNote id = Notion id** → diff por id sin id-map; estructural detectado por cambio del set de ids.
- **Riesgo de shape de BlockNote 0.51.4:** los tests del adapter (T4) fijan el contrato; si la lib difiere, ajustar el test a la lib y anotarlo. El editor se aísla en `NotionEditor.tsx` y se mockea en los tests del tab (ProseMirror no monta en jsdom).
- **Tipos consistentes:** `NotionRef`, `BlockNoteDoc`, `PageData`, `SaveResult`; `notion.save {id, loaded, edited, unsupportedIds}` en transport, capability y store.
