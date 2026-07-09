# R0 — Fundación · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levantar el esqueleto de la app (comando `ide` + backend FastAPI/WS + frontend React con layout 3 regiones y theming 1a + sistema de plugins), con un "esqueleto que camina" que lista los repos reales del workspace en el sidebar.

**Architecture:** Un workspace es un directorio que contiene `.ide/`. El comando `ide` lo detecta por walk-up y levanta un backend FastAPI apuntado a él. El backend expone REST (lecturas) + WebSocket (envelope único `{type,id,channel,payload}`) y despacha capacidades vía un registro de plugins. El frontend (Vite+React+TS) monta el layout de 3 regiones con tokens 1a, un store Zustand y clientes REST/WS; los 6 módulos del rail se registran vía una interfaz de plugin.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, pydantic-settings, pytest (+ `uv`). React 18, Vite, TypeScript, Zustand, lucide-react, vitest + @testing-library/react.

Spec: `docs/superpowers/specs/2026-07-07-foundation-design.md`.

## Global Constraints

- **Fidelidad de UI (no negociable):** dirección visual **1a — Terminal/amber**; tokens exactos en `docs/design/REFERENCES.md` (accent `#e0863f`, app bg `#161513`, panel `#1c1a17`, border `#332f28`, text primary `#f0ece4`). Nada de estética por defecto.
- **Sin fallos silenciosos:** todo error del backend viaja como `{type:"error", payload:{code,message}}`; el frontend muestra "desconectado" en vez de datos viejos.
- **Layout raíz del repo:** backend en `server/` (paquete `ide_server`), frontend en `ui/`.
- **Puertos dev:** backend `8787`, Vite `5173`, con CORS.
- **Envelope WS:** `{ "type": "req|res|event|error", "id": "<uuid>", "channel": "<string>", "payload": {} }`.
- **Nombre de trabajo del proyecto:** "Agentic IDE" (renombrable).

---

## File Structure

**Backend (`server/`)**
- `server/pyproject.toml` — proyecto `uv`, deps, config pytest, entry-point `ide`.
- `server/ide_server/__init__.py`
- `server/ide_server/workspace.py` — `find_workspace_root`, `discover_repos`.
- `server/ide_server/config.py` — `Settings`, `load_config`.
- `server/ide_server/plugins.py` — `Registry`.
- `server/ide_server/bus.py` — envelope + `ConnectionManager` + `handle_message`.
- `server/ide_server/capabilities/__init__.py`
- `server/ide_server/capabilities/repos.py` — `repos.list` + `register`.
- `server/ide_server/app.py` — `create_app`.
- `server/ide_server/cli.py` — `main` (`ide` / `ide init`).
- `server/tests/…` — un test por unidad.

**Frontend (`ui/`)**
- `ui/package.json`, `ui/vite.config.ts`, `ui/tsconfig.json`, `ui/index.html`, `ui/vitest.setup.ts`
- `ui/src/main.tsx`, `ui/src/App.tsx`
- `ui/src/theme/tokens.ts`, `ui/src/theme/theme.css`
- `ui/src/transport/envelope.ts`, `ui/src/transport/ws.ts`, `ui/src/transport/rest.ts`
- `ui/src/state/store.ts`
- `ui/src/modules/registry.tsx`, `ui/src/modules/stubs.tsx`
- `ui/src/layout/{Sidebar,ActivityRail,ContextPanel,MainPanel,TabStrip}.tsx`
- tests colocados `*.test.ts(x)`.

---

## Task 1: Backend scaffold (`uv` + pytest)

**Files:**
- Create: `server/pyproject.toml`, `server/ide_server/__init__.py`, `server/tests/test_smoke.py`

**Interfaces:**
- Produces: paquete importable `ide_server`; `uv run pytest` operativo.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_smoke.py
import ide_server

def test_package_imports():
    assert ide_server.__version__ == "0.0.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_smoke.py -v`
Expected: FAIL (ModuleNotFoundError: ide_server / config missing).

- [ ] **Step 3: Write minimal implementation**

```toml
# server/pyproject.toml
[project]
name = "ide-server"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "pydantic-settings>=2.4"]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]

[project.scripts]
ide = "ide_server.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
pythonpath = ["."]
```

```python
# server/ide_server/__init__.py
__version__ = "0.0.0"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv sync --extra dev && uv run pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/pyproject.toml server/ide_server/__init__.py server/tests/test_smoke.py
git commit -m "chore(server): scaffold uv project + pytest"
```

---

## Task 2: `workspace.py` — detección de workspace y descubrimiento de repos

**Files:**
- Create: `server/ide_server/workspace.py`, `server/tests/test_workspace.py`

**Interfaces:**
- Produces:
  - `find_workspace_root(start: Path) -> Path | None` — walk-up hasta un dir con `.ide/`.
  - `discover_repos(root: Path) -> list[dict]` — `[{ "id": str, "name": str, "branch": str }]` para cada hijo directo con `.git`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_workspace.py
import subprocess
from pathlib import Path
from ide_server.workspace import find_workspace_root, discover_repos

def _git_repo(path: Path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=path, check=True)

def test_find_root_walks_up(tmp_path):
    (tmp_path / ".ide").mkdir()
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert find_workspace_root(deep) == tmp_path

