import pytest
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.capabilities import search as search_cap


def _seed(tmp_path: Path):
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir(exist_ok=True)
    save_sessions(tmp_path, [{"id": "s1", "worktreePath": str(tmp_path)}])
    (tmp_path / "a.py").write_text("import os\nprint('hola')\nprint('chau')\n")
    (tmp_path / "b.txt").write_text("solo texto sin match\n")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "c.py").write_text("PRINT MAYUS\nprint('x')\n")


async def _run(tmp_path, query, options=None):
    reg = Registry()
    search_cap.register(reg, tmp_path)
    return await reg.dispatch("search.content",
        {"sessionId": "s1", "query": query, "options": options or {}})


@pytest.mark.asyncio
async def test_literal_encuentra_agrupado_por_archivo(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "print", {"regex": False, "caseSensitive": True})
    paths = {m["path"] for m in out["matches"]}
    assert paths == {"a.py", "sub/c.py"}         # b.txt no matchea; agrupado por archivo
    a = next(m for m in out["matches"] if m["path"] == "a.py")
    assert [l["line"] for l in a["lines"]] == [2, 3]
    assert a["lines"][0]["ranges"] == [[0, 5]]   # 'print' en offset 0..5
    assert out["total"] == 3 and out["files"] == 2 and out["truncated"] is False


@pytest.mark.asyncio
async def test_sin_match_no_es_error(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "xyz-inexistente")
    assert out == {"matches": [], "total": 0, "files": 0, "truncated": False}


@pytest.mark.asyncio
async def test_query_vacia_devuelve_vacio(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "")
    assert out["total"] == 0 and out["matches"] == []


@pytest.mark.asyncio
async def test_regex_invalido_da_bad_regex(tmp_path):
    _seed(tmp_path)
    with pytest.raises(search_cap.SearchError) as ei:
        await _run(tmp_path, "(", {"regex": True})
    assert ei.value.code == "bad_regex"


@pytest.mark.asyncio
async def test_include_exclude_globs(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "print", {"regex": False, "caseSensitive": True,
                                         "include": ["*.py"], "exclude": ["sub/**"]})
    assert {m["path"] for m in out["matches"]} == {"a.py"}   # sub/c.py excluido, b.txt no es *.py


@pytest.mark.asyncio
async def test_case_insensitive_por_default(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "print", {"regex": False})     # sin caseSensitive → -i
    assert any(m["path"] == "sub/c.py" and any(l["line"] == 1 for l in m["lines"])
               for m in out["matches"])                        # matchea 'PRINT MAYUS'
