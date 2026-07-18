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
