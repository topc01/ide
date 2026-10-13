# Sesiones-carpeta (simplificación del IDE) — Diseño

> Reestructura del núcleo. La sesión deja de ser un nodo de `.ide/sessions.json` y pasa a ser
> **una carpeta** `.ide/sessions/<id>/` donde corre un `claude` interactivo; una sesión puede
> **sumar varios repos** (worktrees). Una **sesión principal** despacha una sesión por ticket del
> backlog de Notion (y por PR a revisar). La UI se reduce a sidebar + terminal; el resto de los
> módulos queda oculto. Fecha: 2026-10-13.

## Objetivo

Flujo de trabajo diario:

1. Abro la **principal** y le pido "despachá". Lee mi backlog en Notion (y los PRs donde me
   pidieron review) y lanza **una sesión por ticket/PR**.
2. Cada sesión de ticket **analiza** su ticket: lee el mapa de repos (`sessions/CLAUDE.md`),
   determina scope, qué repos necesita (y se los agrega como worktrees), bloqueantes y dudas, y
   lo deja escrito en `TICKET.md` con un `status`.
3. En el sidebar veo todas las sesiones con su estado; entro a las que necesitan mi atención y
   decido cuáles implementar.

**Éxito:** un despacho de ~15 tickets termina sin sesiones trabadas en prompts de permiso, cada
sesión queda con su análisis en `TICKET.md`, y el sidebar refleja el disco en todo momento.

Fuera de alcance: chat propio (SDK) para estas sesiones (posible extensión futura), sqlite,
stack pesado por sesión (DB/docker) más allá de lo que hagan los scripts, escribir de vuelta a
Notion, publicar reviews en GitHub automáticamente.

## Decisiones cerradas (brainstorming 2026-10-13)

1. **Simplificar = núcleo nuevo + módulos ocultos.** Los módulos existentes (chat, graphite,
   search, archivos, tasks, notion, mlx/modelos, changes) **no se borran**: siguen registrados
   pero el rail solo muestra los de `config.toml [ui] modules` (default `["sessions",
   "terminal"]`). Se re-agregan editando esa lista.
2. **Una sesión = una carpeta + un proceso `claude` interactivo en un PTY** (cwd = la carpeta).
   No se usa el chat del SDK para estas sesiones. Retomar = `claude --continue` (Claude Code
   indexa conversaciones por directorio → una carpeta = una conversación recuperable).
3. **Enfoque 1: el disco es la fuente de verdad; los procesos pasan solo por el server.** Estado
   (carpetas, repos, `TICKET.md`/`REVIEW.md`, scripts) lo escribe cualquiera (CLI, Claude, yo) al
   disco; el server lo **vigila** y empuja el árbol a la UI. Arrancar/parar `claude` lo hace
   **únicamente** el server (dueño único de procesos).
4. **Canal agente → IDE = subcomandos del CLI `ide`**, que Claude invoca por Bash (documentados
   en `sessions/CLAUDE.md`). Reemplaza al MCP in-process `orq` para este flujo (`orq` queda,
   oculto con el chat).
5. **`<id>` libre:** `--id` si se pasa (típicamente el id del ticket), si no uno al azar corto
   (`s-7f3k2`). Slug validado, único (choque = error claro). La principal usa id al azar.
6. **Estado de cada sesión en un archivo de convención** (`TICKET.md` / `REVIEW.md`) con
   frontmatter `status`; el sidebar lo muestra como badge.
7. **Permisos por perfil**, por sesión: `--permissions analyze|full|default`; default global en
   `config.toml [sessions] default_permissions` (sembrado `"analyze"`; cambiarlo a `"full"` es una
   línea). Perfiles = archivos de settings de Claude Code en `.ide/permissions/`.
8. **Concurrencia:** `config.toml [sessions] max_running`; por encima del tope la sesión se crea
   en estado **`queued`** y el server la lanza al liberarse un lugar.
9. **Scripts por repo estilo Conductor**, en `.ide/scripts/<repo>/`, **un ejecutable por script,
   el nombre del archivo es el nombre**. Reservados: `setup` (tras agregar el repo) y `archive`
   (antes de quitarlo). Sin declaración en TOML.
10. **Sesiones de revisión de PRs** (`kind = "review"`): mismo modelo, otra plantilla, worktree
    **detached** en el head del PR, estado en `REVIEW.md`; bloque propio en el sidebar debajo de
    las sesiones. Las crea la principal (vía `gh search prs --review-requested=@me`, en su
    plantilla editable) y/o yo a mano.
11. **Agrupación del sidebar opcional**: botón arriba a la derecha; `Sin agrupar` (default) o
    `Por estado` (secciones con el componente **AI Elements `Queue`**, tematizado 1a). Registro
    de agrupadores extensible.
