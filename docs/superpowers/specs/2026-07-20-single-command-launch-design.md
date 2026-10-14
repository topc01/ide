# Spec — Arranque con un solo comando `ide`

> Fecha: 2026-07-20. Hoy `ide run` levanta solo el backend (:8787) y abre el browser a :5173 (el
> dev server de Vite que se corre aparte). Objetivo: **un solo `ide` que levante todo** —
> sirviendo el frontend buildeado desde FastAPI, con auto-init de `.ide/`, e instalable global.

## Objetivo

Que `ide run --cwd <workspace>` sea **un único comando** que sirve el frontend + backend + API +
WebSocket en un puerto (`:8787`), cree `.ide/` si falta, y abra el browser. Y que `ide` sea
**instalable global** (`uv tool install`) con el frontend buildeado adentro del paquete — patrón
Jupyter (el paquete Python trae el SPA como package data y lo sirve).

## Decisiones tomadas (brainstorming 2026-07-20)

1. **Servir el build estático** (no spawnear Vite): FastAPI sirve `ui/dist` en `:8787`. Sin
   hot-reload; para iterar UI se rebuildea (`ide build`). El dev loop sigue disponible con `npm
   run dev` desde el repo.
2. **Opción 2 completa**: `ide build` + `ide run` + instalable global (package data + `uv tool
   install`).
3. **Sin cambios en el frontend**: el WS ya está hardcodeado a `ws://localhost:8787/ws`, que
   funciona igual servido desde `:8787` que en dev desde `:5173` (el backend siempre está en :8787).

## Arquitectura

### `create_app(root, web_dir=None)` (`app.py`)

- Nuevo parámetro `web_dir: Path | None = None`.
- Al **final** de `create_app` (después de registrar `/health`, `/api/*`, `/ws`), si `web_dir` no
  es None y `web_dir/index.html` existe:
  `app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")`
  (import `from starlette.staticfiles import StaticFiles`). Se monta **último** para que las rutas
  específicas (`/health`, `/api/*`, `/ws`) ganen; el mount en `/` es catch-all para `index.html`
  + `assets/`. Sin `web_dir` (default) no se monta nada — el comportamiento actual no cambia.

### CLI (`cli.py`)

Constantes/helpers (parametrizables para tests):

- `PKG_WEB = Path(__file__).parent / "web"` — el frontend empaquetado (package data).
- `def repo_ui_dist() -> Path`: `Path(__file__).parent.parent.parent / "ui" / "dist"` (desde
  `server/ide_server/` → raíz del repo → `ui/dist`).
- `def repo_ui() -> Path | None`: `Path(__file__).parent.parent.parent / "ui"` si tiene
  `package.json`, si no `None`.
- `def resolve_web_dir(pkg_web: Path = PKG_WEB, repo_dist: Path | None = None) -> Path | None`:
  `repo_dist` default `repo_ui_dist()`. Devuelve `pkg_web` si `pkg_web/index.html` existe; si no,
  `repo_dist` si `repo_dist/index.html` existe; si no, `None`.
- `def build_frontend(ui_dir: Path, web_dir: Path, runner=subprocess.run) -> int`: corre
  `runner(["npm", "run", "build"], cwd=ui_dir, check=True)`; luego reemplaza `web_dir` por el
  contenido de `ui_dir/dist` (borra `web_dir` si existe, `shutil.copytree(ui_dir/"dist", web_dir)`).
  Devuelve 0. (El `runner` inyectable permite testear la copia sin correr npm.)

`main(argv=None, *, serve=None, opener=None, build_runner=None) -> int`:

- `serve = serve or _serve` (donde `_serve(app, host, port)` hace `uvicorn.run(...)`), `opener =
  opener or webbrowser.open`, `build_runner = build_runner or subprocess.run`. Inyectables para
  tests (evitan bloquear en uvicorn / abrir browser / correr npm).
- `command` ∈ `{"run", "init", "build"}` (default `run`).
- `init` → `init_workspace(cwd)`, print, 0 (igual que hoy).
- `build` → `ui = repo_ui()`; si `None` → print "ide build solo corre desde el checkout del repo
  (no se encontró ui/)", return 1; si no → `build_frontend(ui, PKG_WEB, build_runner)`, print
  "Frontend buildeado en {PKG_WEB}", 0.
