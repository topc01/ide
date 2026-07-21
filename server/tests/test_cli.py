from pathlib import Path
from ide_server.cli import init_workspace, resolve_root, main

def test_init_creates_ide(tmp_path):
    ide = init_workspace(tmp_path)
    assert ide == tmp_path / ".ide"
    assert (ide / "config.toml").is_file()

def test_resolve_root_after_init(tmp_path):
    init_workspace(tmp_path)
    assert resolve_root(tmp_path) == tmp_path


def test_resolve_web_dir_prefers_bundle(tmp_path):
    from ide_server.cli import resolve_web_dir
    bundle = tmp_path / "web"; bundle.mkdir(); (bundle / "index.html").write_text("x")
    dist = tmp_path / "dist"; dist.mkdir(); (dist / "index.html").write_text("y")
    assert resolve_web_dir(pkg_web=bundle, repo_dist=dist) == bundle


def test_resolve_web_dir_falls_back_to_repo_dist(tmp_path):
    from ide_server.cli import resolve_web_dir
    dist = tmp_path / "dist"; dist.mkdir(); (dist / "index.html").write_text("y")
    assert resolve_web_dir(pkg_web=tmp_path / "nope", repo_dist=dist) == dist


def test_resolve_web_dir_none(tmp_path):
    from ide_server.cli import resolve_web_dir
    assert resolve_web_dir(pkg_web=tmp_path / "a", repo_dist=tmp_path / "b") is None


def test_run_auto_inits_and_serves(tmp_path):
    calls = {}
    code = main(["run", "--cwd", str(tmp_path)],
                serve=lambda app, host, port: calls.setdefault("served", (host, port)),
                opener=lambda u: calls.setdefault("opened", u))
    assert code == 0
    assert (tmp_path / ".ide").is_dir()                     # auto-init
    assert "served" in calls
    # Puerto dinámico: verificar que el URL abierto contiene el puerto servido
    host, port = calls["served"]
    assert calls["opened"] == f"http://{host}:{port}"


def test_run_no_browser(tmp_path):
    init_workspace(tmp_path)
    opened = []
    main(["run", "--cwd", str(tmp_path), "--no-browser"],
         serve=lambda a, h, p: None, opener=lambda u: opened.append(u))
    assert opened == []


def test_build_frontend_copies_dist_to_web(tmp_path):
    from ide_server.cli import build_frontend
    ui = tmp_path / "ui"; ui.mkdir()
    web = tmp_path / "pkgweb"
    seen = {}

    def fake_runner(cmd, cwd=None, check=False, **kw):
        seen["cmd"] = cmd; seen["cwd"] = cwd; seen["check"] = check
        d = ui / "dist"; d.mkdir(); (d / "index.html").write_text("built")

    rc = build_frontend(ui, web, runner=fake_runner)
    assert rc == 0
    assert (web / "index.html").read_text() == "built"
    assert seen["cmd"] == ["npm", "run", "build"]
    assert Path(seen["cwd"]) == ui and seen["check"] is True


def test_build_frontend_replaces_existing_web(tmp_path):
    from ide_server.cli import build_frontend
    ui = tmp_path / "ui"; ui.mkdir()
    web = tmp_path / "pkgweb"; web.mkdir(); (web / "stale.txt").write_text("old")

    def fake_runner(cmd, cwd=None, check=False, **kw):
        d = ui / "dist"; d.mkdir(); (d / "index.html").write_text("new")

    build_frontend(ui, web, runner=fake_runner)
    assert not (web / "stale.txt").exists()     # reemplazado, no mergeado
    assert (web / "index.html").read_text() == "new"


def test_main_build_outside_repo(capsys, monkeypatch):
    import ide_server.cli as cli
    monkeypatch.setattr(cli, "repo_ui", lambda: None)
    assert cli.main(["build"]) == 1
    assert "checkout" in capsys.readouterr().out


def test_main_build_invokes_build_frontend(tmp_path, monkeypatch):
    import ide_server.cli as cli
    ui = tmp_path / "ui"; ui.mkdir()
    monkeypatch.setattr(cli, "repo_ui", lambda: ui)
    monkeypatch.setattr(cli, "PKG_WEB", tmp_path / "web")   # no tocar el PKG_WEB real
    ran = {}

    def fake_runner(cmd, cwd=None, check=False, **kw):
        ran["yes"] = True
        d = ui / "dist"; d.mkdir(); (d / "index.html").write_text("x")

    assert cli.main(["build"], build_runner=fake_runner) == 0
    assert ran.get("yes") and (tmp_path / "web" / "index.html").is_file()


def test_find_free_port_returns_start_when_free():
    import socket
    from ide_server.cli import find_free_port
    s = socket.socket(); s.bind(("127.0.0.1", 0)); free = s.getsockname()[1]; s.close()
    assert find_free_port("127.0.0.1", free) == free


def test_find_free_port_bumps_when_busy():
    import socket
    from ide_server.cli import find_free_port
    s = socket.socket(); s.bind(("127.0.0.1", 0)); busy = s.getsockname()[1]; s.listen()
    try:
        got = find_free_port("127.0.0.1", busy)
        assert got != busy
        s2 = socket.socket(); s2.bind(("127.0.0.1", got)); s2.close()   # got es bindeable
    finally:
        s.close()


def test_run_opens_chosen_port(tmp_path):
    init_workspace(tmp_path)
    calls = {}
    main(["run", "--cwd", str(tmp_path), "--port", "8899"],
         serve=lambda app, host, port: calls.setdefault("served", port),
         opener=lambda u: calls.setdefault("opened", u))
    assert calls["served"] == 8899
    assert calls["opened"] == "http://127.0.0.1:8899"
