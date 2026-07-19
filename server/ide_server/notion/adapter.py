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


_BN_TO_NOTION = {"paragraph": "paragraph", "bulletListItem": "bulleted_list_item",
                 "numberedListItem": "numbered_list_item", "checkListItem": "to_do",
                 "quote": "quote", "codeBlock": "code"}


def _notion_type(bn_block: dict) -> str:
    t = bn_block["type"]
    if t == "heading":
        return f"heading_{(bn_block.get('props') or {}).get('level', 1)}"
    return _BN_TO_NOTION.get(t, "paragraph")


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
