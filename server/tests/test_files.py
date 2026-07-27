import pytest
from ide_server.plugins import Registry
import ide_server.capabilities.files as files_cap
from ide_server.capabilities.files import _safe_join


def test_safe_join_ok_and_escape(tmp_path):
    assert _safe_join(tmp_path, "a/b") == (tmp_path.resolve() / "a" / "b")
    assert _safe_join(tmp_path, "") == tmp_path.resolve()
    with pytest.raises(ValueError):
        _safe_join(tmp_path, "../escape")


@pytest.mark.asyncio
async def test_list_dirs_first_then_files(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir(); (tmp_path / "a.txt").write_text("x")
    (tmp_path / "src" / "b.py").write_text("y")
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    reg = Registry(); files_cap.register(reg, tmp_path)
    out = await reg.dispatch("files.list", {"sessionId": "s", "path": ""})
    pairs = [(e["name"], e["type"]) for e in out["entries"]]
    assert ("src", "dir") in pairs and ("a.txt", "file") in pairs
    assert pairs[0][1] == "dir"                       # dirs primero


@pytest.mark.asyncio
async def test_list_subdir(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "b.py").write_text("y")
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    reg = Registry(); files_cap.register(reg, tmp_path)
    out = await reg.dispatch("files.list", {"sessionId": "s", "path": "src"})
    assert [e["name"] for e in out["entries"]] == ["b.py"]


@pytest.mark.asyncio
async def test_list_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    reg = Registry(); files_cap.register(reg, tmp_path)
    with pytest.raises(ValueError):
        await reg.dispatch("files.list", {"sessionId": "s", "path": "../.."})


@pytest.mark.asyncio
async def test_open_delegates_to_terminal(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("x")
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    monkeypatch.setenv("EDITOR", "vim")
    reg = Registry(); files_cap.register(reg, tmp_path)
    captured = {}
    async def fake_term(payload): captured.update(payload); return {"id": "t1", "cwd": str(tmp_path)}
    reg.register("terminal.open", fake_term)
    out = await reg.dispatch("files.open", {"sessionId": "s", "path": "a.txt"})
    assert out == {"id": "t1", "cwd": str(tmp_path)}
    assert captured["cmd"] == ["vim", str((tmp_path.resolve() / "a.txt"))]
    assert captured["sessionId"] == "s"


@pytest.mark.asyncio
async def test_open_con_line_antepone_mas_n(tmp_path, monkeypatch):
    (tmp_path / "x.py").write_text("a\nb\nc\n")
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    monkeypatch.setenv("EDITOR", "vim")
    reg = Registry(); files_cap.register(reg, tmp_path)
    captured = {}
    async def fake_term(payload): captured.update(payload); return {"id": "t1", "cwd": str(tmp_path)}
    reg.register("terminal.open", fake_term)
    await reg.dispatch("files.open", {"sessionId": "s", "path": "x.py", "line": 2})
    assert captured["cmd"] == ["vim", "+2", str((tmp_path.resolve() / "x.py"))]
