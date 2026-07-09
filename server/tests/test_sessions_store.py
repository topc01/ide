# server/tests/test_sessions_store.py
from pathlib import Path
from ide_server.sessions_store import (
    slugify, load_sessions, save_sessions,
    find_node, insert_node, rename_node, remove_node,
)


def _ws(tmp_path: Path) -> Path:
    (tmp_path / ".ide").mkdir()
    return tmp_path


def test_slugify():
    assert slugify("Fix Login v2") == "fix-login-v2"


def test_load_missing_is_empty(tmp_path):
    assert load_sessions(_ws(tmp_path)) == []


def test_save_and_load_roundtrip(tmp_path):
    ws = _ws(tmp_path)
    save_sessions(ws, [{"id": "a", "name": "A", "children": []}])
    assert load_sessions(ws)[0]["name"] == "A"


def test_corrupt_json_backs_up_and_resets(tmp_path):
    ws = _ws(tmp_path)
    (ws / ".ide" / "sessions.json").write_text("{not json")
    assert load_sessions(ws) == []
    assert (ws / ".ide" / "sessions.json.bak").is_file()


def test_insert_find_rename_remove():
    tree: list[dict] = []
    insert_node(tree, None, {"id": "root", "name": "Root", "children": []})
    insert_node(tree, "root", {"id": "child", "name": "Child", "children": []})
    assert find_node(tree, "child")["name"] == "Child"
    assert rename_node(tree, "child", "Nuevo") is True
    assert find_node(tree, "child")["name"] == "Nuevo"
    assert remove_node(tree, "root") is True          # remueve root + hijo
    assert find_node(tree, "child") is None
