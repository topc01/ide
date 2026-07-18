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
