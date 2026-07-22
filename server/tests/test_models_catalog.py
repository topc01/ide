from ide_server.models.catalog import CURATED_MODELS, CuratedModel


def test_curated_non_empty_and_shaped():
    assert len(CURATED_MODELS) >= 3
    for m in CURATED_MODELS:
        assert isinstance(m, CuratedModel)
        assert m.repo_id and m.label and m.params and m.quant
        assert m.size_gb > 0
    # sin repos duplicados
    assert len({m.repo_id for m in CURATED_MODELS}) == len(CURATED_MODELS)
