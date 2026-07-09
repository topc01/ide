# server/tests/test_config.py
from pathlib import Path
from ide_server.config import Settings, load_workspace_config

def test_defaults():
    s = Settings()
    assert s.port == 8787
    assert "http://localhost:5173" in s.cors_origins

def test_load_config(tmp_path):
    ide = tmp_path / ".ide"; ide.mkdir()
    (ide / "config.toml").write_text('name = "finnecto"\n')
    assert load_workspace_config(tmp_path)["name"] == "finnecto"

def test_load_config_missing(tmp_path):
    assert load_workspace_config(tmp_path) == {}
