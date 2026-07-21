# `ide` multi-instancia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps
> usan checkbox (`- [ ]`).

**Goal:** Cada `ide run` toma un puerto libre (arranca en :8787, sube si está ocupado; `--port`
fuerza exacto); el frontend se conecta same-origin; `ide ls` lista las instancias corriendo.

**Architecture:** `find_free_port` en el CLI + `main` que usa el puerto real (URL/serve); módulo
`instances.py` que registra cada instancia en `~/.ide/instances/<port>.json` (+ `ide ls` que poda
las muertas); el frontend deriva la URL del WS de `window.location` (dev sigue en :8787).

**Tech Stack:** Python/FastAPI, React/TS/vitest.

## Global Constraints

- **Sin fallos silenciosos:** sin puerto libre → `RuntimeError`; `--port` ocupado → uvicorn
  propaga; json de instancia corrupto → se omite del listado (no lo tumba); instancia muerta → se
  poda al leer.
- **No romper lo actual:** `main` sin `--port` sigue arrancando (ahora en el primer puerto libre
  desde :8787). El comportamiento por default (un solo `ide`) toma :8787 como siempre.
- **Testabilidad:** `serve`/`opener` ya inyectables; `home` se monkeypatchea vía `Path.home` en
  los tests de instancias.
- **Commits atómicos, en español.** Un commit por tarea.

---

### Task 1: Selección de puerto (`find_free_port` + `--port` + URL real)

**Files:**
- Modify: `server/ide_server/cli.py`
- Test: `server/tests/test_cli.py`

**Interfaces:**
- Produces: `find_free_port(host: str, start: int, limit: int = 100) -> int`; `main` con flag
  `--port` que usa el puerto elegido en opener/print/serve.

- [ ] **Step 1: Tests que fallan**

Agregar a `server/tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL (`find_free_port` no existe / `--port` no es
  un arg / se sirve/abre :8787 fijo).

- [ ] **Step 3: Implementar**

En `server/ide_server/cli.py`: agregar el import `import socket` arriba, la función, el flag, y usar
el puerto real. Función (tras `resolve_web_dir`, por ejemplo):

```python
def find_free_port(host: str, start: int, limit: int = 100) -> int:
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no hay puerto libre en [{start}, {start + limit})")
```

En `main`: agregar el arg y reemplazar el bloque de serve. El `parser`:

```python
    parser.add_argument("command", nargs="?", default="run", choices=["run", "init", "build"])
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=None)
```

Reemplazar el final del bloque `run` (desde `if not args.no_browser:` hasta `return 0`) por:

```python
    host = settings.host
    port = args.port if args.port is not None else find_free_port(host, settings.port)
    url = f"http://{host}:{port}"
    if not args.no_browser:
        opener(url)
    print(f"Workspace: {root}  →  {url}")
    serve(create_app(root, web_dir), host, port)
    return 0
```

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd server && uv run pytest tests/test_cli.py -q` → PASS. Suite: `uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/cli.py server/tests/test_cli.py
git commit -m "feat(cli): find_free_port + --port; ide run usa y abre el puerto real"
```

---

### Task 2: Registro de instancias (`instances.py`) + `ide ls` + wiring

**Files:**
- Create: `server/ide_server/instances.py`
- Modify: `server/ide_server/cli.py`
- Test: `server/tests/test_instances.py` (nuevo), `server/tests/test_cli.py`

**Interfaces:**
- Consumes: `find_free_port` (Task 1).
- Produces: `register_instance(home, *, port, host, workspace, pid) -> Path`,
  `unregister_instance(path)`, `list_instances(home) -> list[dict]`, `_pid_alive(pid) -> bool`.
  `main` con comando `ls` y registro/desregistro alrededor de `serve`.

- [ ] **Step 1: Tests que fallan**

Crear `server/tests/test_instances.py`:

