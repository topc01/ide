import io, json, subprocess
import pytest
from ide_server.cli_sessions import main, current_session, find_server_url
from ide_server.sessions_fs import seed_workspace, session_path, create_session_dir
from ide_server.repos_fs import worktree_path


def _ws(tmp_path):
    r = tmp_path / "repo-a"; r.mkdir()
    for a in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=r, check=True)
    seed_workspace(tmp_path)
    create_session_dir(tmp_path, sid="t1", kind="ticket", permissions="analyze", prompt="")
    return tmp_path


class FakeHttp:
    def __init__(self, status=200, body=None, fail=False):
        self.calls, self.status, self.body, self.fail = [], status, body or {}, fail

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        if self.fail:
            import httpx
            raise httpx.ConnectError("refused")
        return type("R", (), {"status_code": self.status, "json": lambda s: self.body})()

    get = lambda self, url, timeout=None: self.post(url)


def _run(root, argv, *, env=None, cwd=None, http=None):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, cwd=cwd or root, env=env or {}, home=root / "home", http=http or FakeHttp(),
                out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_current_session_resolution(tmp_path):                     # Review Focus 2
    root = _ws(tmp_path)
    assert current_session(root, env={"IDE_SESSION_ID": "t1"}, cwd=root) == "t1"
    assert current_session(root, env={}, cwd=session_path(root, "t1")) == "t1"
    wt = worktree_path(root, "t1", "repo-a"); wt.mkdir(parents=True)
    assert current_session(root, env={}, cwd=wt / "sub") == "t1"
    with pytest.raises(Exception) as e:
        current_session(root, env={}, cwd=root)
    assert "--session" in str(e.value)


def test_repo_add_from_session_env_and_branch_occupied(tmp_path):
    root = _ws(tmp_path)
    code, out, _ = _run(root, ["repo", "add", "repo-a"], env={"IDE_SESSION_ID": "t1"})
    assert code == 0 and "repo-a" in out and "8100" in out
    create_session_dir(root, sid="t2", kind="ticket", permissions="analyze", prompt="")
    code, _, err = _run(root, ["repo", "add", "repo-a", "--branch", "t1", "--session", "t2"])
    assert code == 1 and "--branch" in err


def test_repo_add_from_inside_worktree_without_env(tmp_path):
    root = _ws(tmp_path)
    _run(root, ["repo", "add", "repo-a", "--session", "t1"])
    code, out, err = _run(root, ["script", "nope"], cwd=worktree_path(root, "t1", "repo-a"))
    assert code == 1                                            # resolvió t1; el script no existe
    assert "--session" not in err                               # no cayó en "no estoy dentro de una sesión"


def test_script_infers_single_repo_and_returns_exit_code(tmp_path):
    root = _ws(tmp_path)
    _run(root, ["repo", "add", "repo-a", "--session", "t1"])
    s = root / ".ide" / "scripts" / "repo-a"; s.mkdir(parents=True, exist_ok=True)
    (s / "test").write_text("#!/bin/sh\necho ok-$IDE_REPO\nexit 4\n"); (s / "test").chmod(0o755)
    code, out, _ = _run(root, ["script", "test"], env={"IDE_SESSION_ID": "t1"})
    assert code == 4 and "ok-repo-a" in out


def test_session_new_needs_server(tmp_path):
    root = _ws(tmp_path)
    code, _, err = _run(root, ["session", "new", "--id", "x"])
    assert code == 1 and "ide run" in err


def test_session_new_posts_payload(tmp_path):
    root = _ws(tmp_path)
    http = FakeHttp(body={"session": {"id": "fin-1", "path": "/p"}, "process": "queued", "log": ""})
    pf = root / "p.md"; pf.write_text("prompt largo")
    code, out, _ = _run(root, ["session", "new", "--id", "FIN-1", "--template", "ticket",
                               "--var", "title=Hola mundo", "--var", "notion_url=u",
                               "--var", "body=b", "--permissions", "full"],
                        env={"IDE_URL": "http://h:1"}, http=http)
    assert code == 0 and out.split()[:2] == ["fin-1", "queued"]
    url, body = http.calls[0]
    assert url == "http://h:1/api/sessions"
    assert body == {"id": "FIN-1", "template": "ticket", "permissions": "full",
                    "vars": {"title": "Hola mundo", "notion_url": "u", "body": "b"}}
    _run(root, ["session", "new", "--main", "--prompt-file", str(pf)],
         env={"IDE_URL": "http://h:1"}, http=http)
    assert http.calls[1][1] == {"main": True, "prompt": "prompt largo"}


