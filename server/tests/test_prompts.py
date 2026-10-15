import pytest
from ide_server.prompts import list_prompts
from ide_server.sessions_fs import SessionError


def test_list_prompts_sorted_by_name(tmp_path):
    d = tmp_path / ".ide" / "prompts"; d.mkdir(parents=True)
    (d / "b.md").write_text("segundo\n", encoding="utf-8")
    (d / "a.md").write_text("primero", encoding="utf-8")
    (d / "notas.txt").write_text("ignorado", encoding="utf-8")
    assert list_prompts(tmp_path) == [{"name": "a", "text": "primero"},
                                      {"name": "b", "text": "segundo\n"}]


def test_list_prompts_without_dir_is_empty(tmp_path):
    assert list_prompts(tmp_path) == []


def test_list_prompts_unreadable_raises(tmp_path):
    d = tmp_path / ".ide" / "prompts"; d.mkdir(parents=True)
    (d / "roto.md").write_bytes(b"\xff\xfe")
    with pytest.raises(SessionError) as e:
        list_prompts(tmp_path)
    assert e.value.code == "bad_prompt" and "roto.md" in str(e.value)
