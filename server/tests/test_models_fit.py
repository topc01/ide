import pytest
from ide_server.models.fit import level_from, ModelFit, FitInfo, _run_llmfit


def test_level_from():
    assert level_from(10, 24) == "ok"       # 0.42
    assert level_from(18, 24) == "ok"       # 0.75 (borde inclusive)
    assert level_from(20, 24) == "tight"    # 0.83
    assert level_from(24, 24) == "tight"    # 1.0
    assert level_from(40, 24) == "no"       # 1.67
    assert level_from(5, 0) == "no"         # sin memoria conocida


RAW = {"fit_label": "Perfect", "memory_required_gb": 6.72, "memory_available_gb": 24.0,
       "estimated_tps": 9.5, "disk_size_gb": 5.79, "best_quant": "mlx-8bit",
       "context_length": 32768, "score": 87.0,
       "score_components": {"fit": 100, "speed": 20, "quality": 99, "context": 100}}


@pytest.mark.asyncio
async def test_fit_for_builds_fitinfo():
    mf = ModelFit(run=lambda rid: dict(RAW))
    fi = (await mf.fit_for(["mlx-community/Q"]))["mlx-community/Q"]
    assert isinstance(fi, FitInfo) and fi.level == "ok"
    assert fi.estimated_tps == 9.5 and fi.best_quant == "mlx-8bit"
    assert fi.score_components["speed"] == 20


@pytest.mark.asyncio
async def test_fit_for_none_when_unknown():
    assert await ModelFit(run=lambda rid: None).fit_for(["x"]) == {"x": None}


@pytest.mark.asyncio
async def test_fit_for_caches():
    calls = {"n": 0}
    def run(rid): calls["n"] += 1; return dict(RAW)
    mf = ModelFit(run=run)
    await mf.fit_for(["a"]); await mf.fit_for(["a"])
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_fit_for_concurrent_two():
    out = await ModelFit(run=lambda rid: dict(RAW)).fit_for(["a", "b"])
    assert set(out) == {"a", "b"} and out["a"].level == "ok"


def test_run_llmfit_absent_returns_none(monkeypatch):
    import ide_server.models.fit as fitmod
    def boom(*a, **k): raise FileNotFoundError("no llmfit")
    monkeypatch.setattr(fitmod.subprocess, "run", boom)
    assert _run_llmfit("x") is None


def test_run_llmfit_non_json_returns_none(monkeypatch):
    import ide_server.models.fit as fitmod
    class _P: stdout = "no soy json"
    monkeypatch.setattr(fitmod.subprocess, "run", lambda *a, **k: _P())
    assert _run_llmfit("x") is None


def test_run_llmfit_parses_models0(monkeypatch):
    import ide_server.models.fit as fitmod, json
    class _P: stdout = json.dumps({"models": [RAW]})
    monkeypatch.setattr(fitmod.subprocess, "run", lambda *a, **k: _P())
    assert _run_llmfit("x")["best_quant"] == "mlx-8bit"


@pytest.mark.asyncio
async def test_fit_for_bad_entry_maps_to_none():
    # raw sin memoria y con context_length no numérico → _to_fit podría fallar → None, no rompe el batch
    bad = {"context_length": "no-numero"}
    mf = ModelFit(run=lambda rid: dict(bad))
    assert await mf.fit_for(["a"]) == {"a": None}


def test_run_llmfit_models_not_list_returns_none(monkeypatch):
    import ide_server.models.fit as fitmod, json
    class _P: stdout = json.dumps({"models": {"not": "a list"}})
    monkeypatch.setattr(fitmod.subprocess, "run", lambda *a, **k: _P())
    assert _run_llmfit("x") is None


@pytest.mark.asyncio
async def test_fit_for_missing_score_component_is_zero():
    raw = {"memory_required_gb": 6.0, "memory_available_gb": 24.0, "estimated_tps": 9.0,
           "disk_size_gb": 5.0, "best_quant": "q", "context_length": 100, "score": 80,
           "score_components": {"fit": 100}}   # faltan speed/quality/context
    fi = (await ModelFit(run=lambda rid: dict(raw)).fit_for(["a"]))["a"]
    assert fi.score_components == {"fit": 100, "speed": 0, "quality": 0, "context": 0}
