import pytest
from ide_server.plugins import Registry
import ide_server.capabilities.mlx_config as cap


def _reg(root):
    reg = Registry(); cap.register(reg, root); return reg


@pytest.mark.asyncio
async def test_get_returns_camel_defaults(tmp_path):
    out = await _reg(tmp_path).dispatch("mlx.config.get", {})
    assert out["enabled"] is False and out["model"] == ""
    assert out["defaultPrompt"] and out["routerPrompt"] == out["defaultPrompt"]


@pytest.mark.asyncio
async def test_set_writes_and_get_reflects(tmp_path):
    reg = _reg(tmp_path)
    assert await reg.dispatch("mlx.config.set",
        {"enabled": True, "model": "mlx-community/X", "routerPrompt": ""}) == {"saved": True}
    out = await reg.dispatch("mlx.config.get", {})
    assert out["enabled"] is True and out["model"] == "mlx-community/X"


@pytest.mark.asyncio
async def test_set_enabled_without_model_raises(tmp_path):
    with pytest.raises(ValueError):
        await _reg(tmp_path).dispatch("mlx.config.set",
            {"enabled": True, "model": "  ", "routerPrompt": ""})


@pytest.mark.asyncio
async def test_set_disabled_without_model_ok(tmp_path):
    assert await _reg(tmp_path).dispatch("mlx.config.set",
        {"enabled": False, "model": "", "routerPrompt": ""}) == {"saved": True}
