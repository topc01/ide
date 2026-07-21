from __future__ import annotations
import argparse
import shutil
import socket
import subprocess
import webbrowser
from pathlib import Path
from ide_server.workspace import find_workspace_root

PKG_WEB = Path(__file__).parent / "web"


def init_workspace(cwd: Path) -> Path:
    ide = cwd / ".ide"
    (ide / "worktrees").mkdir(parents=True, exist_ok=True)
    (ide / "tasks").mkdir(exist_ok=True)
    cfg = ide / "config.toml"
    if not cfg.exists():
        cfg.write_text(f'name = "{cwd.name}"\n')
    return ide


def resolve_root(cwd: Path) -> Path | None:
    return find_workspace_root(cwd)


def repo_ui_dist() -> Path:
    return Path(__file__).parent.parent.parent / "ui" / "dist"


def repo_ui() -> Path | None:
    ui = Path(__file__).parent.parent.parent / "ui"
    return ui if (ui / "package.json").is_file() else None


def resolve_web_dir(pkg_web: Path = PKG_WEB, repo_dist: Path | None = None) -> Path | None:
    if (pkg_web / "index.html").is_file():
        return pkg_web
    repo_dist = repo_dist if repo_dist is not None else repo_ui_dist()
    if (repo_dist / "index.html").is_file():
        return repo_dist
    return None


def find_free_port(host: str, start: int, limit: int = 100) -> int:
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no hay puerto libre en [{start}, {start + limit})")


def build_frontend(ui_dir: Path, web_dir: Path, runner=subprocess.run) -> int:
    runner(["npm", "run", "build"], cwd=str(ui_dir), check=True)
    shutil.rmtree(web_dir, ignore_errors=True)
    shutil.copytree(ui_dir / "dist", web_dir)
    return 0


def _serve(app, host: str, port: int) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port)


def main(argv: list[str] | None = None, *, serve=None, opener=None, build_runner=None) -> int:
    serve = serve or _serve
    opener = opener or webbrowser.open
    build_runner = build_runner or subprocess.run

    parser = argparse.ArgumentParser(prog="ide")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "init", "build"])
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    cwd = Path(args.cwd).resolve()

    if args.command == "init":
        print(f"Workspace inicializado en {init_workspace(cwd)}")
        return 0

    if args.command == "build":
        ui = repo_ui()
        if ui is None:
            print("ide build solo corre desde el checkout del repo (no se encontró ui/).")
            return 1
        build_frontend(ui, PKG_WEB, build_runner)
        print(f"Frontend buildeado en {PKG_WEB}")
        return 0

    # command == "run"
    root = resolve_root(cwd)
    if root is None:
        init_workspace(cwd)
        print(f"Workspace .ide/ creado en {cwd}")
        root = cwd

    from ide_server.app import create_app
    from ide_server.config import Settings
    settings = Settings()

    web_dir = resolve_web_dir()
    if web_dir is None:
        print("frontend no buildeado; corré `ide build` (o `npm run build` en ui/).")

    host = settings.host
    port = args.port if args.port is not None else find_free_port(host, settings.port)
    url = f"http://{host}:{port}"
    if not args.no_browser:
        opener(url)
    print(f"Workspace: {root}  →  {url}")
    serve(create_app(root, web_dir), host, port)
    return 0