12. **Descartado:** eve.dev (runtime de agentes TS con API keys; compite con Claude Code en vez
    de orquestarlo). Sin migración del modelo viejo: `sessions.json` y worktrees previos se
    ignoran (quedan en disco). Se elimina el modo **ro** para sesiones de trabajo (solo vuelve,
    implícito, en revisiones).

## Layout en disco

```
<workspace>/                          # dir con repos; detectado por walk-up de .ide/
├── repo-a/  repo-b/  …               # repos principales: no se tocan
└── .ide/
    ├── config.toml
    ├── permissions/
    │   ├── analyze.json              # settings de claude (permissions.allow/deny), editables
    │   └── full.json
    ├── scripts/
    │   └── <repo>/{setup,archive,run,…}   # ejecutables; nombre de archivo = nombre del script
    ├── worktrees/
    │   └── <session-id>/<repo>/      # worktrees reales (git worktree add)
    └── sessions/
        ├── CLAUDE.md                 # editable: mapa de repos + uso de `ide` + convenciones
        ├── templates/
        │   ├── main.md               # prompt inicial de la principal
        │   ├── ticket.md             # prompt por ticket ({{variables}})
        │   └── review.md             # prompt por PR
        └── <session-id>/             # una carpeta = una sesión = cwd de su `claude`
            ├── .session.toml         # kind, permissions, created, ports, (pr_url)
            ├── PROMPT.md             # instrucciones iniciales renderizadas
            ├── TICKET.md | REVIEW.md # estado + análisis (según kind; main no tiene)
            └── <repo> -> ../../worktrees/<session-id>/<repo>   # symlink relativo
```

- `ide init` crea la estructura y **siembra** `sessions/CLAUDE.md` (con los repos descubiertos),
  `templates/*.md` y `permissions/*.json` **solo si no existen** (nunca pisa ediciones).
- `kind ∈ {main, ticket, review}`. **Una sola `main`** por workspace.
- `.session.toml` ejemplo:
  ```toml
  kind = "ticket"
  permissions = "analyze"
  created = 2026-10-13T10:22:00
  [ports]
  repo-a = 8100        # base del bloque de 10 reservado para IDE_PORT
  ```

### `config.toml` (claves nuevas)
```toml
[sessions]
default_permissions = "analyze"   # analyze | full | default
max_running = 5                   # omitido = sin tope
claude_command = "claude"         # inyectable (tests usan un comando falso)

[ui]
modules = ["sessions", "terminal"]
```

### Perfiles de permisos
- `claude` se lanza con `--settings .ide/permissions/<perfil>.json` (los `.claude/settings.json`
  no se heredan por walk-up hacia carpetas no-git; **verificar en el spike**).
- `analyze` (semilla): lectura libre (`Read`, `Grep`, `Glob`, `Bash(git log:*)`,
  `Bash(git diff:*)`, `Bash(git show:*)`), `Bash(ide repo add:*)`, `Bash(ide script:*)`,
  `Bash(gh pr view:*)`, `Bash(gh pr diff:*)`, escribir `TICKET.md`/`REVIEW.md`, MCP de Notion
  (lectura). Todo lo demás pide permiso.
- `full`: además `--permission-mode bypassPermissions`.
- `default`: sin `--settings` (comportamiento normal de Claude Code).

### Convención `TICKET.md` / `REVIEW.md`
```markdown
---
status: analyzing
title: Exportar facturas
notion_url: https://www.notion.so/...
---
## Scope
...
## Repos
## Plan
## Bloqueantes
## Dudas
```
- Ticket: `queued`¹ · `analyzing` · `blocked` · `questions` · `ready` · `in-progress` · `done`.
- Review: `reviewing` · `commented` · `approved` · `changes-requested` · `stale`.
- ¹ `queued` lo deriva el server del estado del proceso; no se escribe en el archivo.
- El **CLI siembra** el frontmatter al crear la sesión (estado inicial determinístico); Claude
  solo lo transiciona. Status desconocido → se muestra tal cual con badge neutro (no se oculta).

## CLI

Resolución de sesión actual: env `IDE_SESSION_ID` (inyectada en cada PTY de sesión, junto con
`IDE_URL`) → `--session <id>` → walk-up del cwd hasta `.ide/sessions/<id>/`. Se usa la env
primero porque `os.getcwd()` devuelve la ruta **resuelta** del symlink.

