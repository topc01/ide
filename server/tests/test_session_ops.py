import io, json, subprocess
import pytest
from ide_server.session_ops import create_session, delete_session, refresh_review, parse_pr_url
from ide_server.sessions_fs import seed_workspace, session_path, read_session, SessionError
from ide_server.repos_fs import add_repo, worktree_path


def _git(*a, cwd):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


def _ws(tmp_path):
    r = tmp_path / "repo-a"; r.mkdir()
    _git("init", "-q", "-b", "main", cwd=r); _git("commit", "-q", "--allow-empty", "-m", "x", cwd=r)
    seed_workspace(tmp_path)
    return tmp_path


def test_parse_pr_url():
    assert parse_pr_url("https://github.com/acme/repo-a/pull/482") == ("repo-a", 482)
    with pytest.raises(SessionError):
        parse_pr_url("https://gitlab.com/x")


def test_create_ticket_from_template_normalizes_id(tmp_path):        # Review Focus 1
    root = _ws(tmp_path)
    res = create_session(root, {"id": "FIN-123", "template": "ticket",
                                "vars": {"title": "Exportar", "notion_url": "https://n", "body": "b"}})
    s = res["session"]
    assert s["id"] == "fin-123" and s["kind"] == "ticket" and s["title"] == "Exportar"
    assert s["permissions"] == "analyze" and s["meta"]["notion_url"] == "https://n"
    assert "fin-123" in (session_path(root, "fin-123") / "PROMPT.md").read_text()


def test_create_missing_var_creates_nothing(tmp_path):
    root = _ws(tmp_path)
    with pytest.raises(SessionError) as e:
        create_session(root, {"id": "x", "template": "ticket", "vars": {"title": "t"}})
    assert e.value.code == "missing_vars" and not session_path(root, "x").exists()


def test_create_main_random_id_free_prompt(tmp_path):
    root = _ws(tmp_path)
    s = create_session(root, {"main": True, "prompt": "hola", "permissions": "full"})["session"]
    assert s["kind"] == "main" and s["id"].startswith("s-") and s["permissions"] == "full"


def _fake_gh(sha, *, fail=False):
    calls = []

    def runner(argv):
        calls.append(argv)
        if argv[0] == "gh":
            if fail:
                return subprocess.CompletedProcess(argv, 1, "", "HTTP 404")
            return subprocess.CompletedProcess(argv, 0, json.dumps(
                {"title": "Refactor auth", "author": {"login": "juan"}, "headRefOid": sha,
                 "state": "OPEN"}), "")
        if argv[:2] == ["git", "-C"] and "fetch" in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.run(argv, capture_output=True, text=True)
    return runner, calls


def test_create_review(tmp_path):
    root = _ws(tmp_path)
    sha = _git("rev-parse", "HEAD", cwd=root / "repo-a")
    runner, calls = _fake_gh(sha)
    s = create_session(root, {"review": "https://github.com/acme/repo-a/pull/482"},
                       runner=runner)["session"]
    assert s["id"] == "pr-repo-a-482" and s["kind"] == "review" and s["status"] == "reviewing"
    assert s["title"] == "Refactor auth" and s["meta"]["author"] == "@juan"
    assert s["reviewedSha"] == sha and s["repos"][0]["name"] == "repo-a"
    assert any(c[:1] == ["git"] and "pull/482/head" in c for c in calls)


def test_create_review_gh_failure_leaves_nothing(tmp_path):
    root = _ws(tmp_path)
    runner, _ = _fake_gh("x", fail=True)
    with pytest.raises(SessionError) as e:
        create_session(root, {"review": "https://github.com/acme/repo-a/pull/1"}, runner=runner)
    assert e.value.code == "gh_failed" and "404" in str(e.value)
    assert not session_path(root, "pr-repo-a-1").exists()


