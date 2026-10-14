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
    rt = [_rt("aquí", link="https://x.com")]
    inline = notion_richtext_to_inline(rt)
    assert inline[0] == {
        "type": "link", "href": "https://x.com",
        "content": [{"type": "text", "text": "aquí", "styles": {}}]}


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
