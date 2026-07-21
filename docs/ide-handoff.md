# Guía para agentes — cómo operar y hacer handoff al Agentic IDE

> Documento para que un agente (Claude Code u otro) entienda **qué es este IDE, cómo levantarlo,
> y cómo delegarle / retomar trabajo**. Es la referencia práctica de operación; para el estado del
> desarrollo interno ver `docs/superpowers/HANDOFF.md`.

## Qué es

Un **IDE agéntico que corre en el navegador (localhost)** para orquestar **sesiones paralelas de
Claude Code** sobre múltiples repos y git worktrees, cada una aislada. Backend **Python/FastAPI**
(WebSocket + API), frontend **React + Vite** — ambos servidos juntos por el comando `ide`.

Reglas base (no negociables):
- **Claude Code local, no Managed Agents.** Usa el binario `claude` con tu **login de suscripción**,
  **sin `ANTHROPIC_API_KEY`**.
- **Sin fallos silenciosos.** Todo error viaja como envelope `{type:"error", payload:{code,message}}`;
  el frontend muestra "desconectado", nunca datos viejos como vivos.
- **Extensibilidad.** Los módulos del rail (Search, Changed files, Graphite, Tasks, Terminal,
  Notion) son plugins detrás de una interfaz común: agregar uno = un `register` de cada lado.

## Cómo levantarlo

