import tomllib
from pathlib import Path
from ide_server.notion.config import notion_token


def _write(p: Path, token: str) -> None:
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.toml").write_text(f'[notion]\ntoken = "{token}"\n')


def test_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "env-tok")
    assert notion_token(tmp_path / "home", tmp_path / "root") == "env-tok"


def test_local_over_global(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    _write(tmp_path / "home" / ".ide", "global-tok")
    _write(tmp_path / "root" / ".ide", "local-tok")
    assert notion_token(tmp_path / "home", tmp_path / "root") == "local-tok"


def test_global_fallback_and_none(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    _write(tmp_path / "home" / ".ide", "global-tok")
    assert notion_token(tmp_path / "home", tmp_path / "root") == "global-tok"
    assert notion_token(tmp_path / "empty-home", tmp_path / "empty-root") is None
