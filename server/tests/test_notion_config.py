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


from ide_server.notion.config import write_token, clear_token


def test_write_token_creates_and_preserves(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    home = tmp_path / "home"
    # sección previa que NO se debe pisar
    (home / ".ide").mkdir(parents=True)
    (home / ".ide" / "config.toml").write_text('name = "demo"\n')
    write_token(home, "secret-abc")
    import tomllib
    data = tomllib.loads((home / ".ide" / "config.toml").read_text())
    assert data["name"] == "demo"
    assert data["notion"]["token"] == "secret-abc"
    assert notion_token(home, tmp_path / "no-root") == "secret-abc"


def test_write_token_creates_dir_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    home = tmp_path / "fresh"
    write_token(home, "tok")
    assert notion_token(home, tmp_path / "no-root") == "tok"


def test_clear_token_removes_and_keeps_rest(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    home = tmp_path / "home"
    (home / ".ide").mkdir(parents=True)
    (home / ".ide" / "config.toml").write_text('name = "demo"\n[notion]\ntoken = "x"\n')
    clear_token(home)
    import tomllib
    data = tomllib.loads((home / ".ide" / "config.toml").read_text())
    assert data["name"] == "demo" and "notion" not in data
    assert notion_token(home, tmp_path / "no-root") is None


def test_clear_token_missing_file_noop(tmp_path):
    clear_token(tmp_path / "nope")   # no explota