def test_find_root_none_when_absent(tmp_path):
    assert find_workspace_root(tmp_path) is None

def test_discover_repos(tmp_path):
    (tmp_path / ".ide").mkdir()
    _git_repo(tmp_path / "repo-a")
    _git_repo(tmp_path / "repo-b")
    repos = discover_repos(tmp_path)
    names = sorted(r["name"] for r in repos)
    assert names == ["repo-a", "repo-b"]
    assert all(r["branch"] == "main" for r in repos)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_workspace.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/workspace.py
from __future__ import annotations
import subprocess
from pathlib import Path


def find_workspace_root(start: Path) -> Path | None:
    start = start.resolve()
    for candidate in [start, *start.parents]:
        if (candidate / ".ide").is_dir():
            return candidate
    return None


def _current_branch(repo: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return out.stdout.strip() or "HEAD"


def discover_repos(root: Path) -> list[dict]:
    repos: list[dict] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if (child / ".git").exists():
            repos.append({"id": child.name, "name": child.name, "branch": _current_branch(child)})
    return repos
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_workspace.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/workspace.py server/tests/test_workspace.py
git commit -m "feat(server): workspace detection + repo discovery"
```

---

## Task 3: `config.py` — settings + carga de `.ide/config.toml`

**Files:**
- Create: `server/ide_server/config.py`, `server/tests/test_config.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `Settings` (pydantic-settings): `host: str = "127.0.0.1"`, `port: int = 8787`, `cors_origins: list[str] = ["http://localhost:5173"]`.
  - `load_workspace_config(root: Path) -> dict` — parsea `<root>/.ide/config.toml` (usa `tomllib`); `{}` si no existe.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_config.py
from pathlib import Path
from ide_server.config import Settings, load_workspace_config

def test_defaults():
    s = Settings()
    assert s.port == 8787
    assert "http://localhost:5173" in s.cors_origins

def test_load_config(tmp_path):
    ide = tmp_path / ".ide"; ide.mkdir()
    (ide / "config.toml").write_text('name = "finnecto"\n')
    assert load_workspace_config(tmp_path)["name"] == "finnecto"

def test_load_config_missing(tmp_path):
    assert load_workspace_config(tmp_path) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_config.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/config.py
from __future__ import annotations
import tomllib
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8787
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_prefix": "IDE_"}


def load_workspace_config(root: Path) -> dict:
    path = root / ".ide" / "config.toml"
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/config.py server/tests/test_config.py
git commit -m "feat(server): settings + .ide/config.toml loader"
```

---

## Task 4: `plugins.py` — registro de capacidades

**Files:**
- Create: `server/ide_server/plugins.py`, `server/tests/test_plugins.py`

**Interfaces:**
- Produces:
  - `Registry` con `register(channel: str, handler: Callable[[dict], Awaitable[dict]])` y `async dispatch(channel: str, payload: dict) -> dict`.
  - `dispatch` levanta `KeyError` si el canal no existe.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_plugins.py
import pytest
from ide_server.plugins import Registry

@pytest.mark.asyncio
async def test_register_and_dispatch():
    reg = Registry()
    async def handler(payload): return {"echo": payload["x"]}
    reg.register("t.echo", handler)
    assert await reg.dispatch("t.echo", {"x": 1}) == {"echo": 1}

@pytest.mark.asyncio
async def test_unknown_channel():
    reg = Registry()
    with pytest.raises(KeyError):
        await reg.dispatch("nope", {})
```

- [ ] **Step 2: Run test to verify it fails**

Add `pytest-asyncio>=0.23` to dev deps in `pyproject.toml`, and under `[tool.pytest.ini_options]` add `asyncio_mode = "auto"`. Then:
Run: `cd server && uv sync --extra dev && uv run pytest tests/test_plugins.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/plugins.py
from __future__ import annotations
from typing import Awaitable, Callable

Handler = Callable[[dict], Awaitable[dict]]


class Registry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, channel: str, handler: Handler) -> None:
        self._handlers[channel] = handler

    async def dispatch(self, channel: str, payload: dict) -> dict:
        if channel not in self._handlers:
            raise KeyError(channel)
        return await self._handlers[channel](payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_plugins.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/pyproject.toml server/ide_server/plugins.py server/tests/test_plugins.py
git commit -m "feat(server): plugin registry (register/dispatch)"
```

---

## Task 5: `bus.py` — envelope + ruteo de mensajes

**Files:**
- Create: `server/ide_server/bus.py`, `server/tests/test_bus.py`

**Interfaces:**
- Consumes: `Registry` (Task 4).
- Produces:
  - `async handle_message(raw: str, registry: Registry) -> str` — parsea un `req`, despacha, devuelve `res` o `error` (JSON string) con el mismo `id`/`channel`.
  - `ConnectionManager` con `connect`/`disconnect`/`broadcast(channel, payload)` (usado por el WS en app).

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_bus.py
import json
import pytest
from ide_server.bus import handle_message
from ide_server.plugins import Registry

@pytest.mark.asyncio
async def test_req_returns_res():
    reg = Registry()
    async def h(p): return {"n": p["n"] + 1}
    reg.register("t.inc", h)
    raw = json.dumps({"type": "req", "id": "1", "channel": "t.inc", "payload": {"n": 41}})
    out = json.loads(await handle_message(raw, reg))
    assert out == {"type": "res", "id": "1", "channel": "t.inc", "payload": {"n": 42}}

@pytest.mark.asyncio
async def test_unknown_channel_returns_error():
    raw = json.dumps({"type": "req", "id": "9", "channel": "nope", "payload": {}})
    out = json.loads(await handle_message(raw, Registry()))
    assert out["type"] == "error"
    assert out["id"] == "9"
    assert out["payload"]["code"] == "unknown_channel"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_bus.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/bus.py
from __future__ import annotations
import json
from ide_server.plugins import Registry


async def handle_message(raw: str, registry: Registry) -> str:
    msg = json.loads(raw)
    mid, channel = msg.get("id"), msg.get("channel")
    try:
        payload = await registry.dispatch(channel, msg.get("payload") or {})
        return json.dumps({"type": "res", "id": mid, "channel": channel, "payload": payload})
    except KeyError:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": "unknown_channel", "message": f"no handler: {channel}"}})
    except Exception as exc:  # noqa: BLE001 — todo error viaja como envelope, nunca silencioso
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": "handler_error", "message": str(exc)}})


class ConnectionManager:
    def __init__(self) -> None:
        self._active: set = set()

    async def connect(self, ws) -> None:
        await ws.accept()
        self._active.add(ws)

    def disconnect(self, ws) -> None:
        self._active.discard(ws)

    async def broadcast(self, channel: str, payload: dict) -> None:
        msg = json.dumps({"type": "event", "id": None, "channel": channel, "payload": payload})
        for ws in list(self._active):
            await ws.send_text(msg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_bus.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/bus.py server/tests/test_bus.py
git commit -m "feat(server): message envelope + bus routing + ConnectionManager"
```

---

## Task 6: `capabilities/repos.py` — capacidad `repos.list`

**Files:**
- Create: `server/ide_server/capabilities/__init__.py`, `server/ide_server/capabilities/repos.py`, `server/tests/test_repos.py`

**Interfaces:**
- Consumes: `Registry` (Task 4), `discover_repos` (Task 2).
- Produces: `register(registry: Registry, root: Path) -> None` que registra `repos.list` → `{ "repos": [ {id,name,branch} ] }`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_repos.py
import subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import repos as repos_cap

def _git_repo(path: Path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=path, check=True)

@pytest.mark.asyncio
async def test_repos_list(tmp_path):
    (tmp_path / ".ide").mkdir()
    _git_repo(tmp_path / "repo-a")
    reg = Registry()
    repos_cap.register(reg, tmp_path)
    out = await reg.dispatch("repos.list", {})
    assert out["repos"][0]["name"] == "repo-a"

@pytest.mark.asyncio
async def test_repos_list_empty(tmp_path):
    (tmp_path / ".ide").mkdir()
    reg = Registry()
    repos_cap.register(reg, tmp_path)
    assert await reg.dispatch("repos.list", {}) == {"repos": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_repos.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/capabilities/__init__.py
```

```python
# server/ide_server/capabilities/repos.py
from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.workspace import discover_repos


def register(registry: Registry, root: Path) -> None:
    async def handle(_payload: dict) -> dict:
        return {"repos": discover_repos(root)}
    registry.register("repos.list", handle)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_repos.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities server/tests/test_repos.py
git commit -m "feat(server): repos.list capability"
```

---

## Task 7: `app.py` — FastAPI (health, /api/repos, /ws)

**Files:**
- Create: `server/ide_server/app.py`, `server/tests/test_app.py`

**Interfaces:**
- Consumes: `Settings`, `Registry`, `handle_message`, `ConnectionManager`, `repos_cap.register`.
- Produces: `create_app(root: Path) -> FastAPI` con `GET /health`, `GET /api/repos`, `WS /ws`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_app.py
import json, subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from ide_server.app import create_app

def _ws(tmp_path: Path):
    (tmp_path / ".ide").mkdir()
    r = tmp_path / "repo-a"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=r, check=True)
    return tmp_path

def test_health(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    assert c.get("/health").json()["status"] == "ok"

def test_api_repos(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    data = c.get("/api/repos").json()
    assert data["repos"][0]["name"] == "repo-a"

def test_ws_req_res(tmp_path):
    c = TestClient(create_app(_ws(tmp_path)))
    with c.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "req", "id": "1", "channel": "repos.list", "payload": {}}))
        out = json.loads(ws.receive_text())
        assert out["type"] == "res" and out["id"] == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_app.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/app.py
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ide_server.config import Settings
from ide_server.plugins import Registry
from ide_server.bus import handle_message, ConnectionManager
from ide_server.capabilities import repos as repos_cap


