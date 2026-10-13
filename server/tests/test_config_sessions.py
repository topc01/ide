import pytest
from ide_server.config import sessions_config, reviews_config, ui_modules


def _cfg(tmp_path, text=""):
    (tmp_path / ".ide").mkdir(exist_ok=True)
    (tmp_path / ".ide" / "config.toml").write_text(text)
    return tmp_path


def test_defaults(tmp_path):
    root = _cfg(tmp_path)
    assert sessions_config(root) == {"default_permissions": "analyze", "max_running": None,
                                     "claude_command": "claude"}
    assert reviews_config(root) == {"poll_interval": 300}
    assert ui_modules(root) == ["sessions", "terminal"]


def test_overrides(tmp_path):
    root = _cfg(tmp_path, '[sessions]\ndefault_permissions = "full"\nmax_running = 3\n'
                          '[reviews]\npoll_interval = 0\n[ui]\nmodules = ["sessions", "chat"]\n')
    assert sessions_config(root)["default_permissions"] == "full"
    assert sessions_config(root)["max_running"] == 3
    assert reviews_config(root)["poll_interval"] == 0
    assert ui_modules(root) == ["sessions", "chat"]


def test_bad_permissions(tmp_path):
    root = _cfg(tmp_path, '[sessions]\ndefault_permissions = "yolo"\n')
    with pytest.raises(ValueError, match="default_permissions"):
        sessions_config(root)
