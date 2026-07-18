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
