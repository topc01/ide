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
