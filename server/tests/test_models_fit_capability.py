import pytest
from ide_server.plugins import Registry
import ide_server.capabilities.models_fit as cap
from ide_server.models.fit import FitInfo


class _FakeFit:
    def __init__(self, mapping): self._m = mapping
    async def fit_for(self, repo_ids): return {r: self._m.get(r) for r in repo_ids}


def _fi():
    return FitInfo("a", "ok", "Perfect", 6.7, 24.0, 9.5, 5.8, "mlx-8bit", 32768, 87.0,
                   {"fit": 100, "speed": 20, "quality": 99, "context": 100})


@pytest.mark.asyncio
async def test_models_fit_serializes_camel(tmp_path):
    reg = Registry(); cap.register(reg, tmp_path, fit=_FakeFit({"a": _fi()}))
    out = await reg.dispatch("models.fit", {"repoIds": ["a"]})
    assert out["a"]["level"] == "ok" and out["a"]["estimatedTps"] == 9.5
    assert out["a"]["memoryRequiredGb"] == 6.7 and out["a"]["scoreComponents"]["speed"] == 20


@pytest.mark.asyncio
async def test_models_fit_none_stays_null(tmp_path):
    reg = Registry(); cap.register(reg, tmp_path, fit=_FakeFit({"a": None}))
    assert await reg.dispatch("models.fit", {"repoIds": ["a"]}) == {"a": None}


@pytest.mark.asyncio
async def test_models_fit_empty_repoids(tmp_path):
    reg = Registry(); cap.register(reg, tmp_path, fit=_FakeFit({}))
    assert await reg.dispatch("models.fit", {}) == {}
