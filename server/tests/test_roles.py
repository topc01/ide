from pathlib import Path
import pytest
from ide_server.roles import Role, PRESETS, load_roles, resolve_role


def _ws(tmp_path: Path, toml: str = "") -> Path:
    ide = tmp_path / ".ide"; ide.mkdir()
    if toml:
        (ide / "config.toml").write_text(toml)
    return tmp_path


def test_presets_have_readonly_flags():
    assert PRESETS["lector"].read_only is True
    assert PRESETS["revisor"].read_only is True
    assert PRESETS["arquitecto"].read_only is False


def test_resolve_none_is_no_role(tmp_path):
    assert resolve_role(_ws(tmp_path), None) is None


def test_resolve_preset(tmp_path):
    role = resolve_role(_ws(tmp_path), "lector")
    assert role.read_only is True


def test_config_overrides_and_adds(tmp_path):
    ws = _ws(tmp_path, '[roles.qa]\nmodel = "haiku"\nread_only = true\n')
    roles = load_roles(ws)
    assert roles["qa"].model == "haiku"
    assert roles["qa"].read_only is True
    # los presets siguen presentes
    assert "arquitecto" in roles


def test_resolve_unknown_raises(tmp_path):
    with pytest.raises(KeyError):
        resolve_role(_ws(tmp_path), "no-existe")