- `run`:
  - `root = resolve_root(cwd)`; si `None` → **auto-init**: `init_workspace(cwd)`, print
    "Workspace .ide/ creado en {cwd}", `root = cwd`.
  - `web_dir = resolve_web_dir()`; si `None` → print "⚠ frontend no buildeado; ejecuta `ide build`
    (o `npm run build` en ui/)". (Igual arranca el backend — la API/WS funcionan.)
  - si no `--no-browser` → `opener("http://127.0.0.1:8787")`.
  - print "Workspace: {root} → http://127.0.0.1:8787".
  - `serve(create_app(root, web_dir), settings.host, settings.port)`; return 0.

### Packaging (`pyproject.toml`, hatchling)

- `[tool.hatch.build]` → `artifacts = ["ide_server/web/**"]` — fuerza incluir el frontend
  buildeado (gitignoreado) en el wheel.
- `.gitignore` (server) → `ide_server/web/` (no se commitea el build).
- Flujo global: `uv run ide build` (popula `ide_server/web/`) → `uv tool install ./server` →
  `ide` en el PATH con el frontend adentro. `ide run --cwd <ws>` desde cualquier lado.

## Flujo de datos

`ide run --cwd ~/ws` → resuelve/auto-crea `.ide/` → `resolve_web_dir()` (bundle > `ui/dist` >
None) → abre browser :8787 → uvicorn sirve `StaticFiles(web_dir)` + API + WS. El browser carga
`index.html` de :8787; el WS se conecta a `ws://localhost:8787/ws` (mismo host). `ide build`
regenera `ide_server/web/` desde `ui/dist`.

## Manejo de errores

- `ide build` fuera del repo (sin `ui/`) → mensaje claro + exit 1.
- `ide run` sin frontend buildeado → warning + arranca igual (backend funcional); no crashea.
- `npm run build` que falla → `subprocess.run(check=True)` levanta `CalledProcessError` → propaga
  (el usuario ve el error de npm). Sin fallo silencioso.

## Plan de tests (TDD)

**Backend (`server/`):**
1. `create_app` con `web_dir`: `TestClient(create_app(ws, web_dir=tmp))` donde `tmp/index.html`
   existe → `GET /` devuelve el html; `GET /health` sigue 200; `GET /api/repos` sigue funcionando.
   Sin `web_dir` → `GET /` no sirve index (404) pero `/health` funciona (comportamiento actual).
2. `resolve_web_dir(pkg_web, repo_dist)`: bundle gana si tiene index; si no, repo_dist; si ninguno,
   None. (tmp dirs con/ sin `index.html`.)
3. `build_frontend(ui_dir, web_dir, runner=fake)`: el fake runner crea `ui_dir/dist/index.html`;
   `build_frontend` copia a `web_dir` (index.html presente); llamó al runner con `["npm","run",
   "build"]` y `cwd=ui_dir`; si `web_dir` ya existía, lo reemplaza.
4. `main(["run","--cwd",tmp], serve=noop, opener=noop)`: **auto-init** — crea `.ide/`, return 0,
   no bloquea (serve inyectado). `main(["run","--cwd",ws_existente], serve=noop, opener=noop,
   ...)` no re-inicializa. `main(["build"], build_runner=...)` fuera del repo → mensaje + 1
   (o con repo_ui mockeado, llama build). `main(["init"])` sigue creando `.ide/`.
   Actualizar/replazar `test_main_without_workspace_returns_1` (ya no aplica: ahora auto-inicia).

**Verificación de packaging (paso manual en la tarea, no unit test):**
5. `cd server && uv run ide build` popula `ide_server/web/`; `uv build` produce un wheel que
   incluye `ide_server/web/` (`unzip -l dist/*.whl | grep web/`). Documentado en la tarea.

## Fuera de alcance (Fase 2+)

- `--dev` que spawnee Vite con hot-reload (elegimos servir el build).
- Auto-rebuild inteligente por mtime (hoy `ide build` es explícito; `ide run` sirve lo que haya).
- Publicar el paquete a un índice; hoy `uv tool install ./server` desde el checkout.
- Elegir puerto/host por flag (siguen viniendo de `Settings`, :8787).

## Fidelidad de UI

No aplica (cambio de backend/CLI/packaging). El frontend servido es idéntico al de dev.