```python
import json, os
from ide_server import instances


def test_register_and_list(tmp_path):
    p = instances.register_instance(tmp_path, port=8787, host="127.0.0.1",
                                    workspace="/ws/a", pid=os.getpid())
    assert p == tmp_path / ".ide" / "instances" / "8787.json"
    data = json.loads(p.read_text())
    assert data["port"] == 8787 and data["workspace"] == "/ws/a" and data["url"] == "http://127.0.0.1:8787"
    listed = instances.list_instances(tmp_path)
    assert len(listed) == 1 and listed[0]["port"] == 8787


def test_list_prunes_dead_pid(tmp_path):
    instances.register_instance(tmp_path, port=9001, host="127.0.0.1", workspace="/ws/x", pid=2147480000)
    assert instances.list_instances(tmp_path) == []                       # pid muerto → podado
    assert not (tmp_path / ".ide" / "instances" / "9001.json").exists()   # archivo borrado


def test_list_skips_corrupt_json(tmp_path):
    d = tmp_path / ".ide" / "instances"; d.mkdir(parents=True)
    (d / "8787.json").write_text("{ no es json")
    assert instances.list_instances(tmp_path) == []                       # no tumba el listado


def test_unregister(tmp_path):
    p = instances.register_instance(tmp_path, port=8787, host="127.0.0.1", workspace="/ws", pid=os.getpid())
    instances.unregister_instance(p)
    assert not p.exists()
    instances.unregister_instance(p)   # idempotente


def test_pid_alive():
    assert instances._pid_alive(os.getpid()) is True
    assert instances._pid_alive(2147480000) is False
```

Agregar a `server/tests/test_cli.py`:

