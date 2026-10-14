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
                           prompt="haz X", meta={"title": "Exportar", "notion_url": "https://n"},
                           now=T0)
    assert p == session_path(tmp_path, "fin-1")
    assert read_toml(p / ".session.toml") == {"kind": "ticket", "permissions": "analyze",
                                              "created": "2026-10-13T10:00:00"}
    assert (p / "PROMPT.md").read_text() == "haz X"
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


def test_unreadable_session_toml_surfaces_with_error(tmp_path):
    create_session_dir(tmp_path, sid="ok", kind="ticket", permissions="analyze", prompt="")
    bin_ = create_session_dir(tmp_path, sid="bin", kind="ticket", permissions="analyze", prompt="")
    (bin_ / ".session.toml").write_bytes(b"\xff\xfe\x00\x81")
    dir_ = create_session_dir(tmp_path, sid="dir", kind="ticket", permissions="analyze", prompt="")
    (dir_ / ".session.toml").unlink()
    (dir_ / ".session.toml").mkdir()
    by_id = {s["id"]: s for s in list_sessions(tmp_path)}
    assert set(by_id) == {"ok", "bin", "dir"}
    assert by_id["ok"]["error"] is None
    assert by_id["bin"]["error"] and "ilegible" in by_id["bin"]["error"]
    assert by_id["dir"]["error"] and "ilegible" in by_id["dir"]["error"]


def test_non_utf8_ticket_md_surfaces_with_error(tmp_path):
    create_session_dir(tmp_path, sid="ok", kind="ticket", permissions="analyze", prompt="")
    t = create_session_dir(tmp_path, sid="tb", kind="ticket", permissions="analyze", prompt="")
    (t / "TICKET.md").write_bytes(b"---\nstatus: \xff\xfe\n---\n")
    by_id = {s["id"]: s for s in list_sessions(tmp_path)}
    assert set(by_id) == {"ok", "tb"}
    assert by_id["ok"]["error"] is None
    assert by_id["tb"]["error"] and "TICKET.md" in by_id["tb"]["error"]


def test_malformed_ports_and_setup_do_not_break_listing(tmp_path):
    p = create_session_dir(tmp_path, sid="t", kind="ticket", permissions="analyze", prompt="")
    real = tmp_path / "wt"; real.mkdir()
    (p / "repo-a").symlink_to(real)
    (p / ".session.toml").write_text('kind = "ticket"\npermissions = "analyze"\nports = 5\nsetup = "x"\n')
    s = {x["id"]: x for x in list_sessions(tmp_path)}["t"]
    assert s["error"] is None
    assert s["repos"] == [{"name": "repo-a", "state": "ok", "branch": None, "port": None, "setup": None}]


def test_main_creation_survives_unreadable_other_session(tmp_path):
    bad = create_session_dir(tmp_path, sid="bad", kind="ticket", permissions="analyze", prompt="")
    (bad / ".session.toml").write_bytes(b"\xff\xfe\x00")
    p = create_session_dir(tmp_path, sid="m", kind="main", permissions="full", prompt="")
    assert p.is_dir()


def test_meta_cannot_override_seeded_status(tmp_path):
    p = create_session_dir(tmp_path, sid="fin-9", kind="ticket", permissions="analyze", prompt="",
                           meta={"status": "done", "title": "T"})
    assert read_session(tmp_path, "fin-9")["status"] == "analyzing"
    assert (p / "TICKET.md").read_text().startswith("---\nstatus: analyzing\n")


@pytest.mark.parametrize("kind", ['["ticket"]', '{ a = 1 }', '3'])
def test_non_string_kind_surfaces_as_error(tmp_path, kind):
    p = create_session_dir(tmp_path, sid="t", kind="ticket", permissions="analyze", prompt="")
    (p / ".session.toml").write_text(f'kind = {kind}\npermissions = "analyze"\n')
    s = list_sessions(tmp_path)[0]
    assert s["kind"] is None and "kind inválido" in s["error"]


def test_workspace_lock_is_reentrant(tmp_path):
    from ide_server.sessions_fs import workspace_lock
    with workspace_lock(tmp_path):
        with workspace_lock(tmp_path):
            update_session_toml  # noqa: B018 — sólo verificamos que no se cuelga
    assert (tmp_path / ".ide" / ".lock").exists()
