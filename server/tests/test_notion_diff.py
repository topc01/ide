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
