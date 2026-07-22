from ide_server.mlx.config import mlx_config, DEFAULT_ROUTER_PROMPT


def _write(root, body):
    (root / ".ide").mkdir(parents=True, exist_ok=True)
    (root / ".ide" / "config.toml").write_text(body)


def test_none_when_no_section(tmp_path):
    _write(tmp_path, 'name = "x"\n')
    assert mlx_config(tmp_path) is None


def test_none_when_disabled(tmp_path):
    _write(tmp_path, '[mlx]\nenabled = false\nmodel = "m"\n')
    assert mlx_config(tmp_path) is None


def test_enabled_uses_default_prompt(tmp_path):
    _write(tmp_path, '[mlx]\nenabled = true\nmodel = "mlx-community/Q"\n')
    cfg = mlx_config(tmp_path)
    assert cfg.model == "mlx-community/Q"
    assert cfg.router_prompt == DEFAULT_ROUTER_PROMPT
    assert cfg.port is None


def test_custom_prompt_and_port(tmp_path):
    _write(tmp_path, '[mlx]\nenabled = true\nmodel = "m"\nrouter_prompt = "PROMPT"\nport = 9001\n')
    cfg = mlx_config(tmp_path)
    assert cfg.router_prompt == "PROMPT" and cfg.port == 9001


def test_none_when_no_config_file(tmp_path):
    assert mlx_config(tmp_path) is None