def test_create_review_unknown_repo(tmp_path):
    root = _ws(tmp_path)
    with pytest.raises(SessionError) as e:
        create_session(root, {"review": "https://github.com/acme/otro/pull/1"})
    assert e.value.code == "unknown_repo"


def test_delete_refuses_dirty_before_touching_anything(tmp_path):    # Review Focus 5
    root = _ws(tmp_path)
    create_session(root, {"id": "t", "prompt": ""})
    for name in ("repo-a",):
        add_repo(root, "t", name, out=io.StringIO())
    (worktree_path(root, "t", "repo-a") / "x").write_text("sucio")
    stopped = []
    with pytest.raises(SessionError) as e:
        delete_session(root, "t", stop=stopped.append)
    assert e.value.code == "uncommitted_changes" and stopped == []
    assert worktree_path(root, "t", "repo-a").exists()
    delete_session(root, "t", force=True, stop=stopped.append)
    assert stopped == ["t"] and not session_path(root, "t").exists()
    assert not worktree_path(root, "t", "repo-a").exists()


def test_refresh_review_moves_head(tmp_path):
    root = _ws(tmp_path)
    sha1 = _git("rev-parse", "HEAD", cwd=root / "repo-a")
    runner, _ = _fake_gh(sha1)
    create_session(root, {"review": "https://github.com/acme/repo-a/pull/9"}, runner=runner)
    _git("commit", "-q", "--allow-empty", "-m", "y", cwd=root / "repo-a")
    sha2 = _git("rev-parse", "HEAD", cwd=root / "repo-a")
    runner2, _ = _fake_gh(sha2)
    s = refresh_review(root, "pr-repo-a-9", runner=runner2)
    assert s["reviewedSha"] == sha2
    assert _git("rev-parse", "HEAD", cwd=worktree_path(root, "pr-repo-a-9", "repo-a")) == sha2


# --- C1: una sesión no escala permisos vía `ide session new` ---------------------------------

def _main(root, perm="analyze"):
    return create_session(root, {"main": True, "prompt": "p", "permissions": perm})["session"]["id"]


def test_caller_ticket_cannot_create_sessions(tmp_path):
    root = _ws(tmp_path)
    create_session(root, {"id": "t1", "prompt": "p"})
    with pytest.raises(SessionError) as e:
        create_session(root, {"id": "x", "prompt": "p", "caller": "t1"})
    assert e.value.code == "forbidden" and not session_path(root, "x").exists()
    with pytest.raises(SessionError) as e:
        create_session(root, {"id": "x", "prompt": "p", "caller": "nope"})
    assert e.value.code == "forbidden"


def test_caller_main_cannot_request_full(tmp_path):
    root = _ws(tmp_path)
    m = _main(root)
    with pytest.raises(SessionError) as e:
        create_session(root, {"id": "x", "prompt": "p", "permissions": "full", "caller": m})
    assert e.value.code == "forbidden" and not session_path(root, "x").exists()
    with pytest.raises(SessionError) as e:
        create_session(root, {"review": "https://github.com/a/repo-a/pull/1",
                              "permissions": "full", "caller": m})
    assert e.value.code == "forbidden"


def test_caller_main_default_full_is_downgraded(tmp_path):
    root = _ws(tmp_path)
    (root / ".ide" / "config.toml").write_text('[sessions]\ndefault_permissions = "full"\n')
    m = _main(root)
    s = create_session(root, {"id": "x", "prompt": "p", "caller": m})["session"]
    assert s["permissions"] == "analyze"


def test_no_caller_can_request_full(tmp_path):
    root = _ws(tmp_path)
    s = create_session(root, {"id": "x", "prompt": "p", "permissions": "full"})["session"]
    assert s["permissions"] == "full"


def test_load_template_rejects_non_plain_names(tmp_path):
    root = _ws(tmp_path)
    for bad in ("../x", "a/b", "..", "."):
        with pytest.raises(SessionError) as e:
            create_session(root, {"id": "x", "template": bad})
        assert e.value.code == "invalid_name"