def create_app(root: Path) -> FastAPI:
    settings = Settings()
    registry = Registry()
    repos_cap.register(registry, root)
    manager = ConnectionManager()

    app = FastAPI(title="Agentic IDE")
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/repos")
    async def api_repos() -> dict:
        return await registry.dispatch("repos.list", {})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        try:
            while True:
                raw = await ws.receive_text()
                await ws.send_text(await handle_message(raw, registry))
        except WebSocketDisconnect:
            manager.disconnect(ws)

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_app.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/app.py server/tests/test_app.py
git commit -m "feat(server): FastAPI app (health, /api/repos, /ws)"
```

---

## Task 8: `cli.py` — comando `ide` / `ide init`

**Files:**
- Create: `server/ide_server/cli.py`, `server/tests/test_cli.py`

**Interfaces:**
- Consumes: `find_workspace_root` (Task 2), `create_app` (Task 7), `Settings`.
- Produces:
  - `init_workspace(cwd: Path) -> Path` — crea `<cwd>/.ide/` con `config.toml` mínimo; devuelve el path del `.ide`.
  - `resolve_root(cwd: Path) -> Path | None` — envuelve `find_workspace_root`.
  - `main(argv: list[str] | None = None) -> int` — `ide init` inicializa; `ide` resuelve root y (si existe) levanta uvicorn + abre navegador; si no, imprime sugerencia de `ide init` y devuelve 1.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_cli.py
from pathlib import Path
from ide_server.cli import init_workspace, resolve_root, main

def test_init_creates_ide(tmp_path):
    ide = init_workspace(tmp_path)
    assert ide == tmp_path / ".ide"
    assert (ide / "config.toml").is_file()

def test_resolve_root_after_init(tmp_path):
    init_workspace(tmp_path)
    assert resolve_root(tmp_path) == tmp_path

def test_main_without_workspace_returns_1(tmp_path, capsys):
    code = main(["--cwd", str(tmp_path)])   # no .ide/ → sugiere init
    assert code == 1
    assert "ide init" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_cli.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/cli.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_cli.py -v`
