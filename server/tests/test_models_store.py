from ide_server.models.store import installed_models, delete_model, InstalledModel


class _Rev:
    def __init__(self, h): self.commit_hash = h


class _Repo:
    def __init__(self, repo_id, size, revs=(), repo_type="model"):
        self.repo_id = repo_id; self.size_on_disk = size
        self.repo_type = repo_type; self.revisions = [_Rev(r) for r in revs]


class _Info:
    def __init__(self, repos): self.repos = repos; self.deleted = None
    def delete_revisions(self, *hashes): self.deleted = hashes; return self
    def execute(self): return None


def test_installed_maps_and_filters_datasets():
    info = _Info([_Repo("mlx-community/A", 100),
                  _Repo("data/x", 5, repo_type="dataset")])
    assert installed_models(scan=lambda: info) == [InstalledModel("mlx-community/A", 100)]


def test_installed_empty_on_scan_error():
    def boom(): raise RuntimeError("no cache")
    assert installed_models(scan=boom) == []


def test_delete_calls_delete_revisions_for_repo():
    info = _Info([_Repo("mlx-community/A", 100, revs=["h1", "h2"])])
    delete_model("mlx-community/A", scan=lambda: info)
    assert set(info.deleted) == {"h1", "h2"}


def test_delete_absent_is_noop():
    info = _Info([_Repo("mlx-community/A", 100, revs=["h1"])])
    delete_model("mlx-community/Z", scan=lambda: info)
    assert info.deleted is None
