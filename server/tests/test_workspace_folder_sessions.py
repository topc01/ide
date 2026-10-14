import pytest
from ide_server.workspace import resolve_cwd, resolve_repo


def _ws(tmp_path, repos=("a",)):
    sess = tmp_path / ".ide" / "sessions" / "s1"
    sess.mkdir(parents=True)
    (sess / ".session.toml").write_text('kind = "ticket"\n')
    for r in repos:
        (tmp_path / r).mkdir()
        (sess / r).symlink_to(tmp_path / r)
    return sess


def test_cwd_repo_resolves_worktree(tmp_path):
    _ws(tmp_path)
    assert resolve_cwd(tmp_path, {"sessionId": "s1", "repoId": "a"}) == (tmp_path / "a").resolve()


def test_cwd_without_repo_is_session_folder(tmp_path):
    sess = _ws(tmp_path)
    assert resolve_cwd(tmp_path, {"sessionId": "s1"}) == sess


def test_cwd_unlinked_or_missing_or_escaping_repo_raises(tmp_path):
    sess = _ws(tmp_path)
    (tmp_path / "b").mkdir()
    (sess / "gone").symlink_to(tmp_path / "nope")  # worktree faltante
    for rid in ("b", "gone", "../../.."):
        with pytest.raises(KeyError):
            resolve_cwd(tmp_path, {"sessionId": "s1", "repoId": rid})


def test_bad_session_id_is_not_folder_session(tmp_path):
    _ws(tmp_path)
    with pytest.raises(KeyError):  # cae al camino viejo/KeyError, no escapa
        resolve_repo(tmp_path, {"sessionId": "../sessions/s1"})


def test_repo_single_without_repoid(tmp_path):
    _ws(tmp_path)
    assert resolve_repo(tmp_path, {"sessionId": "s1"}) == tmp_path / "a"


def test_repo_zero_or_many_without_repoid_raises(tmp_path):
    _ws(tmp_path, repos=())
    with pytest.raises(KeyError):
        resolve_repo(tmp_path, {"sessionId": "s1"})
    (tmp_path / "x").mkdir(); (tmp_path / "y").mkdir()
    sess = tmp_path / ".ide" / "sessions" / "s1"
    (sess / "x").symlink_to(tmp_path / "x"); (sess / "y").symlink_to(tmp_path / "y")
    with pytest.raises(KeyError):
        resolve_repo(tmp_path, {"sessionId": "s1"})


def test_repo_unlinked_repoid_raises(tmp_path):
    _ws(tmp_path)
    with pytest.raises(KeyError):
        resolve_repo(tmp_path, {"sessionId": "s1", "repoId": "zzz"})
