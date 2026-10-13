import pytest
from datetime import datetime
from ide_server.sessions_fs import (
    SessionError, create_session_dir, read_session, list_sessions, session_path,
    update_session_toml, find_main, read_toml,
)

T0 = datetime(2026, 10, 13, 10, 0, 0)
T1 = datetime(2026, 10, 13, 11, 0, 0)


def test_create_ticket_seeds_files(tmp_path):
    p = create_session_dir(tmp_path, sid="fin-1", kind="ticket", permissions="analyze",
                           prompt="hacé X", meta={"title": "Exportar", "notion_url": "https://n"},
                           now=T0)
    assert p == session_path(tmp_path, "fin-1")
    assert read_toml(p / ".session.toml") == {"kind": "ticket", "permissions": "analyze",
                                              "created": "2026-10-13T10:00:00"}
    assert (p / "PROMPT.md").read_text() == "hacé X"
    s = read_session(tmp_path, "fin-1")
    assert s["status"] == "analyzing" and s["title"] == "Exportar"
    assert s["meta"] == {"notion_url": "https://n"} and s["error"] is None


def test_review_seeds_reviewing(tmp_path):
    create_session_dir(tmp_path, sid="pr-a-1", kind="review", permissions="analyze", prompt="")
    assert read_session(tmp_path, "pr-a-1")["status"] == "reviewing"


def test_main_has_no_state_file_and_is_unique(tmp_path):
    p = create_session_dir(tmp_path, sid="s-aaaaa", kind="main", permissions="full", prompt="")
    assert not (p / "TICKET.md").exists()
    assert find_main(tmp_path) == "s-aaaaa"
    with pytest.raises(SessionError) as e:
        create_session_dir(tmp_path, sid="s-bbbbb", kind="main", permissions="full", prompt="")
    assert e.value.code == "main_exists" and "s-aaaaa" in str(e.value)


def test_duplicate_and_invalid(tmp_path):
    create_session_dir(tmp_path, sid="a", kind="ticket", permissions="analyze", prompt="")
    with pytest.raises(SessionError) as e:
        create_session_dir(tmp_path, sid="a", kind="ticket", permissions="analyze", prompt="")
    assert e.value.code == "session_exists"
    for kw, code in [({"kind": "otro"}, "invalid_kind"), ({"permissions": "x"}, "invalid_permissions")]:
        args = {"sid": "b", "kind": "ticket", "permissions": "analyze", "prompt": "", **kw}
        with pytest.raises(SessionError) as e:
            create_session_dir(tmp_path, **args)
        assert e.value.code == code
    assert not session_path(tmp_path, "b").exists()


def test_list_orders_main_first_then_created(tmp_path):
    create_session_dir(tmp_path, sid="t2", kind="ticket", permissions="analyze", prompt="", now=T1)
    create_session_dir(tmp_path, sid="t1", kind="ticket", permissions="analyze", prompt="", now=T0)
    create_session_dir(tmp_path, sid="m", kind="main", permissions="analyze", prompt="", now=T1)
    (session_path(tmp_path, "t1").parent / "templates").mkdir()
    assert [s["id"] for s in list_sessions(tmp_path)] == ["m", "t1", "t2"]


def test_garbage_dirs_surface_with_error(tmp_path):            # Review Focus 3
    create_session_dir(tmp_path, sid="ok", kind="ticket", permissions="analyze", prompt="")
    (session_path(tmp_path, "basura")).mkdir()
    rota = create_session_dir(tmp_path, sid="rota", kind="ticket", permissions="analyze", prompt="")
    (rota / "TICKET.md").write_text("---\nstatus ready\n---\n")
    toml_mal = create_session_dir(tmp_path, sid="tm", kind="ticket", permissions="analyze", prompt="")
    (toml_mal / ".session.toml").write_text("kind = ")
    by_id = {s["id"]: s for s in list_sessions(tmp_path)}
    assert by_id["ok"]["error"] is None
    assert "falta .session.toml" in by_id["basura"]["error"]
    assert "TICKET.md" in by_id["rota"]["error"]
    assert ".session.toml inválido" in by_id["tm"]["error"]


def test_repos_from_symlinks(tmp_path):
    p = create_session_dir(tmp_path, sid="t", kind="ticket", permissions="analyze", prompt="")
    real = tmp_path / "wt"; real.mkdir()
    (p / "repo-a").symlink_to(real)
    (p / "repo-b").symlink_to(tmp_path / "no-existe")
    update_session_toml(tmp_path, "t", lambda d: d.setdefault("ports", {}).update({"repo-a": 8100}))
    repos = read_session(tmp_path, "t")["repos"]
    assert repos == [
        {"name": "repo-a", "state": "ok", "branch": None, "port": 8100, "setup": None},
        {"name": "repo-b", "state": "missing", "branch": None, "port": None, "setup": None},
    ]