def test_session_new_server_error_is_reported(tmp_path):
    root = _ws(tmp_path)
    http = FakeHttp(status=409, body={"code": "session_exists", "message": "ya existe la sesión x"})
    code, _, err = _run(root, ["session", "new", "--id", "x"], env={"IDE_URL": "http://h:1"}, http=http)
    assert code == 1 and "ya existe" in err


def test_session_ls_json_without_server(tmp_path):
    root = _ws(tmp_path)
    code, out, _ = _run(root, ["session", "ls", "--json"], http=FakeHttp(fail=True))
    data = json.loads(out)
    assert code == 0 and data[0]["id"] == "t1" and data[0]["process"] == "?"


def test_session_rm(tmp_path):
    root = _ws(tmp_path)
    code, _, _ = _run(root, ["session", "rm", "t1"], http=FakeHttp(fail=True))
    assert code == 0 and not session_path(root, "t1").exists()


def test_session_rm_refuses_dirty_before_stopping(tmp_path):
    root = _ws(tmp_path)
    _run(root, ["repo", "add", "repo-a", "--session", "t1"])
    (worktree_path(root, "t1", "repo-a") / "sucio.txt").write_text("x")
    http = FakeHttp()
    code, _, err = _run(root, ["session", "rm", "t1"], env={"IDE_URL": "http://h:1"}, http=http)
    assert code == 1 and "cambios sin commitear" in err
    assert http.calls == []                                     # no mató el proceso
    assert session_path(root, "t1").exists()


def test_session_rm_stops_then_deletes(tmp_path):
    root = _ws(tmp_path)
    http = FakeHttp(body={})
    code, _, _ = _run(root, ["session", "rm", "t1"], env={"IDE_URL": "http://h:1"}, http=http)
    assert code == 0 and http.calls == [("http://h:1/api/sessions/t1/stop", {})]
    assert not session_path(root, "t1").exists()


def test_bad_input_is_reported_without_traceback(tmp_path):
    root = _ws(tmp_path)
    code, _, err = _run(root, ["session", "new", "--var", "foo"], env={"IDE_URL": "http://h:1"})
    assert code == 1 and "k=v" in err
    code, _, err = _run(root, ["session", "new", "--prompt-file", str(root / "no.md")],
                        env={"IDE_URL": "http://h:1"})
    assert code == 1 and "--prompt-file" in err


def test_non_json_server_response_is_reported(tmp_path):
    root = _ws(tmp_path)

    class BadJson(FakeHttp):
        def post(self, url, json=None, timeout=None):
            self.calls.append((url, json))
            def boom():
                raise ValueError("no json")
            return type("R", (), {"status_code": 502, "json": staticmethod(boom)})()

    code, _, err = _run(root, ["session", "new", "--id", "x"], env={"IDE_URL": "http://h:1"},
                        http=BadJson())
    assert code == 1 and "respuesta inválida" in err and "502" in err


def test_session_ls_warns_when_server_fails(tmp_path):
    root = _ws(tmp_path)
    code, out, err = _run(root, ["session", "ls", "--json"], env={"IDE_URL": "http://h:1"},
                          http=FakeHttp(fail=True))
    assert code == 0 and json.loads(out)[0]["process"] == "?"
    assert "aviso: no se pudo consultar el server" in err


def test_find_server_url_from_instances(tmp_path, monkeypatch):
    root = _ws(tmp_path)
    from ide_server import cli_sessions
    monkeypatch.setattr(cli_sessions.instances, "list_instances",
                        lambda home: [{"workspace": "/otro", "url": "http://a"},
                                      {"workspace": str(root), "url": "http://b"}])
    assert find_server_url(root, {}, root) == "http://b"
    assert find_server_url(root, {"IDE_URL": "http://c"}, root) == "http://c"