Expected: PASS (3 tests). Full backend: `uv run pytest -v` → todo verde.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/cli.py server/tests/test_cli.py
git commit -m "feat(server): ide CLI (init + walk-up + launch)"
```

---

## Task 9: Frontend scaffold (Vite + React + TS + vitest)

**Files:**
- Create: `ui/package.json`, `ui/vite.config.ts`, `ui/tsconfig.json`, `ui/index.html`, `ui/vitest.setup.ts`, `ui/src/main.tsx`, `ui/src/smoke.test.ts`

**Interfaces:**
- Produces: `npm test` operativo (vitest jsdom).

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/smoke.test.ts
import { describe, it, expect } from "vitest";
describe("smoke", () => { it("suma", () => expect(1 + 1).toBe(2)); });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test`
Expected: FAIL (no package.json / vitest no instalado).

- [ ] **Step 3: Write minimal implementation**

```json
// ui/package.json
{
  "name": "ide-ui",
  "private": true,
  "type": "module",
  "scripts": { "dev": "vite", "build": "tsc && vite build", "test": "vitest run" },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1", "zustand": "^4.5.5", "lucide-react": "^0.454.0" },
  "devDependencies": {
    "@testing-library/react": "^16.0.1", "@testing-library/jest-dom": "^6.5.0",
    "@types/react": "^18.3.11", "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2", "jsdom": "^25.0.1", "typescript": "^5.6.3",
    "vite": "^5.4.8", "vitest": "^2.1.2"
  }
}
```

```ts
// ui/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: { environment: "jsdom", setupFiles: ["./vitest.setup.ts"], globals: true },
});
```

```json
// ui/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext",
    "moduleResolution": "bundler", "jsx": "react-jsx", "strict": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"], "skipLibCheck": true
  },
  "include": ["src", "vitest.setup.ts", "vite.config.ts"]
}
```

```html
<!-- ui/index.html -->
<!doctype html><html lang="es"><head><meta charset="UTF-8" />
<title>Agentic IDE</title></head><body><div id="root"></div>
<script type="module" src="/src/main.tsx"></script></body></html>
```

```ts
// ui/vitest.setup.ts
import "@testing-library/jest-dom";
```

```tsx
// ui/src/main.tsx
import { createRoot } from "react-dom/client";
import App from "./App";
import "./theme/theme.css";
createRoot(document.getElementById("root")!).render(<App />);
```

