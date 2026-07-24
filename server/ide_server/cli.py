from __future__ import annotations
import argparse
import os
import shutil
import socket
import subprocess
import webbrowser
from pathlib import Path
from ide_server import instances
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


def _ensure_root(cwd: Path) -> Path:
    root = resolve_root(cwd)
    if root is None:
        init_workspace(cwd)
        print(f"Workspace .ide/ creado en {cwd}")
        return cwd
    return root


def _launch(root: Path, host: str, port: int, web_dir, *, open_browser: bool, serve, opener) -> None:
    from ide_server.app import create_app
    url = f"http://{host}:{port}"
    inst_path = instances.register_instance(Path.home(), port=port, host=host,
                                            workspace=str(root), pid=os.getpid())
    if open_browser:
        opener(url)
    print(f"Workspace: {root}  →  {url}")
    try:
        serve(create_app(root, web_dir), host, port)
    finally:
        instances.unregister_instance(inst_path)


HELP_TEXT = """\
ide — Agentic IDE (orquestador de sesiones paralelas de Claude Code)

Un IDE que corre en el navegador (localhost) para manejar múltiples sesiones de Claude Code
sobre varios repos y git worktrees. Backend FastAPI + frontend React, servidos juntos por `ide`.
Usa tu login de Claude Code (suscripción), sin ANTHROPIC_API_KEY.

COMANDOS
  ide run [--cwd DIR] [--port N] [--no-browser]
        Levanta todo (frontend + backend + API + WebSocket) en un puerto y abre el navegador.
        Elige :8787; si está ocupado sube al siguiente libre (así podés correr varios `ide` a la
        vez). --port fuerza uno exacto. Si el workspace no tiene .ide/, lo crea automáticamente.
  ide server [--dev] [--cwd DIR] [--port N]
        Solo el backend, headless (no abre navegador). Con --dev fija el puerto :8787 (donde pega
        el frontend dev). Sin --dev usa un puerto libre. Para el flujo de desarrollo con `ide ui --dev`.
  ide ui [--dev]
        Levanta el frontend en modo dev (Vite, hot-reload, http://localhost:5173). Correr desde el
        checkout del repo. Se usa junto con `ide server --dev`.
  ide build
        Buildea el frontend (Vite) y lo empaqueta en el paquete. Correr desde el checkout del repo.
  ide ls
        Lista las instancias de `ide` corriendo (url, workspace, pid). Poda las muertas.
  ide init [--cwd DIR]
        Inicializa un workspace (.ide/) sin levantar el server. Normalmente no hace falta:
        `ide run` ya auto-inicializa.
  ide help
        Esta ayuda.

INSTALAR (global, un comando levanta todo)
  cd server && uv run ide build      # empaqueta el frontend
  uv tool install ./server           # deja `ide` en el PATH
  ide run --cwd /ruta/al/workspace   # http://127.0.0.1:8787 (o el siguiente libre)

DESARROLLO (hot-reload de la UI, dos procesos)
  ide server --dev --cwd <ws>        # backend en :8787 (headless)
  ide ui --dev                       # Vite en :5173 (el WS del front pega a :8787)

EL WORKSPACE (.ide/)
  Un directorio con .ide/ es la unidad de trabajo. Contiene: config.toml, sessions.json,
  tasks/ (tareas markdown), worktrees/ (worktrees de las sesiones), notion.json.
  .ide/ es local y no se commitea. Global del usuario (en ~/.ide/): config.toml y
  instances/<port>.json (instancias corriendo, compartidas entre workspaces).

CÓMO UN AGENTE HACE HANDOFF A ESTE IDE (resumen)
  Una sesión COORDINADORA (sin worktree) comanda sesiones HIJAS (worktree + branch + rol) vía
  herramientas MCP `orq` expuestas a su Claude Code: list_children, ask_session(id, tarea)
  [request-reply bloqueante], ask_sessions({requests:[...]}) [fan-out paralelo],
  spawn_session(repo, nombre).
  Las hijas corren permisivas; los mensajes se ven como chat en ambas sesiones. Las tareas viven
  como markdown en .ide/tasks/ (capability tasks.list/read/save/create).

  Guía completa para agentes: docs/ide-handoff.md
"""


def main(argv: list[str] | None = None, *, serve=None, opener=None, build_runner=None) -> int:
    serve = serve or _serve
    opener = opener or webbrowser.open
    build_runner = build_runner or subprocess.run

    parser = argparse.ArgumentParser(prog="ide")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "server", "ui", "init", "build", "ls", "help"])
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    cwd = Path(args.cwd).resolve()

    if args.command == "help":
        print(HELP_TEXT)
        return 0

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

    if args.command == "ui":
        ui = repo_ui()
        if ui is None:
            print("ide ui solo corre desde el checkout del repo (no se encontró ui/).")
            return 1
        build_runner(["npm", "run", "dev"], cwd=str(ui), check=True)   # Vite dev server (:5173)
        return 0

    if args.command == "ls":
        insts = instances.list_instances(Path.home())
        if not insts:
            print("no hay instancias corriendo")
            return 0
        for i in insts:
            print(f"  {i['url']}  {i['workspace']}  (pid {i['pid']})")
        return 0

    # command == "run" o "server" (ambos levantan el backend)
    from ide_server.config import Settings
    root = _ensure_root(cwd)
    settings = Settings()
    web_dir = resolve_web_dir()
    host = settings.host

    if args.command == "server":
        # backend headless (sin abrir navegador). --dev fija :8787, donde pega el frontend dev.
        if args.dev:
            port = settings.port
            print("dev: levantá la UI aparte con `ide ui --dev` (Vite en http://localhost:5173)")
        else:
            port = args.port if args.port is not None else find_free_port(host, settings.port)
        _launch(root, host, port, web_dir, open_browser=False, serve=serve, opener=opener)
        return 0

    # command == "run"
    if web_dir is None:
        print("frontend no buildeado; corré `ide build` (o `npm run build` en ui/).")
    port = args.port if args.port is not None else find_free_port(host, settings.port)
    _launch(root, host, port, web_dir, open_browser=not args.no_browser, serve=serve, opener=opener)
    return 0
