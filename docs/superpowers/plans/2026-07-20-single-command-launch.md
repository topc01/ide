# Arranque con un solo comando `ide` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps
> usan checkbox (`- [ ]`).

**Goal:** `ide run` sirve frontend + backend + API + WS en un puerto con auto-init de `.ide/`;
`ide build` empaqueta el frontend; `ide` instalable global (patrón Jupyter).

**Architecture:** FastAPI monta el `ui/dist` buildeado con `StaticFiles`; el CLI resuelve el web
dir (bundle `ide_server/web/` > `ui/dist` del repo > None) y auto-inicia el workspace; hatchling
empaqueta `ide_server/web/` en el wheel.

**Tech Stack:** Python/FastAPI/hatchling. Tests: `cd server && uv run pytest`.

## Global Constraints

- **Sin fallos silenciosos:** `ide run` sin frontend buildeado → warning + arranca (no crashea);
  `npm run build` que falla → propaga (`check=True`); `ide build` fuera del repo → mensaje + exit 1.
- **Sin romper el comportamiento actual:** `create_app(root)` sin `web_dir` se comporta igual que
  hoy. Los tests existentes de `test_app.py` siguen verdes.
- **Testabilidad por inyección:** `main` acepta `serve`/`opener`/`build_runner` inyectables (los
  tests no bloquean en uvicorn, no abren browser, no corren npm).
- **Frontend sin cambios** (el WS ya apunta a `:8787`).
- **Commits atómicos, en español, conventional commits.** Un commit por tarea.

---

### Task 1: `create_app` sirve el frontend estático

**Files:**
- Modify: `server/ide_server/app.py`
- Test: `server/tests/test_app.py`

**Interfaces:**
- Produces: `create_app(root: Path, web_dir: Path | None = None) -> FastAPI` — si `web_dir` tiene
  `index.html`, monta `StaticFiles(web_dir, html=True)` en `/` (último, tras las rutas).

- [ ] **Step 1: Tests que fallan**

Agregar a `server/tests/test_app.py`:

```python
def test_serves_frontend_when_web_dir(tmp_path):
    ws = _ws(tmp_path)
    web = tmp_path / "web"; web.mkdir()
    (web / "index.html").write_text("<html>IDE</html>")
    c = TestClient(create_app(ws, web_dir=web))
    assert "<html>IDE</html>" in c.get("/").text        # sirve index
    assert c.get("/health").json()["status"] == "ok"    # ruta específica gana
    assert c.get("/api/repos").json()["repos"][0]["name"] == "repo-a"


def test_no_web_dir_still_ok(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))            # sin web_dir
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/").status_code == 404                # no monta estáticos
```

- [ ] **Step 2: Correr, verificar que falla**

Run: `cd server && uv run pytest tests/test_app.py -q`
Expected: FAIL (`create_app() got an unexpected keyword argument 'web_dir'`).

- [ ] **Step 3: Implementar**

En `server/ide_server/app.py`, cambiar la firma a
`def create_app(root: Path, web_dir: Path | None = None) -> FastAPI:` y montar los estáticos al
final de `create_app` (justo antes de `return app`):

```python
    if web_dir is not None and (web_dir / "index.html").is_file():
        from starlette.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
```

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd server && uv run pytest tests/test_app.py -q` → PASS (incluidos los tests previos).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/app.py server/tests/test_app.py
git commit -m "feat(cli): create_app sirve el frontend estático desde web_dir"
```

---

### Task 2: CLI completo — resolución de web dir, auto-init, `ide build`, `main` inyectable

**Files:**
- Modify: `server/ide_server/cli.py`
- Test: `server/tests/test_cli.py`

**Interfaces:**
- Consumes: `create_app` (Task 1); `find_workspace_root` (existente).
- Produces: `PKG_WEB`, `repo_ui_dist()`, `repo_ui()`, `resolve_web_dir(pkg_web=PKG_WEB,
  repo_dist=None)`, `build_frontend(ui_dir, web_dir, runner=subprocess.run)`, `_serve(app, host,
  port)`; `main(argv=None, *, serve=None, opener=None, build_runner=None)` con comandos
  `run` (auto-init) / `init` / `build`.

- [ ] **Step 1: Tests que fallan (y actualizar el que cambia)**

En `server/tests/test_cli.py`: **eliminar** `test_main_without_workspace_returns_1` (ya no aplica:
`run` ahora auto-inicia). Dejar `test_init_creates_ide` y `test_resolve_root_after_init`. Agregar:

```python
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
    assert calls["opened"] == "http://127.0.0.1:8787"


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
```