Requisitos: [`uv`](https://docs.astral.sh/uv/), Node + npm, y el binario `claude` en el PATH
(logueado).

```bash
# instalar global (un comando levanta todo)
cd server && uv run ide build     # buildea el frontend y lo empaqueta en el paquete
uv tool install ./server          # deja `ide` en el PATH con el frontend adentro
ide run --cwd /ruta/al/workspace  # sirve todo en http://127.0.0.1:8787 (o el siguiente libre)

# ver qué instancias corren
ide ls

# ayuda del CLI
ide help
```

- **`ide run`** auto-crea `.ide/` si falta, elige un puerto libre (arranca en :8787, sube si está
  ocupado — así podés correr **varios `ide` a la vez** en distintos proyectos), y abre el navegador
  a la URL real. `--port N` fuerza uno exacto; `--no-browser` no abre el navegador.
- Cada instancia se registra en `~/.ide/instances/<port>.json`; `ide ls` las lista y poda las muertas.
- **Desarrollo (hot-reload de la UI):** `uv run ide run --cwd <ws> --no-browser` + `cd ui && npm run
  dev` (Vite en :5173). El WebSocket del frontend se conecta same-origin en producción y a `:8787`
  en dev.

## El workspace y `.ide/`

La unidad de trabajo es un directorio con **`.ide/`** (se detecta por walk-up; `ide run`/`ide init`
lo crean). Es **local, no se commitea**. Contenido:

| Archivo/dir | Qué es |
|---|---|
| `.ide/config.toml` | Config del workspace (nombre, roles). |
| `.ide/sessions.json` | Árbol de sesiones (ver abajo). |
| `.ide/tasks/` | Tareas markdown (`.md`). |
| `.ide/worktrees/<slug>/` | Worktrees de las sesiones de trabajo. |
| `.ide/notion.json` | Lista curada de páginas de Notion. |

Config y estado **global** del usuario (en `~/.ide/`, no en el workspace): `~/.ide/config.toml`
(p.ej. el token de integración de Notion) y `~/.ide/instances/<port>.json` (instancias `ide`
corriendo, compartidas entre todos los workspaces).

## Sesiones (el modelo central)

Cada sesión es una **conversación con Claude Code** con su propio contexto. Forman un **árbol**
(`parentId`, `children[]`). Dos tipos:

- **Coordinadora** — sin branch ni worktree (`worktreePath: null`). Su rol es comandar hijas.
- **De trabajo** — con worktree + branch propios. `access: "rw"` (worktree exclusivo) o `"ro"`
  (worktree `--detach`, repetible). Corren en su directorio aislado.

Se crean desde la UI (o la capability `sessions.create`). El **repo principal no es una sesión**
(se monitorea). Si la branch pedida está ocupada, se ofrece una nueva (nunca falla crudo).

Los **roles** son presets funcionales (`{model, system_prompt, read_only, tools}`) en
`.ide/config.toml`, extensibles. Los **permisos** son por sesión (skip vs approve/deny inline),
con default desde el rol.

## Cómo un agente hace HANDOFF de trabajo (orquestación)

Esta es la parte clave para delegar. Una **sesión coordinadora** (su Claude Code) recibe un
**MCP server `orq` in-process** con estas herramientas — así el agente coordinador reparte y recoge
trabajo **por sí mismo**:

| Tool | Qué hace |
|---|---|
| `list_children()` | Lista las sesiones hijas de la coordinadora (id, nombre, estado, repo). |
| `ask_session(session_id, task)` | Le manda una tarea a una hija y **espera su respuesta final** (request-reply bloqueante). Devuelve el texto de la hija. |
| `ask_sessions({requests: [{session_id, task}, …]})` | **Fan-out**: manda tareas a varias hijas en paralelo y espera todas. |
| `spawn_session(repo, name, role?, branch?)` | Crea una hija nueva (worktree + branch + rol) bajo la coordinadora y la deja lista. |

Detalles:
- La coordinadora se detecta por `worktreePath is None`. El server `orq` se monta solo en ellas.
- Las hijas comandadas/spawneadas corren **permisivas** (bypassPermissions) — no piden aprobación.
- Cada `ask` emite mensajes **relay** que se ven como conversación en **ambos** chats (la
  coordinadora ve "→ hija" y "← hija: respuesta"; la hija ve "↳ de coordinadora").
- Los nombres de tool que ve Claude Code son `mcp__orq__list_children`, `mcp__orq__ask_session`, etc.

**Flujo típico de handoff:** desde una coordinadora → `list_children` (o `spawn_session` para armar
el equipo) → `ask_session`/`ask_sessions` para repartir el trabajo → razonar con las respuestas.

## Tareas (`.ide/tasks/`)

Cada tarea es un `.md` en `.ide/tasks/`. Convención: **título** = primer `# H1`; **status** = línea
`status: <x>`. Capability:

| Canal | Payload → resultado |
|---|---|
| `tasks.list` | `{}` → `{tasks:[{id,title,status}]}` |
| `tasks.read` | `{id}` → `{id,title,status,markdown}` |
| `tasks.save` | `{id, markdown}` → `{id,title,status}` |
| `tasks.create` | `{name}` → `{task:{id,title,status}}` |

Sirven para dejar/registrar ítems de trabajo que persisten en el workspace.

## Otros módulos del rail

- **Notion** — lista curada de páginas por URL, editables (agregar/borrar bloques, título, checkbox)
  contra la API oficial. Token en `~/.ide/config.toml [notion].token` o el panel "Conectar Notion".
- **Graphite** — stack de branches del repo de la sesión activa (branch → commits → archivos →
  diff), con restack.
- **Changed files + diff** — archivos cambiados de una sesión y su diff.
- **Terminal** — PTY por sesión (xterm.js sobre WebSocket).
- **Chat** — la conversación con Claude Code de la sesión (default del panel principal).

## Protocolo (API / WebSocket)

- **WebSocket `/ws`**: mensajes JSON. Request: `{type:"req", id, channel, payload}` → response
  `{type:"res", id, payload}` o `{type:"error", id, payload:{code,message}}`. Los eventos (streams
  de chat, PTY) llegan como `{type:"event", channel:"chat.event.<sessionId>", payload}`.
- **Capabilities** (canales): `repos.*`, `sessions.*`, `terminals.*`, `chat.*`, `customizations.*`,
  `changes.*`, `graphite.*`, `notion.*`, `tasks.*`. Cada una es un plugin registrado en `app.py`.
- **HTTP**: `GET /health`, `GET /api/repos`, `GET /api/sessions`. El resto del frontend va por WS.

## Dónde seguir

- Estado del desarrollo y próximos pasos: `docs/superpowers/HANDOFF.md`.
- Specs y planes por rebanada: `docs/superpowers/specs/` y `docs/superpowers/plans/`.
- Instrucciones para trabajar en el repo: `CLAUDE.md`.
- Diseño/identidad visual: `docs/design/`.
