from __future__ import annotations
import argparse
import os
import shutil
import socket
import subprocess
import sys
import webbrowser
from ide_server.updater import RESTART_CODE, SUPERVISED_ENV
from pathlib import Path
from ide_server import instances
from ide_server.workspace import find_workspace_root

PKG_WEB = Path(__file__).parent / "web"


def init_workspace(cwd: Path) -> Path:
    from ide_server import seeds
    from ide_server.sessions_fs import seed_workspace
    ide = cwd / ".ide"
    ide.mkdir(parents=True, exist_ok=True)
    cfg = ide / "config.toml"
    if not cfg.exists():
        cfg.write_text(seeds.CONFIG_TOML.format(name=cwd.name))
    seed_workspace(cwd)
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


def _launch(root: Path, host: str, port: int, web_dir, *, open_browser: bool, serve, opener) -> int:
    from ide_server.app import create_app
    url = f"http://{host}:{port}"
    inst_path = instances.register_instance(Path.home(), port=port, host=host,
                                            workspace=str(root), pid=os.getpid())
    if open_browser:
        opener(url)
    print(f"Workspace: {root}  →  {url}")
    app = create_app(root, web_dir, server_url=url)
    try:
        serve(app, host, port)
    finally:
        instances.unregister_instance(inst_path)
    # pidió reiniciarse (versión nueva instalada): el supervisor lo relanza
    return RESTART_CODE if getattr(app.state, "updater", None) and app.state.updater.restart_requested else 0


def _supervise(root: Path, port: int, *, open_browser: bool, opener) -> int:
    """`ide run`: corre el server como hijo y lo relanza si pide reiniciarse (versión nueva) o se
    cae. Las conversaciones de `claude` siguen vivas en su daemon y la UI se reconecta sola."""
    import time
    if open_browser:
        opener(f"http://127.0.0.1:{port}")
    env = {**os.environ, SUPERVISED_ENV: "1"}
    argv = [sys.executable, "-m", "ide_server.cli", "run", "--cwd", str(root), "--port", str(port),
            "--no-browser"]
    crashes: list[float] = []
    while True:
        child = subprocess.Popen(argv, env=env)
        try:
            code = child.wait()
        except KeyboardInterrupt:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
            return 0
        if code == RESTART_CODE:
            print("ide: versión nueva instalada, relanzando el server…", flush=True)
            continue
        if code == 0:
            return 0
        now = time.time()
        crashes = [t for t in crashes if now - t < 300] + [now]
        if len(crashes) > 5:
            print(f"ide: el server se cayó {len(crashes)} veces en 5 min (código {code}); me detengo")
            return code
        print(f"ide: el server se cayó (código {code}); relanzando en {2 ** len(crashes)} s…", flush=True)
        time.sleep(2 ** len(crashes))


