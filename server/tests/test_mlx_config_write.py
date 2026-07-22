import tomllib
from ide_server.mlx.config import mlx_config_raw, write_mlx_config, mlx_config, DEFAULT_ROUTER_PROMPT


def test_raw_defaults_without_config(tmp_path):
    assert mlx_config_raw(tmp_path) == {
        "enabled": False, "model": "", "router_prompt": DEFAULT_ROUTER_PROMPT,
        "default_prompt": DEFAULT_ROUTER_PROMPT}


def test_raw_reads_values(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "config.toml").write_text('[mlx]\nenabled = true\nmodel = "m"\n')
    r = mlx_config_raw(tmp_path)
    assert r["enabled"] is True and r["model"] == "m"
    assert r["router_prompt"] == DEFAULT_ROUTER_PROMPT and r["default_prompt"] == DEFAULT_ROUTER_PROMPT


def test_write_preserves_other_sections_and_port(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "config.toml").write_text(
        '[roles]\narquitecto = { model = "opus" }\n\n[mlx]\nport = 9001\n')
    write_mlx_config(tmp_path, enabled=True, model="mlx-community/X",
                     router_prompt=DEFAULT_ROUTER_PROMPT)
    data = tomllib.loads((tmp_path / ".ide" / "config.toml").read_text())
    assert data["roles"]["arquitecto"]["model"] == "opus"       # preservado
    assert data["mlx"]["port"] == 9001                          # preservado
    assert data["mlx"]["enabled"] is True and data["mlx"]["model"] == "mlx-community/X"
    assert "router_prompt" not in data["mlx"]                   # == default → no se persiste
    cfg = mlx_config(tmp_path)
    assert cfg.model == "mlx-community/X" and cfg.port == 9001


def test_write_persists_custom_prompt(tmp_path):
    write_mlx_config(tmp_path, enabled=True, model="m", router_prompt="MI PROMPT")
    data = tomllib.loads((tmp_path / ".ide" / "config.toml").read_text())
    assert data["mlx"]["router_prompt"] == "MI PROMPT"
    assert mlx_config_raw(tmp_path)["router_prompt"] == "MI PROMPT"


def test_write_creates_ide_dir(tmp_path):
    write_mlx_config(tmp_path, enabled=False, model="", router_prompt=DEFAULT_ROUTER_PROMPT)
    assert (tmp_path / ".ide" / "config.toml").is_file()