```python
def test_run_registers_and_unregisters_instance(tmp_path, monkeypatch):
    import ide_server.cli as cli
    from ide_server import instances
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    init_workspace(tmp_path)
    seen = {}
    def fake_serve(app, host, port):
        seen["during"] = instances.list_instances(tmp_path)   # registrada mientras sirve
    cli.main(["run", "--cwd", str(tmp_path), "--port", "8787"],
             serve=fake_serve, opener=lambda u: None)
    assert len(seen["during"]) == 1 and seen["during"][0]["port"] == 8787
    assert instances.list_instances(tmp_path) == []           # desregistrada al terminar (finally)


def test_ls_lists_running(tmp_path, monkeypatch, capsys):
    import ide_server.cli as cli
    from ide_server import instances
    import os
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    instances.register_instance(tmp_path, port=8788, host="127.0.0.1", workspace="/ws/b", pid=os.getpid())
    assert cli.main(["ls"]) == 0
    out = capsys.readouterr().out
    assert "http://127.0.0.1:8788" in out and "/ws/b" in out
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL (`No module named ...instances` / `ls` no es
  un choice).

- [ ] **Step 3: Implementar**

Crear `server/ide_server/instances.py`:

```python
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _instances_dir(home: Path) -> Path:
    d = home / ".ide" / "instances"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def register_instance(home: Path, *, port: int, host: str, workspace: str, pid: int) -> Path:
    path = _instances_dir(home) / f"{port}.json"
    path.write_text(json.dumps({
        "pid": pid, "port": port, "host": host, "workspace": workspace,
        "url": f"http://{host}:{port}", "started": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    return path


def unregister_instance(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def list_instances(home: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(_instances_dir(home).glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not _pid_alive(int(data.get("pid", -1))):
            p.unlink(missing_ok=True)
            continue
        out.append(data)
    out.sort(key=lambda d: d.get("port", 0))
    return out
```

En `server/ide_server/cli.py`: agregar `import os` y `from ide_server import instances`; agregar
`"ls"` a los choices del comando; agregar el handler `ls` (tras el bloque `build`):

```python
    if args.command == "ls":
        insts = instances.list_instances(Path.home())
        if not insts:
            print("no hay instancias corriendo")
            return 0
        for i in insts:
            print(f"  {i['url']}  {i['workspace']}  (pid {i['pid']})")
        return 0
```

Y envolver el serve con registro/desregistro (reemplazar el final del bloque `run` de Task 1):

```python
    host = settings.host
    port = args.port if args.port is not None else find_free_port(host, settings.port)
    url = f"http://{host}:{port}"
    inst_path = instances.register_instance(Path.home(), port=port, host=host,
                                            workspace=str(root), pid=os.getpid())
    if not args.no_browser:
        opener(url)
    print(f"Workspace: {root}  →  {url}")
    try:
        serve(create_app(root, web_dir), host, port)
    finally:
        instances.unregister_instance(inst_path)
    return 0
```

Actualizar el `choices`: `choices=["run", "init", "build", "ls"]`.

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd server && uv run pytest tests/test_instances.py tests/test_cli.py -q` → PASS.
Suite completa: `cd server && uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/instances.py server/ide_server/cli.py server/tests/test_instances.py server/tests/test_cli.py
git commit -m "feat(cli): registro de instancias en ~/.ide/instances + comando ide ls"
```

---

### Task 3: Frontend — WS same-origin (`wsUrl`)

**Files:**
- Modify: `ui/src/transport/wsClient.ts`
- Create: `ui/src/transport/wsUrl.ts`
- Test: `ui/src/transport/wsUrl.test.ts`

**Interfaces:**
- Produces: `wsUrl(env: { DEV: boolean }, loc: { protocol: string; host: string }) -> string`.

- [ ] **Step 1: Test que falla**

Crear `ui/src/transport/wsUrl.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { wsUrl } from "./wsUrl";

describe("wsUrl", () => {
  it("prod: mismo origen con el puerto real", () => {
    expect(wsUrl({ DEV: false }, { protocol: "http:", host: "127.0.0.1:8788" }))
      .toBe("ws://127.0.0.1:8788/ws");
  });
  it("prod https → wss", () => {
    expect(wsUrl({ DEV: false }, { protocol: "https:", host: "ide.example.com" }))
      .toBe("wss://ide.example.com/ws");
  });
  it("dev: backend en :8787", () => {
    expect(wsUrl({ DEV: true }, { protocol: "http:", host: "localhost:5173" }))
      .toBe("ws://localhost:8787/ws");
  });
});
```

- [ ] **Step 2: Correr, verificar que falla**

Run: `cd ui && npm test -- wsUrl` → FAIL (no existe).

- [ ] **Step 3: Implementar**

Crear `ui/src/transport/wsUrl.ts`:

```ts
export function wsUrl(env: { DEV: boolean }, loc: { protocol: string; host: string }): string {
  if (env.DEV) return "ws://localhost:8787/ws";                 // dev: Vite :5173 → backend :8787
  const proto = loc.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${loc.host}/ws`;                            // prod: mismo origen (puerto real)
}
```

En `ui/src/transport/wsClient.ts`, reemplazar la URL hardcodeada:

```ts
import { WsClient } from "./ws";
import { wsUrl } from "./wsUrl";

let client: WsClient | null = null;
export function getWs(): WsClient {
  if (!client) client = new WsClient(wsUrl(import.meta.env, window.location));
  return client;
}
```

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd ui && npm test -- wsUrl` → PASS. Suite completa: `cd ui && npm test` → PASS.
Tipos: `cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/wsUrl.ts ui/src/transport/wsClient.ts ui/src/transport/wsUrl.test.ts
git commit -m "feat(cli): frontend deriva la URL del WS del origen (same-origin), dev en :8787"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** puerto dinámico + `--port` (T1), instancias + `ide ls` (T2), WS
  same-origin + dev override (T3). ✓
- **Consistencia:** `find_free_port(host, start)` (T1) usado en `main` (T1) y envuelto con
  registro (T2); `instances.*(home=...)` con `Path.home()` en `main`, monkeypatcheado en tests;
  `wsUrl(env, loc)` (T3) ↔ `import.meta.env`/`window.location`. ✓
- **Riesgo señalado:** T1/T2 modifican el mismo bloque `run` de `main` (T2 reemplaza el de T1 y
  agrega el try/finally + registro) — el implementer de T2 debe integrar sobre lo de T1, no
  duplicar. `Path.home` monkeypatch en los tests de cli para no escribir en el `~/.ide/` real.
- **Verificación E2E manual (fuera del plan):** dos `ide run` en dos workspaces → puertos :8787 y
  :8788 sin colisión + `ide ls` los muestra — en vivo tras el merge.
```
