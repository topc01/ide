from pathlib import Path
from ide_server.cli import init_workspace, resolve_root, main

def test_init_creates_ide(tmp_path):
    ide = init_workspace(tmp_path)
    assert ide == tmp_path / ".ide"
    assert (ide / "config.toml").is_file()

def test_resolve_root_after_init(tmp_path):
    init_workspace(tmp_path)
    assert resolve_root(tmp_path) == tmp_path

def test_main_without_workspace_returns_1(tmp_path, capsys):
    code = main(["--cwd", str(tmp_path)])   # no .ide/ → sugiere init
    assert code == 1
    assert "ide init" in capsys.readouterr().out