(`App` y `theme.css` se crean en tareas siguientes; `main.tsx` aún no se importa en tests.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm install && npm test`
Expected: PASS (smoke).

- [ ] **Step 5: Commit**

```bash
git add ui/package.json ui/vite.config.ts ui/tsconfig.json ui/index.html ui/vitest.setup.ts ui/src/main.tsx ui/src/smoke.test.ts
git commit -m "chore(ui): scaffold vite+react+ts+vitest"
```

---

## Task 10: Theming 1a (tokens + CSS variables)

**Files:**
- Create: `ui/src/theme/tokens.ts`, `ui/src/theme/theme.css`, `ui/src/theme/tokens.test.ts`

**Interfaces:**
- Produces:
  - `tokens` — objeto con la paleta 1a (`accent`, `appBg`, `panelBg`, `border`, `textPrimary`, …).
  - `applyTheme(root: HTMLElement)` — setea las CSS variables (`--accent`, …) en `root`.

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/theme/tokens.test.ts
import { describe, it, expect } from "vitest";
import { tokens, applyTheme } from "./tokens";

describe("tokens 1a", () => {
  it("accent es amber 1a", () => expect(tokens.accent).toBe("#e0863f"));
  it("applyTheme setea las CSS vars", () => {
    const el = document.createElement("div");
    applyTheme(el);
    expect(el.style.getPropertyValue("--accent")).toBe("#e0863f");
    expect(el.style.getPropertyValue("--app-bg")).toBe("#161513");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- tokens`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```ts
// ui/src/theme/tokens.ts
export const tokens = {
  appBg: "#161513", panelBg: "#1c1a17", titleBg: "#131210", terminalBg: "#0f0e0c",
  agentBubble: "#211e1a", border: "#332f28", borderSoft: "#2a2721",
  textPrimary: "#f0ece4", textSecondary: "#cfc9bd", textMuted: "#75705f",
  accent: "#e0863f", accentHover: "#eb954f", onAccent: "#161513",
  selectedBg: "#2e2820", statusRunning: "#7fb069", statusIdle: "#7d7568", statusDone: "#6b8fbf",
} as const;

const VARS: Record<string, keyof typeof tokens> = {
  "--app-bg": "appBg", "--panel-bg": "panelBg", "--title-bg": "titleBg",
  "--terminal-bg": "terminalBg", "--agent-bubble": "agentBubble", "--border": "border",
  "--border-soft": "borderSoft", "--text-primary": "textPrimary",
  "--text-secondary": "textSecondary", "--text-muted": "textMuted",
  "--accent": "accent", "--accent-hover": "accentHover", "--on-accent": "onAccent",
  "--selected-bg": "selectedBg",
};

export function applyTheme(root: HTMLElement): void {
  for (const [cssVar, key] of Object.entries(VARS)) root.style.setProperty(cssVar, tokens[key]);
}
```

```css
/* ui/src/theme/theme.css */
:root {
  --app-bg: #161513; --panel-bg: #1c1a17; --title-bg: #131210; --terminal-bg: #0f0e0c;
  --agent-bubble: #211e1a; --border: #332f28; --border-soft: #2a2721;
  --text-primary: #f0ece4; --text-secondary: #cfc9bd; --text-muted: #75705f;
  --accent: #e0863f; --accent-hover: #eb954f; --on-accent: #161513; --selected-bg: #2e2820;
  --radius: 8px;
  font-family: Inter, system-ui, sans-serif; font-size: 13px;
}
* { box-sizing: border-box; }
html, body, #root { height: 100%; margin: 0; }
body { background: var(--app-bg); color: var(--text-primary); }
code, .mono { font-family: "JetBrains Mono", ui-monospace, monospace; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- tokens`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/theme
git commit -m "feat(ui): 1a theming tokens + css variables"
```

---

## Task 11: Transport (envelope + REST + WS con correlación)

**Files:**
- Create: `ui/src/transport/envelope.ts`, `ui/src/transport/rest.ts`, `ui/src/transport/ws.ts`, `ui/src/transport/ws.test.ts`

**Interfaces:**
- Produces:
  - `envelope.ts`: tipos `Envelope`, `Repo = { id; name; branch }`.
  - `rest.ts`: `getRepos(base?): Promise<Repo[]>`.
  - `ws.ts`: clase `WsClient` con `request(channel, payload): Promise<any>` (correlaciona por `id`) y `on(channel, cb)` para eventos.

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/transport/ws.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WsClient } from "./ws";

class FakeSocket {
  onopen: any; onmessage: any; onclose: any; sent: string[] = [];
  constructor(public url: string) { setTimeout(() => this.onopen?.(), 0); }
  send(s: string) {
    this.sent.push(s);
    const req = JSON.parse(s);
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(
      { type: "res", id: req.id, channel: req.channel, payload: { ok: req.payload.n } }) }), 0);
  }
  close() { this.onclose?.(); }
}

describe("WsClient", () => {
  beforeEach(() => { (globalThis as any).WebSocket = FakeSocket; });
  it("correlaciona req/res por id", async () => {
    const c = new WsClient("ws://x/ws"); await c.ready();
    expect(await c.request("t.inc", { n: 5 })).toEqual({ ok: 5 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- ws`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```ts
// ui/src/transport/envelope.ts
export type EnvType = "req" | "res" | "event" | "error";
export interface Envelope { type: EnvType; id: string | null; channel: string; payload: any; }
export interface Repo { id: string; name: string; branch: string; }
```

```ts
// ui/src/transport/rest.ts
import type { Repo } from "./envelope";
const BASE = "http://localhost:8787";
export async function getRepos(base: string = BASE): Promise<Repo[]> {
  const res = await fetch(`${base}/api/repos`);
  if (!res.ok) throw new Error(`repos ${res.status}`);
  return (await res.json()).repos as Repo[];
}
```

```ts
// ui/src/transport/ws.ts
import type { Envelope } from "./envelope";

export class WsClient {
  private ws: WebSocket;
  private pending = new Map<string, (p: any) => void>();
  private listeners = new Map<string, ((p: any) => void)[]>();
  private openP: Promise<void>;

  constructor(url: string) {
    this.ws = new WebSocket(url);
    this.openP = new Promise((r) => (this.ws.onopen = () => r()));
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data) as Envelope);
  }
  ready() { return this.openP; }

  private onMessage(msg: Envelope) {
    if ((msg.type === "res" || msg.type === "error") && msg.id) {
      this.pending.get(msg.id)?.(msg.type === "error" ? Promise.reject(msg.payload) : msg.payload);
      this.pending.delete(msg.id);
    } else if (msg.type === "event") {
      (this.listeners.get(msg.channel) ?? []).forEach((cb) => cb(msg.payload));
    }
  }
  request(channel: string, payload: any): Promise<any> {
    const id = crypto.randomUUID();
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this.ws.send(JSON.stringify({ type: "req", id, channel, payload }));
    });
  }
  on(channel: string, cb: (p: any) => void) {
    this.listeners.set(channel, [...(this.listeners.get(channel) ?? []), cb]);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- ws`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport
git commit -m "feat(ui): transport (envelope + rest + ws correlation)"
```

---

## Task 12: Store global (Zustand)

**Files:**
- Create: `ui/src/state/store.ts`, `ui/src/state/store.test.ts`

**Interfaces:**
- Consumes: `Repo` (Task 11).
- Produces: `useStore` con `repos`, `activePanel`, `openTabs`, `activeTabId` + acciones `setRepos`, `setActivePanel`, `openTab(tab)`, `closeTab(id)`. `closeTab` de la tab activa cae a la anterior o `"chat"`.

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/state/store.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./store";

describe("store", () => {
  beforeEach(() => useStore.setState({ repos: [], activePanel: "sessions", openTabs: [], activeTabId: "chat" }));
  it("setRepos", () => { useStore.getState().setRepos([{ id: "a", name: "a", branch: "main" }]);
    expect(useStore.getState().repos).toHaveLength(1); });
  it("open/close tab cae a chat", () => {
    const s = useStore.getState();
    s.openTab({ id: "t1", type: "file", label: "f" });
    expect(useStore.getState().activeTabId).toBe("t1");
    useStore.getState().closeTab("t1");
    expect(useStore.getState().activeTabId).toBe("chat");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- store`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```ts
// ui/src/state/store.ts
import { create } from "zustand";
import type { Repo } from "../transport/envelope";

export type PanelId = "search" | "changes" | "graphite" | "tasks" | "terminal" | "notion" | "sessions";
export interface Tab { id: string; type: "file" | "task" | "branch" | "terminal" | "page"; label: string; }

interface State {
  repos: Repo[]; activePanel: PanelId; openTabs: Tab[]; activeTabId: string;
  setRepos: (r: Repo[]) => void;
  setActivePanel: (p: PanelId) => void;
  openTab: (t: Tab) => void;
  closeTab: (id: string) => void;
}

export const useStore = create<State>((set) => ({
  repos: [], activePanel: "sessions", openTabs: [], activeTabId: "chat",
  setRepos: (repos) => set({ repos }),
  setActivePanel: (activePanel) => set({ activePanel }),
  openTab: (t) => set((s) => ({
    openTabs: s.openTabs.some((x) => x.id === t.id) ? s.openTabs : [...s.openTabs, t],
    activeTabId: t.id,
  })),
  closeTab: (id) => set((s) => {
    const tabs = s.openTabs.filter((t) => t.id !== id);
    const active = s.activeTabId === id ? (tabs.at(-1)?.id ?? "chat") : s.activeTabId;
    return { openTabs: tabs, activeTabId: active };
  }),
}));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- store`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/state
git commit -m "feat(ui): zustand store (repos, panel, tabs)"
```

---

## Task 13: Registro de módulos (plugins del rail)

**Files:**
- Create: `ui/src/modules/registry.tsx`, `ui/src/modules/stubs.tsx`, `ui/src/modules/registry.test.ts`

**Interfaces:**
- Consumes: `PanelId` (Task 12).
- Produces:
  - `ActivityModule = { id: PanelId; title: string; icon: LucideIcon; Panel: React.FC }`.
  - `registerModule(m)`, `getModules(): ActivityModule[]`.
  - `stubs.tsx` registra los 6 módulos (sessions con panel real mínimo en Task 15; el resto stubs).

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/modules/registry.test.ts
import { describe, it, expect } from "vitest";
import { getModules } from "./stubs";

describe("module registry", () => {
  it("registra 6 módulos del rail", () => {
    const ids = getModules().map((m) => m.id);
    expect(ids).toEqual(
      expect.arrayContaining(["search", "changes", "graphite", "tasks", "terminal", "notion"]));
    expect(getModules().length).toBeGreaterThanOrEqual(6);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- registry`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/modules/registry.tsx
import type { LucideIcon } from "lucide-react";
import type { PanelId } from "../state/store";

export interface ActivityModule { id: PanelId; title: string; icon: LucideIcon; Panel: React.FC; }
const modules: ActivityModule[] = [];
export function registerModule(m: ActivityModule) {
  if (!modules.some((x) => x.id === m.id)) modules.push(m);
}
export function getModules(): ActivityModule[] { return modules; }
```

```tsx
// ui/src/modules/stubs.tsx
import { Search, FileDiff, Layers, ListChecks, SquareTerminal, BookOpen } from "lucide-react";
import { registerModule, getModules } from "./registry";

const Stub = (label: string): React.FC => () => (
  <div style={{ padding: 12, color: "var(--text-muted)" }}>{label} — próximamente</div>
);

registerModule({ id: "search", title: "Search", icon: Search, Panel: Stub("Search") });
registerModule({ id: "changes", title: "Changed files", icon: FileDiff, Panel: Stub("Changed files") });
registerModule({ id: "graphite", title: "Graphite", icon: Layers, Panel: Stub("Graphite") });
registerModule({ id: "tasks", title: "Tasks", icon: ListChecks, Panel: Stub("Tasks") });
registerModule({ id: "terminal", title: "Terminal", icon: SquareTerminal, Panel: Stub("Terminal") });
registerModule({ id: "notion", title: "Notion", icon: BookOpen, Panel: Stub("Notion") });

export { getModules };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- registry`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules
git commit -m "feat(ui): activity module registry + 6 rail slots"
```

---

## Task 14: Layout de 3 regiones (estilo 1a)

**Files:**
- Create: `ui/src/layout/Sidebar.tsx`, `ui/src/layout/ActivityRail.tsx`, `ui/src/layout/ContextPanel.tsx`, `ui/src/layout/MainPanel.tsx`, `ui/src/layout/TabStrip.tsx`, `ui/src/layout/layout.test.tsx`

**Interfaces:**
- Consumes: `useStore` (Task 12), `getModules` (Task 13).
- Produces: componentes de layout; `ActivityRail` con un botón por módulo; `TabStrip` con pestaña **Chat** fija primero.

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/layout/layout.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "../modules/stubs";
import { ActivityRail } from "./ActivityRail";
import { TabStrip } from "./TabStrip";

describe("layout", () => {
  it("ActivityRail muestra un botón por módulo", () => {
    render(<ActivityRail />);
    expect(screen.getByRole("button", { name: "Terminal" })).toBeInTheDocument();
  });
  it("TabStrip tiene la pestaña Chat fija", () => {
    render(<TabStrip />);
    expect(screen.getByText("Chat")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- layout`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/layout/ActivityRail.tsx
import { useStore } from "../state/store";
import { getModules } from "../modules/registry";

export function ActivityRail() {
  const { activePanel, setActivePanel } = useStore();
  return (
    <nav style={{ width: 44, background: "var(--title-bg)", borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8, gap: 4 }}>
      {getModules().map((m) => {
        const Icon = m.icon, active = activePanel === m.id;
        return (
          <button key={m.id} aria-label={m.title} title={m.title} onClick={() => setActivePanel(m.id)}
            style={{ width: 32, height: 32, display: "grid", placeItems: "center", border: "none",
              borderRadius: 6, cursor: "pointer",
              background: active ? "var(--selected-bg)" : "transparent",
              color: active ? "var(--accent)" : "var(--text-muted)" }}>
            <Icon size={16} strokeWidth={2} />
          </button>
        );
      })}
    </nav>
  );
}
```

```tsx
// ui/src/layout/TabStrip.tsx
import { useStore } from "../state/store";

export function TabStrip() {
  const { openTabs, activeTabId, closeTab } = useStore();
  const tab = (id: string, label: string, closable: boolean) => {
    const active = activeTabId === id;
    return (
      <div key={id} style={{ padding: "6px 12px", fontSize: 12, display: "flex", gap: 6,
        color: active ? "var(--text-primary)" : "var(--text-muted)",
        borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent" }}>
        {label}{closable && <span onClick={() => closeTab(id)} style={{ cursor: "pointer" }}>×</span>}
      </div>
    );
  };
  return (
    <div style={{ display: "flex", background: "var(--title-bg)", borderBottom: "1px solid var(--border)" }}>
      {tab("chat", "Chat", false)}
      {openTabs.map((t) => tab(t.id, t.label, true))}
    </div>
  );
}
```

```tsx
// ui/src/layout/ContextPanel.tsx
import { useStore } from "../state/store";
import { getModules } from "../modules/registry";

export function ContextPanel() {
  const { activePanel } = useStore();
  const mod = getModules().find((m) => m.id === activePanel);
  const Panel = mod?.Panel;
  return (
    <aside style={{ width: 264, background: "var(--panel-bg)", borderRight: "1px solid var(--border)", overflow: "auto" }}>
      {Panel ? <Panel /> : null}
    </aside>
  );
}
```

```tsx
// ui/src/layout/Sidebar.tsx
import { useStore } from "../state/store";

export function Sidebar() {
  const { repos } = useStore();
  return (
    <aside style={{ width: 272, background: "var(--panel-bg)", borderRight: "1px solid var(--border)", padding: 10 }}>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--text-muted)", marginBottom: 6 }}>Repos</div>
      {repos.map((r) => (
        <div key={r.id} style={{ display: "flex", justifyContent: "space-between", padding: "4px 6px", borderRadius: 6 }}>
          <span>{r.name}</span>
          <span className="mono" style={{ color: "var(--accent)", fontSize: 11 }}>{r.branch}</span>
        </div>
      ))}
    </aside>
  );
}
```

```tsx
// ui/src/layout/MainPanel.tsx
import { TabStrip } from "./TabStrip";
import { useStore } from "../state/store";

export function MainPanel() {
  const { activeTabId } = useStore();
  return (
    <main style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--app-bg)" }}>
      <TabStrip />
      <div style={{ flex: 1, padding: 16, color: "var(--text-secondary)" }}>
        {activeTabId === "chat" ? "Chat (R3)" : `Tab: ${activeTabId}`}
      </div>
    </main>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- layout`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/layout
git commit -m "feat(ui): 3-region layout shell (1a)"
```

---

## Task 15: `App` — composición + esqueleto que camina

**Files:**
- Create: `ui/src/App.tsx`, `ui/src/App.test.tsx`

**Interfaces:**
- Consumes: `Sidebar`, `ActivityRail`, `ContextPanel`, `MainPanel`, `useStore`, `getRepos`, `applyTheme`, `import "../modules/stubs"`.
- Produces: `App` que al montar aplica el theme, hace `getRepos()` y llena el store → `Sidebar` renderiza los repos.

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/App.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("./transport/rest", () => ({
  getRepos: vi.fn().mockResolvedValue([{ id: "repo-a", name: "repo-a", branch: "main" }]),
}));

import App from "./App";
import { useStore } from "./state/store";

describe("App walking skeleton", () => {
  beforeEach(() => useStore.setState({ repos: [] }));
  it("hidrata repos desde el backend y los muestra en el sidebar", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("repo-a")).toBeInTheDocument());
    expect(screen.getByText("main")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- App`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/App.tsx
import { useEffect } from "react";
import "./modules/stubs";
import { applyTheme } from "./theme/tokens";
import { getRepos } from "./transport/rest";
import { useStore } from "./state/store";
import { ActivityRail } from "./layout/ActivityRail";
import { ContextPanel } from "./layout/ContextPanel";
import { Sidebar } from "./layout/Sidebar";
import { MainPanel } from "./layout/MainPanel";

export default function App() {
  const setRepos = useStore((s) => s.setRepos);
  useEffect(() => {
    applyTheme(document.documentElement);
    getRepos().then(setRepos).catch(() => setRepos([]));
  }, [setRepos]);
  return (
    <div style={{ display: "flex", height: "100%" }}>
      <Sidebar />
      <ActivityRail />
      <ContextPanel />
      <MainPanel />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- App` then `cd ui && npm test`
Expected: PASS (todo el frontend verde).

- [ ] **Step 5: Commit**

```bash
git add ui/src/App.tsx ui/src/App.test.tsx
git commit -m "feat(ui): App composition + walking skeleton (repos from backend)"
```

---

## Task 16: Verificación end-to-end (manual)

**Files:** ninguno (validación).

- [ ] **Step 1: Inicializar un workspace de prueba**

```bash
mkdir -p /tmp/ws-demo/repo-x && (cd /tmp/ws-demo/repo-x && git init -q -b main && git commit -q --allow-empty -m x)
cd server && uv run ide init --cwd /tmp/ws-demo
```
Expected: crea `/tmp/ws-demo/.ide/` con `config.toml`.

- [ ] **Step 2: Levantar backend apuntado al workspace**

```bash
cd server && uv run ide --cwd /tmp/ws-demo --no-browser
```
Expected: log "Workspace: /tmp/ws-demo → backend en http://127.0.0.1:8787". `curl localhost:8787/api/repos` lista `repo-x`.

- [ ] **Step 3: Levantar el frontend**

```bash
cd ui && npm run dev
```
Expected: en `localhost:5173` se ve el layout de 3 regiones con estética 1a; el sidebar lista `repo-x` con su branch `main`.

- [ ] **Step 4: Correr todas las suites**

```bash
cd server && uv run pytest -v && cd ../ui && npm test
```
Expected: todo verde.

- [ ] **Step 5: Commit (si hubo ajustes)**

```bash
git commit -am "chore: R0 end-to-end verified" || true
```

---

## Self-Review

**Spec coverage:**
- `ide` walk-up + `ide init` → Task 8. Backend FastAPI (config/bus/plugins/repos/health) → Tasks 3–7. Envelope WS → Task 5/7. Frontend shell 3 regiones + theming 1a → Tasks 9,10,14. Store → 12. Transport REST/WS → 11. Registro de módulos (6 slots) → 13. Pestaña Chat fija → 14. Esqueleto que camina (repos reales → sidebar) → 15. Tests back+front → en cada tarea. Extensibilidad demostrable (register de cada lado) → Task 6 (backend) + Task 13 (frontend). **Sin gaps.**
- Criterio "layout con estética 1a" cubierto por tokens (Task 10) aplicados en layout (Task 14) — la fidelidad fina al mockup se refina visualmente en la verificación (Task 16).

**Placeholder scan:** sin TBD/TODO; cada step trae código real y comando con expected. Los Panels stub dicen "próximamente" intencionalmente (son slots de R1–R6, no placeholders del plan).

**Type consistency:** `Repo {id,name,branch}` consistente entre backend (`workspace.discover_repos`), REST (`getRepos`), store (`setRepos`) y Sidebar. Envelope `{type,id,channel,payload}` idéntico en `bus.py` y `envelope.ts`/`ws.ts`. `PanelId` compartido entre store, registry y rail.

## Notas de ejecución

- Ejecutar en un **workspace de Conductor sobre `~/dev/ide`** (aislamiento), no desde el workspace de finnecto-ide.
- Requisitos: `uv`, Node 18+. Los tests de git usan `git` del sistema.