HELP_TEXT = """\
ide — Agentic IDE (orquestador de sesiones paralelas de Claude Code)

Un IDE que corre en el navegador (localhost) para manejar múltiples sesiones de Claude Code
sobre varios repos y git worktrees. Backend FastAPI + frontend React, servidos juntos por `ide`.
Usa tu login de Claude Code (suscripción), sin ANTHROPIC_API_KEY.

COMANDOS
  ide run [--cwd DIR] [--port N] [--no-browser]
        Levanta todo (frontend + backend + API + WebSocket) en un puerto y abre el navegador.
        Elige :8787; si está ocupado sube al siguiente libre (así puedes correr varios `ide` a la
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
  ide docs
        Referencia completa (layout de .ide/, config.toml, permisos, plantillas, scripts, CLI,
        estados, errores). Pensada para que un agente pueda configurar el IDE.
  ide session new [--id X] [--main] [--template t --var k=v …] [--prompt "…" | --prompt-file f]
                  [--permissions analyze|full|default] [--review <pr-url>]
                  [--notion <url>] [--vars-file f.json|-] [--if-missing] [--dry-run]
        Crea una sesión-carpeta (.ide/sessions/<id>/) y lanza `claude` en ella (requiere `ide run`).
        --notion deriva el id del page id (n-<8 hex>) y deja el link del ticket en sus Adjuntos;
        --if-missing no falla si ya existe;
        --dry-run valida y muestra el prompt sin crear nada; --vars-file lee variables en JSON.
  ide session ls [--json] | open <id> | stop <id> | rm <id> [--force]
  ide repo add <repo> [--branch b] | ide repo rm <repo> [--force]
        Agrega/quita un repo (worktree) a la sesión actual; corre su script `setup`/`archive`.
  ide script <nombre> [<repo>]
        Corre .ide/scripts/<repo>/<nombre> en el worktree con env IDE_* (IDE_PORT, …).

INSTALAR (global, un comando levanta todo)
  cd server && uv run ide build      # empaqueta el frontend
  uv tool install ./server           # deja `ide` en el PATH
  ide run --cwd /ruta/al/workspace   # http://127.0.0.1:8787 (o el siguiente libre)

DESARROLLO (hot-reload de la UI, dos procesos)
  ide server --dev --cwd <ws>        # backend en :8787 (headless)
  ide ui --dev                       # Vite en :5173 (el WS del front pega a :8787)

EL WORKSPACE (.ide/)
  Contiene: config.toml, sessions/ (una carpeta por sesión + CLAUDE.md + templates/), worktrees/,
  scripts/<repo>/, permissions/. .ide/ es local y no se commitea.

CÓMO UN AGENTE HACE HANDOFF A ESTE IDE (resumen)
  Las sesiones son `claude` interactivos en .ide/sessions/<id>/. Se comunican con el IDE vía este
  CLI (ver .ide/sessions/CLAUDE.md). Estado en SESSION.md (frontmatter status).
"""


def main(argv: list[str] | None = None, *, serve=None, opener=None, build_runner=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] in ("session", "repo", "script", "status", "dev", "handoff", "feedback", "reply", "telegram", "later", "tools", "review", "evidence", "evidencias", "hook", "dep", "server", "push", "update", "merge", "merges", "migrate-ids", "migrations", "notion", "ticket", "artifact", "instagram", "db", "browser", "procs"):
        from ide_server.cli_sessions import main as sessions_main
        return sessions_main(raw, cwd=Path.cwd(), env=dict(os.environ), home=Path.home())

    serve = serve or _serve
    opener = opener or webbrowser.open
    build_runner = build_runner or subprocess.run

    parser = argparse.ArgumentParser(prog="ide")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "server", "ui", "init", "build", "ls", "help", "docs"])
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-supervise", action="store_true",
                        help="sin supervisor: no se relanza solo al instalar una versión nueva")
    args = parser.parse_args(argv)
    cwd = Path(args.cwd).resolve()

    if args.command == "help":
        print(HELP_TEXT)
        return 0

    if args.command == "docs":
        print((Path(__file__).parent / "REFERENCE.md").read_text(encoding="utf-8"))
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
            print("dev: levanta la UI aparte con `ide ui --dev` (Vite en http://localhost:5173)")
        else:
            port = args.port if args.port is not None else find_free_port(host, settings.port)
        return _launch(root, host, port, web_dir, open_browser=False, serve=serve, opener=opener)

    # command == "run"
    if web_dir is None:
        print("frontend no buildeado; ejecuta `ide build` (o `npm run build` en ui/).")
    port = args.port if args.port is not None else find_free_port(host, settings.port)
    if os.environ.get(SUPERVISED_ENV) == "1" or args.no_supervise:
        return _launch(root, host, port, web_dir, open_browser=not args.no_browser, serve=serve,
                       opener=opener)
    return _supervise(root, port, open_browser=not args.no_browser, opener=opener)


if __name__ == "__main__":
    sys.exit(main())
