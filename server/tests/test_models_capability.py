import pytest
from ide_server.plugins import Registry
import ide_server.capabilities.models as models_cap


class _FakeDownloader:
    def __init__(self): self.started = []
    async def start(self, repo_id): self.started.append(repo_id)
    def active(self): return {"r-en-curso": {"downloaded": 5, "total": 10}}


def _reg(tmp_path, downloader, installed=None, removed=None):
    reg = Registry()
    models_cap.register(reg, tmp_path, manager=None, downloader=downloader,
                        installed=(installed if installed is not None else (lambda: [])),
                        remove=(removed if removed is not None else (lambda r: None)))
    return reg


@pytest.mark.asyncio
async def test_list_curated_installed_active_inuse(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "config.toml").write_text('[mlx]\nmodel = "mlx-community/A"\n')
    from ide_server.models.store import InstalledModel
    reg = _reg(tmp_path, _FakeDownloader(),
               installed=lambda: [InstalledModel("mlx-community/A", 123)])
    out = await reg.dispatch("models.list", {})
    assert out["curated"] and out["curated"][0]["repoId"]
    assert out["installed"] == [{"repoId": "mlx-community/A", "sizeOnDisk": 123}]
    assert out["active"] == {"r-en-curso": {"downloaded": 5, "total": 10}}
    assert out["inUse"] == "mlx-community/A"


@pytest.mark.asyncio
async def test_list_inuse_none_without_config(tmp_path):
    reg = _reg(tmp_path, _FakeDownloader())
    out = await reg.dispatch("models.list", {})
    assert out["inUse"] is None


@pytest.mark.asyncio
async def test_download_calls_start(tmp_path):
    dl = _FakeDownloader()
    reg = _reg(tmp_path, dl)
    assert await reg.dispatch("models.download", {"repoId": "mlx-community/X"}) == {"started": True}
    assert dl.started == ["mlx-community/X"]


@pytest.mark.asyncio
async def test_download_empty_raises(tmp_path):
    reg = _reg(tmp_path, _FakeDownloader())
    with pytest.raises(ValueError):
        await reg.dispatch("models.download", {"repoId": "  "})


@pytest.mark.asyncio
async def test_delete_calls_remove(tmp_path):
    removed = []
    reg = _reg(tmp_path, _FakeDownloader(), removed=lambda r: removed.append(r))
    assert await reg.dispatch("models.delete", {"repoId": "mlx-community/A"}) == {"deleted": True}
    assert removed == ["mlx-community/A"]
