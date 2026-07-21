# Spec — `ide` multi-instancia (puerto dinámico + descubrimiento)

> Fecha: 2026-07-20. Hoy el puerto está hardcodeado a `:8787` y el WS del frontend a
> `ws://localhost:8787/ws` → **no se pueden correr dos `ide` a la vez**. Esta rebanada: cada
> `ide run` toma un puerto libre, el frontend se conecta same-origin, y `ide ls` lista las
> instancias corriendo.

## Objetivo

Poder tener varios `ide` abiertos en distintos proyectos sin colisión: cada instancia en su
puerto, cada frontend conectado a **su** backend, y un comando para ver qué está corriendo.

## Decisiones tomadas (brainstorming 2026-07-20)

1. **Puerto: arranca en :8787, sube al siguiente libre si está ocupado** (`find_free_port`). El
   primer `ide` toma :8787 (predecible); los extras suben a :8788, :8789… `--port <n>` fuerza uno
   **exacto** (sin auto-bump). Se imprime y se abre la URL con el puerto real (arregla la deuda del
   URL hardcodeado).
2. **Frontend WS same-origin**: en prod (servido por el backend) el WS se deriva de
   `window.location` (`ws(s)://{host}/ws`, incluye el puerto real); en **dev** (Vite) sigue
   pegándole a `ws://localhost:8787/ws`.
3. **Descubrimiento (`ide ls`)**: cada instancia se registra en `~/.ide/instances/<port>.json`;
   `ide ls` lista las vivas (podando las muertas por pid).

## Arquitectura

### Backend

**`cli.py` — selección de puerto:**

- `find_free_port(host: str, start: int, limit: int = 100) -> int`: prueba a bindear
  `(host, start)`, `(host, start+1)`, … hasta encontrar uno libre; devuelve ese puerto. Si no hay
  libre en `[start, start+limit)`, `raise RuntimeError`.
- `main` (comando `run`): nuevo flag `--port` (int, opcional). `port = args.port if args.port is
  not None else find_free_port(host, settings.port)`. Se imprime y se abre `http://{host}:{port}`
  (host normalizado a `127.0.0.1`); se sirve en `port`.

**`instances.py` (nuevo) — registro de instancias corriendo:**

- Dir global: `home/.ide/instances/` (crear si falta). `home` default `Path.home()`.
- `register_instance(home, *, port, host, workspace, pid, now=...) -> Path`: escribe
  `home/.ide/instances/{port}.json` con `{"pid", "port", "host", "workspace", "url", "started"}`
  (`url = f"http://{host}:{port}"`, `started` ISO). Devuelve el path.
- `unregister_instance(path) -> None`: borra el archivo si existe (best-effort, no-op si falta).
- `_pid_alive(pid) -> bool`: `os.kill(pid, 0)` → `True`; `ProcessLookupError` → `False`;
  `PermissionError` → `True` (existe, no es nuestro).
- `list_instances(home) -> list[dict]`: por cada `*.json` en el dir, carga; si `_pid_alive(pid)`
  es `False`, **borra el archivo** (poda) y lo omite; si el json está corrupto, lo omite. Devuelve
  las vivas ordenadas por puerto. (Sin fallos silenciosos: un json corrupto no tumba el listado.)

**`cli.py` — wiring:**

- `run`: tras elegir `port`, `path = register_instance(Path.home(), port=port, host=host,
  workspace=str(root), pid=os.getpid())`; `try: serve(...)` … `finally: unregister_instance(path)`
  (se limpia al salir con Ctrl-C; si lo matan con SIGKILL, queda huérfano y lo poda `ide ls`).
- Nuevo comando `ls`: `for inst in list_instances(Path.home()): print(...)` — tabla con
  `puerto`, `url`, `workspace`, `pid`. Si no hay ninguna: "no hay instancias corriendo".

### Frontend

**`transport/ws.ts` (o un módulo nuevo) — `wsUrl` puro y testable:**

```ts
export function wsUrl(env: { DEV: boolean }, loc: { protocol: string; host: string }): string {
  if (env.DEV) return "ws://localhost:8787/ws";                    // dev: Vite en :5173 → backend :8787
  const proto = loc.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${loc.host}/ws`;                               // prod: mismo origen (puerto real)
}
```

**`transport/wsClient.ts`**: `getWs()` usa
`new WsClient(wsUrl(import.meta.env, window.location))` en vez de la URL hardcodeada.

## Flujo de datos

`ide run --cwd ~/proyecto-A` → `find_free_port(127.0.0.1, 8787)` → :8787 → registra
`~/.ide/instances/8787.json` → sirve + abre `http://127.0.0.1:8787`. El browser carga el frontend
de :8787; el WS se conecta a `ws://127.0.0.1:8787/ws` (same-origin). Segundo `ide run --cwd
~/proyecto-B` → :8787 ocupado → :8788 → registra `8788.json` → su frontend pega a
`ws://127.0.0.1:8788/ws`. `ide ls` → lista A(:8787) y B(:8788). Al cerrar A (Ctrl-C) → borra
`8787.json`.

## Manejo de errores

- Sin puerto libre en el rango → `RuntimeError` (mensaje claro), exit ≠ 0.
- `--port` ocupado → uvicorn falla al bindear y propaga (explícito = exacto; el usuario ve el
  error). Sin fallo silencioso.
- json de instancia corrupto → se omite del listado (no tumba `ide ls`).
- Instancia muerta (pid no vivo) → se poda al leer.

## Plan de tests (TDD)

**Backend:**
1. `find_free_port`: devuelve `start` si está libre; si ocupo `start` con un socket bindeado, sube
   al siguiente; sin ninguno libre en el rango → `RuntimeError`.
2. `instances`: `register_instance` escribe el json con los campos correctos; `list_instances` lo
   devuelve; una entrada con pid muerto (pid inexistente) se **poda** (no aparece + archivo
   borrado); json corrupto se omite; `unregister_instance` borra; `_pid_alive` (pid actual → True,
   pid bogus → False). (tmp como `home`.)
3. `main(["run","--cwd",tmp], serve, opener)`: abre/imprime la URL con el puerto elegido; registra
   una instancia (aparece en `list_instances`) y la **desregistra** al terminar (finally). Con
   `--port N` usa exactamente N. (serve inyectado no bloquea; `home` inyectable o monkeypatch de
   `Path.home`.)
4. `main(["ls"])`: lista las instancias registradas (sembrar una con `register_instance`).

**Frontend:**
5. `wsUrl`: prod (`DEV:false`) con `{protocol:"http:", host:"127.0.0.1:8788"}` →
   `ws://127.0.0.1:8788/ws`; con `https:` → `wss://…`; dev (`DEV:true`) → `ws://localhost:8787/ws`.

## Fuera de alcance (Fase 2+)

- `--host` configurable (sigue `127.0.0.1`).
- Que la UI muestre/cambie entre instancias (hoy `ide ls` es CLI).
- Que dev (Vite) apunte a un backend en puerto no-default.
- Cerrar/administrar instancias desde `ide` (solo listar).

## Fidelidad de UI

No aplica (backend/CLI + un cambio interno de transporte que no toca la UI visible).
