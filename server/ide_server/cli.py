from __future__ import annotations
import argparse
import webbrowser
from pathlib import Path
from ide_server.workspace import find_workspace_root


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ide")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "init"])
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    cwd = Path(args.cwd).resolve()

    if args.command == "init":
        ide = init_workspace(cwd)
        print(f"Workspace inicializado en {ide}")
        return 0

    root = resolve_root(cwd)
    if root is None:
        print("No se encontró un workspace (.ide/). Corré `ide init` en la raíz del workspace.")
        return 1

    from ide_server.app import create_app
    from ide_server.config import Settings
    import uvicorn

    settings = Settings()
    if not args.no_browser:
        webbrowser.open(f"http://localhost:5173")
    print(f"Workspace: {root}  →  backend en http://{settings.host}:{settings.port}")
    uvicorn.run(create_app(root), host=settings.host, port=settings.port)
    return 0