> El import del tope del test necesita `from ide_server.cli import init_workspace, resolve_root,
> main` (ya está); agrega lo que falte.

- [ ] **Step 2: Correr, verificar que falla** → FAIL (`resolve_web_dir`/`build_frontend` no
  existen / `main` no acepta `serve`).

- [ ] **Step 3: Implementar**

Reescribir `server/ide_server/cli.py` (preservando `init_workspace`/`resolve_root`):

```python
from __future__ import annotations
import argparse
import shutil
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
        print("⚠ frontend no buildeado; ejecuta `ide build` (o `npm run build` en ui/).")

    if not args.no_browser:
        opener("http://127.0.0.1:8787")
    print(f"Workspace: {root}  →  http://127.0.0.1:8787")
    serve(create_app(root, web_dir), settings.host, settings.port)
    return 0
```

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd server && uv run pytest tests/test_cli.py -q` → PASS.
Suite completa: `cd server && uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/cli.py server/tests/test_cli.py
git commit -m "feat(cli): un solo comando ide (resolve_web_dir, auto-init, ide build, main inyectable)"
```

---

### Task 3: Packaging (hatchling artifacts + gitignore) + README

**Files:**
- Modify: `server/pyproject.toml`, `server/.gitignore` (crear si no existe), `README.md`

**Interfaces:** ninguna (config + docs).

- [ ] **Step 1: Declarar el package data del frontend**

En `server/pyproject.toml`, agregar (tras `[build-system]`):

```toml
[tool.hatch.build]
artifacts = ["ide_server/web/**"]
```

- [ ] **Step 2: Gitignorear el build**

Agregar a `server/.gitignore` (crear el archivo si no existe) la línea:

```
ide_server/web/
```

- [ ] **Step 3: Verificar el empaquetado (stub, sin npm real)**

```bash
cd server
mkdir -p ide_server/web && echo '<html>stub</html>' > ide_server/web/index.html
uv build 2>&1 | tail -2
unzip -l dist/*.whl | grep 'ide_server/web/index.html' && echo "OK: el frontend viaja en el wheel"
rm -rf dist ide_server/web
git status --porcelain    # debe quedar limpio salvo los archivos de esta tarea
```
Expected: `ide_server/web/index.html` aparece en el listado del wheel → el `artifacts` funciona.

- [ ] **Step 4: Actualizar el README (flujo de un comando)**

Reemplazar la sección "## Cómo correr" del `README.md` (raíz del repo) por:

````markdown
## Cómo correr

**Requisitos:** [`uv`](https://docs.astral.sh/uv/), Node + npm, y el binario `claude` de Claude
Code en el PATH, logueado por suscripción (**sin `ANTHROPIC_API_KEY`**).

### Un comando levanta todo

```bash
cd server && uv run ide build     # buildea el frontend y lo empaqueta en ide_server/web/
uv tool install ./server          # deja `ide` en el PATH con el frontend adentro

ide run --cwd /ruta/a/tu/workspace   # sirve todo en http://127.0.0.1:8787
```

`ide run` auto-crea `.ide/` si falta y abre el navegador (`--no-browser` lo evita).

### Desarrollo (hot-reload de la UI)

```bash
cd server && uv run ide run --cwd <ws> --no-browser   # backend + frontend servido
cd ui && npm run dev                                   # Vite en :5173 con hot-reload
```

En dev abre `:5173` (Vite); el WebSocket del frontend siempre pega a `:8787`.
````

- [ ] **Step 5: Suite + commit**

Run: `cd server && uv run pytest -q` → PASS (225+ passed). `git status` limpio salvo los archivos
de esta tarea (el `ide_server/web/` gitignoreado no debe aparecer).

```bash
git add server/pyproject.toml server/.gitignore README.md
git commit -m "build(cli): empaqueta el frontend en el wheel (hatchling artifacts) + README"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** servir estáticos (T1), resolve_web_dir + auto-init + main inyectable +
  ide build (T2), packaging + README (T3). ✓
- **Consistencia:** `create_app(root, web_dir)` (T1) ↔ llamado en `main` (T2); `build_frontend`
  con runner inyectable (T2) testeado en el mismo task; `PKG_WEB` monkeypatcheable. ✓
- **Riesgo señalado:** `StaticFiles` requiere que el dir exista (guard con `index.html` en T1). El
  `artifacts` de hatchling incluye archivos gitignoreados (verificado con el stub en T3).
- **Verificación E2E manual (fuera del plan):** `uv run ide build` real + `uv tool install` +
  `ide run` sirviendo la app en vivo — tras el merge, como con orquestación.
```