| Comando | Qué hace | Server |
|---|---|---|
| `ide session new [--id X] [--main] [--title T] [--template t --var k=v …] [--prompt "…" \| --prompt-file f] [--permissions p]` | Crea la carpeta (`.session.toml`, `PROMPT.md`, `TICKET.md` sembrado si kind=ticket) y pide al server lanzarla (o encolarla). Imprime id y ruta. | **Sí** |
| `ide session new --review <pr-url>` | `id = pr-<repo>-<num>`; `gh pr view` → título/autor; worktree detached en el head del PR + `setup`; `REVIEW.md` sembrado; plantilla `review`. | **Sí** |
| `ide session ls [--json]` | Lista desde disco: id, kind, status, repos, proceso (si hay server; si no `?`). | No |
| `ide session open <id>` | Sin proceso vivo: `claude --continue`; sin historia: `claude` con `PROMPT.md`. Review `stale`: ofrece refrescar el head. | **Sí** |
| `ide session stop <id>` | Mata el proceso; carpeta y worktrees quedan. | **Sí** |
| `ide session rm <id> [--force]` | stop (si hay server) → `archive` por repo → `git worktree remove` → borra carpeta. Cambios sin commitear → se niega salvo `--force`. Branches se conservan. | No |
| `ide repo add <repo> [--branch b]` | Worktree en `.ide/worktrees/<id>/<repo>` (branch default `<id>`; ocupada → error que sugiere `--branch`), symlink, reserva `IDE_PORT`, corre `setup` (espera y streamea; exit≠0 → sale ≠0). | No |
| `ide repo rm <repo>` | `archive` → quita worktree + symlink + libera puerto. | No |
| `ide script <name> [<repo>]` | Corre el script en el worktree con env `IDE_*`; `<repo>` inferido si la sesión tiene uno solo. | No |

- Con `--template`, una `{{var}}` sin valor es **error** (no se manda un prompt con placeholders).
- `new` con id existente → error "ya existe `<id>`" (idempotencia del despacho). `--main` con una
  main existente → error que sugiere `ide session open <id>`.
- Sin server para `new/open/stop` → "No hay `ide run` activo para este workspace" y exit ≠ 0.

### Env de scripts
`IDE_SESSION_ID`, `IDE_REPO`, `IDE_ROOT_REPO` (repo principal), `IDE_WORKSPACE`, `IDE_PORT`
(base del bloque de 10 reservado por sesión+repo, persistido en `.session.toml`). cwd = worktree.

## Ciclo de vida del proceso

```
(nuevo) ──new──▶ queued ──slot libre──▶ running ──claude sale / stop──▶ stopped ──open──▶ running
                   └───────────── (sin tope: directo a running) ─────────────┘
```
- Los PTY son hijos del server: al reiniciar `ide run` todas quedan `stopped` (sin auto-resume).
- La cola es FIFO por `created`; `stop`/salida de un proceso libera slot y el supervisor lanza
  la siguiente. Las sesiones `queued` sobreviven a un reinicio como `stopped` (ver Abiertas).

## Componentes

### Server (`server/ide_server/`)
| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `sessions_fs.py` | **Puro**: `list_sessions(root)` → modelos desde `.session.toml` + frontmatter + symlinks; `create_session_dir`, `render_template`, `seed_workspace` (para `ide init`). | disco |
| `repos_fs.py` | `add_repo`/`rm_repo` (worktree + symlink + puertos), `add_pr_worktree` (detached). | `worktrees.py` |
| `scripts.py` | Descubrir scripts, validar `+x`, armar env, correr inline o en PTY. | disco |
| `supervisor.py` | **Dueño único** de procesos `claude`: spawn en PTY, estados, cola `max_running`, comando configurable. | `pty_manager.py` |
| `watcher.py` | `watchfiles` (ya viene con `uvicorn[standard]`) sobre `.ide/sessions/` y `.ide/scripts/` → debounce → re-lista completo → broadcast `sessions.tree`. | `sessions_fs` |
| `capabilities/folder_sessions.py` | WS (árbol, open/stop/rm/script desde la UI) + HTTP `/api/sessions/{new,open,stop}` para el CLI. | todos |
| `cli.py` | Subcomandos nuevos (argparse, como hoy). Disco → in-process; procesos → HTTP. | todos |

Se reemplazan `sessions_store.py` y `capabilities/sessions.py` (árbol viejo). `ide init` deja de
crear `tasks/` por defecto.

### UI (`ui/src/`)
- **Rail:** filtra el registry por `[ui] modules` (llega en el handshake de config).
- **Sidebar de sesiones** (módulo `sessions` reescrito):
  - Fila fija **★ principal** arriba (botón "Principal": abre o crea).
  - **Sesiones** (`ticket`): punto de proceso (● running / ○ stopped / ◌ queued) + id + título +
    badge de status; expandible a sus repos (branch, estado de `setup`, `⋯` con scripts).
  - **Revisiones** (`review`): bloque fijo debajo, con título del PR, `@autor`, badge.
  - Botón **agrupar** arriba a la derecha: `Sin agrupar` (default, por `created`) / `Por estado`
    (secciones: En curso · Necesitan tu atención (`blocked|questions|ready`) · En cola · Hechos
    (colapsado)). Registro `groupers: {id, label, groupOf(session)}`; preferencia en
    `localStorage` (try/catch). Aplica solo al bloque de sesiones, no a Revisiones.
  - Componente **AI Elements `Queue`** (vía registro shadcn) para las secciones, tematizado 1a.
  - `[+]` modal: id, template, variables, permisos. `[+ revisión]`: URL del PR.
  - Menú contextual: open / stop / rm (confirmación; muestra si hay cambios sin commitear).
- **Área principal:** tabs **por sesión**: `claude` (xterm del proceso; click con proceso parado
  → `open`), `TICKET.md`/`REVIEW.md` (markdown read-only, vivo), y uno por script lanzado.
  Reusa el módulo `terminal` (PTY ↔ WS ↔ xterm).

## Flujo de datos

```
CLI/Claude/yo ──escriben──▶ .ide/sessions/** , .ide/scripts/**
                                   │ watchfiles
                                   ▼
                     watcher → sessions_fs.list_sessions → WS sessions.tree → sidebar
CLI new/open/stop ──HTTP──▶ supervisor ──PTY──▶ claude (cwd=sessions/<id>, env IDE_*)
                                   └──estado de proceso──▶ WS sessions.tree
```

## Manejo de errores (sin fallos silenciosos)

| Situación | Comportamiento |
|---|---|
| `.session.toml` o frontmatter corrupto | La sesión aparece con badge `⚠ error` + mensaje; nunca se oculta. |
| Symlink roto (worktree borrado a mano) | Repo `missing`, acción "quitar". |
| Script sin `+x` | Warning en el `⋯` del repo con el `chmod +x` sugerido. |
| `setup` exit ≠ 0 | `ide repo add` sale ≠ 0 con el log; repo `setup failed`; reintento `ide script setup <repo>`. |
| `claude` no está / spawn falla | Envelope `{type:"error",payload:{code,message}}`; CLI imprime y sale ≠ 0. |
| CLI sin server (new/open/stop) | Mensaje explícito; exit ≠ 0. |
| `gh` ausente o PR inaccesible | `--review` falla con el error de `gh`; no crea carpeta a medias. |
| `{{var}}` sin valor | Error antes de crear nada. |
| WS caído | Sidebar "desconectado", no el árbol viejo como vivo. |

Las operaciones que crean varias cosas (carpeta + worktree + …) **limpian lo parcial** si fallan
antes de terminar (excepto `setup` fallido, que deja el worktree a propósito para reintentar).

## Testing (TDD)

- **Spike previo (tarea 0):** confirmar que `claude --settings <file>` aplica la allowlist desde
  una carpeta no-git; que `--continue` retoma por cwd; que `CLAUDE.md` de `sessions/` se hereda
  en `sessions/<id>/`; que el conector Notion de la cuenta está disponible en `claude` local.
  Ajustar el diseño si algo no se cumple.
- `sessions_fs`, `repos_fs`, `scripts`: pytest con `tmp_path` y **repos git reales** temporales
  (worktrees, symlinks, branch ocupada, detached, env `IDE_*`, bloques de puerto, `+x`).
- `supervisor`: cola/`max_running`/estados con `claude_command` falso (`sleep`/`echo`).
- `watcher`: escribir en disco → recibir `sessions.tree` (con debounce).
- CLI: invocar `main([...])` contra `tmp_path` + app de test (httpx) para los comandos con server.
- UI (vitest): sidebar sin agrupar / por estado, bloque Revisiones, badges, `⚠ error`,
  `missing`, "desconectado"; rail filtrado por `[ui] modules`.

## Orden de implementación (rebanadas dentro del plan)

1. Spike (tarea 0).
2. `sessions_fs` + `ide init` (siembra) + `ide session ls/rm`.
3. `supervisor` + HTTP + `ide session new/open/stop` + watcher + sidebar básico + tab `claude`.
4. `repos_fs` + `scripts` + `ide repo add/rm` + `ide script` + repos/`⋯` en el sidebar.
5. Plantillas + `--template` + `TICKET.md` sembrado + `max_running`/`queued`.
6. Rail filtrado por `[ui] modules`; agrupar + `Queue`.
7. Revisiones (`--review`, `REVIEW.md`, bloque del sidebar, `stale`).

## Abiertas (decidir en el plan, no bloquean)

- ¿Las `queued` al reiniciar el server se re-encolan solas o quedan `stopped`? (Diseño actual:
  `stopped`, coherente con "sin auto-resume".)
- Detección de `stale` en revisiones: ¿al abrir la sesión o por polling de `gh`? (Diseño actual:
  al abrir y en `ide session ls`.)
