# `ide` — referencia completa (para humanos y agentes)

> Imprímela con `ide docs`. Este archivo es la fuente de verdad de cómo se configura y opera el
> IDE. Si eres un agente y te piden "configura el IDE", todo lo que puedes tocar está aquí.

## 1. Qué es

Un IDE en el navegador (localhost) que orquesta **sesiones paralelas de Claude Code**. Una
**sesión = una carpeta** `.ide/sessions/<id>/` donde corre un `claude` **interactivo** (en una
terminal manejada por el server). Una sesión puede sumar **varios repos** como git worktrees.
Usa el login de suscripción de `claude`; nunca `ANTHROPIC_API_KEY`.

Principio: **el disco es la fuente de verdad**. Todo estado (sesiones, repos, estado de tickets,
scripts, plantillas, permisos) son archivos que cualquiera puede leer/editar. El server los vigila
y refresca la UI solo. Solo los **procesos** (arrancar/parar `claude`) pasan por el server.

Requisitos de runtime: `claude` (logueado), `git`, `gh` (solo para revisiones de PR), `uv`.

## 2. Arrancar

```bash
ide init            # crea .ide/ en el directorio actual (lo hace solo `ide run` si falta)
ide run             # levanta server + UI en http://127.0.0.1:8787 (o el siguiente puerto libre)
ide run --no-browser --port 8790
ide run --no-supervise   # sin supervisor (no se relanza solo con versiones nuevas)
ide ls              # instancias corriendo (url, workspace, pid)
ide docs            # esta referencia
```

El **workspace** es el directorio que contiene `.ide/` y los repos (cada subdirectorio con `.git`
es un repo del workspace). `ide` lo encuentra subiendo desde el cwd hasta el primer `.ide/` (o por
la env `IDE_WORKSPACE`). **Ojo:** correrlo desde un directorio sin `.ide/` propio puede encontrar
uno viejo más arriba (ej. `~/.ide`).

**Auto-actualización:** `ide run` es un supervisor: corre el server como proceso hijo y lo relanza
en el mismo puerto si se cae o si se instala una versión nueva del IDE (`uv tool install
--reinstall`). El server vigila la huella de su código instalado; al cambiar avisa en la barra
inferior ("versión nueva: se reinicia cuando dejes de escribir", con **reiniciar ahora**) y se
reinicia cuando nadie tecleó en una terminal por 60 s. Las conversaciones de `claude` siguen vivas
en su daemon (se reenganchan al abrir la sesión); la pantalla de cada `claude` se guarda en
`.ide/terminals/claude-<sesión>.log` (cada 30 s y al cerrar) y al volver se muestra con una marca
de reinicio; la página espera a que el server vuelva y se recarga sola (recuerda el desarrollo
abierto). `ide run --no-supervise` corre sin supervisor (sin auto-actualización); `ide server`
tampoco usa supervisor.

Cambios en `config.toml` se leen **al arrancar el server** (reinicia `ide run`). Plantillas,
`sessions/CLAUDE.md`, scripts y perfiles de permisos se leen **en cada uso** (sin reiniciar).

## 3. Layout de `.ide/` (local, no se commitea)

```
<workspace>/
├── repo-a/  repo-b/ …                  # repos principales: el IDE no los modifica
└── .ide/
    ├── config.toml                     # §4
    ├── permissions/{analyze,main,full}.json   # §5 (settings de claude, editables)
    ├── archive/{sessions,worktrees}/<id>/  # sesiones archivadas (solo de ida)
    ├── ide.db                          # base local (SQLite): cache de GitHub, merges, ajustes (§9c)
    ├── prompts/*.md                    # §7b (prompts que la UI pega en el input de claude)
    ├── scripts/<repo>/<nombre>         # §8 (ejecutables; `.lib/` u otros con punto = helpers, no se listan)
    ├── runs/<lugar>/<repo>/<nombre>/   # §8b: log, meta.json, exit de cada servidor
    ├── worktrees/<id>/<repo>/          # worktrees reales (git worktree add)
    ├── worktrees/wt-<repo>-<n>/<repo>/ # §8b: worktree de una PR sin sesión (detach)
    └── sessions/
        ├── CLAUDE.md                   # mapa de repos + uso de `ide` + desarrollos/dependencias/servidores; lo heredan TODAS las sesiones
        ├── templates/{ticket,review}.md   # §7
        └── <id>/                       # una sesión
            ├── .session.toml           # kind, permissions, created, [ports], [setup], pr_url, reviewed_sha, claude_session, claude_name
            ├── PROMPT.md               # prompt inicial (plantilla renderizada)
            ├── SESSION.md   # estado + análisis (§9)
            └── <repo> -> ../../worktrees/<id>/<repo>   # symlink relativo
```

`ide init` **siembra** `sessions/CLAUDE.md`, `templates/*.md`, `prompts/tickets-y-prs.md`, `prompts/review-pr.md`, `prompts/rereview-pr.md`, `skills/backlog/SKILL.md`, `permissions/*.json` y
`config.toml` **solo si no existen**: nunca pisa ediciones. Para volver a la semilla, borra el
archivo y ejecuta `ide init`.

`claude` también hereda (por walk-up) cualquier `CLAUDE.md` en `<workspace>/` o más arriba.

## 4. `config.toml`

```toml
name = "mi-workspace"

[sessions]
default_permissions = "analyze"   # analyze | full | default — perfil cuando no se pasa --permissions
max_running = 5                   # tope de `claude` corriendo a la vez; omitido = sin tope; entero >= 1
claude_command = "claude"         # comando base (se le agregan flags); útil para wrappers

[reviews]
poll_interval = 300               # segundos entre polls de PRs con `gh`; 0 = desactivado
github_interval = 120             # segundos entre polls de revisiones en GitHub (sección Revisiones); 0 = off
# github_org = "MiOrg"            # org donde buscar; omitido = owners de los `origin` de los repos
# plugins = ["mi-plugin@mi-marketplace"]  # plugins de Claude Code habilitados solo en revisiones

[ui]
modules = ["sessions", "dev", "terminal", "prompts", "stack", "review", "deps", "servers", "db", "pins", "later", "evidence", "attachments", "explorer", "config"]   # módulos visibles en el menú de acciones; ver abajo
[ide]                     # opcional: la sesión "IDE", pestaña junto a la Manager
repo = "/Users/topc/ide"  # su claude corre en ese repo (permisos default, hooks por --settings)
resume = "<uuid>"         # la conversación de claude que retoma la primera vez (opcional)
[recursos]                # opcional: la sesión Recursos y el vigilante (valores por defecto)
idle_hours = 12           # un servidor del IDE sin uso (log ni claude) hace más de esto = abandonado
watch_seconds = 300       # cada cuánto mira el vigilante (0 = no vigila)
cpu_alert = 150           # % de CPU sostenido (dos miradas seguidas) que avisa con una notificación

# [mlx] …                         # modelos locales (opcional; panel Settings → Modelos)
```

Valores inválidos (`default_permissions` fuera de la lista, `max_running` < 1 o no entero) hacen
fallar el arranque con un mensaje que nombra la clave.

`[ui] modules`: ids disponibles `dev`, `terminal`, `prompts`, `stack`, `review`, `deps`, `servers`, `db`, `pins`, `attachments`, `explorer`, `config`, `files`, `search`, `changes`, `graphite`, `tasks`,
`notion`, y `chat`. Si `chat` **no** está, el área principal es la vista por sesión (terminal
`claude` + doc + scripts); si está, vuelve el chat propio.
La **sidebar interna** (el panel del módulo activo) se ensancha arrastrando su borde derecho (200–720 px); el
ancho queda guardado en el navegador (`ide.innerSidebarWidth` en localStorage) y doble click en el borde
vuelve al de siempre (256 px).

**Modo claro:** el botón al pie del menú de acciones rota entre oscuro (el de siempre, luna), claro (sol) y
sistema (pantalla: sigue al modo claro/oscuro del computador, también si cambia con el IDE abierto); queda guardado en el navegador (`ide.theme` en localStorage). Las terminales y los logs de servidores
cambian con él. `claude` pinta con sus propios colores: para que siga al fondo, en `claude` elige
`/theme` → "Auto (match terminal)" (o "Light"); toma el fondo al arrancar, así que las sesiones ya abiertas
se ajustan al reabrir `claude`.

## 5. Permisos

Cada sesión tiene un perfil (`.session.toml` → `permissions`), elegido con `--permissions` o
`[sessions] default_permissions`:

| Perfil | Cómo se lanza `claude` | Para qué |
|---|---|---|
| `analyze` | `--settings .ide/permissions/analyze.json` | leer y analizar; lo demás pide permiso en la terminal |
| (main + analyze) | `--settings .ide/permissions/main.json` | igual + `ide session new` (despachar) |
| `full` | `--settings full.json --permission-mode bypassPermissions` | corre sola, sin preguntar |
| `default` | sin `--settings` | comportamiento normal de Claude Code |

`analyze.json` (semilla) permite: `Read`, `Grep`, `Glob`; Bash de solo lectura (`ls`, `cat`,
`head`, `tail`, `wc`, `find`, `rg`, `grep`, `git log/diff/show/status/branch`, `git remote -v`);
`ide repo add`, `ide script`, `ide session ls`; `gh pr view/diff`, `gh search prs`;
`Edit(**/SESSION.md)`, `Edit(**/SESSION.md)` (crear incluido); MCP de Notion
(`notion-fetch`, `notion-search`, `notion-query-data-sources`). Niega `git diff/log --output`.
Las reglas de archivo se escriben como `Edit(...)`: Claude Code no evalúa `Write(...)`.

Todas las sesiones reciben `--add-dir=.ide/worktrees/<id>` (sus repos); la principal además
`--add-dir=.ide/sessions` (para leer los `SESSION.md` de todas).

**Restricción de seguridad (server):** cuando el pedido viene de una sesión (`IDE_SESSION_ID`
seteada), **cualquier sesión** puede crear sesiones (p.ej. para separar una línea paralela): la nueva
**hereda los permisos de la que la crea** (solo puede pedir esos mismos o `analyze`) y **nunca `full`**
(si el default es
`full`, se baja a `analyze`). `full` solo se lanza desde la UI o desde una terminal tuya.

Edita los `.json` para ajustar (formato de settings de Claude Code: `permissions.allow/deny`).

## 6. CLI

Dentro de una sesión, el CLI sabe en qué sesión está por `IDE_SESSION_ID` (la inyecta el server),
o subiendo desde el cwd hasta `.ide/sessions/<id>/` o `.ide/worktrees/<id>/`. Fuera, usa
`--session <id>`. Todos los ids se normalizan a slug (`FIN-123` → `fin-123`).

Los comandos marcados **[server]** necesitan `ide run` activo (lo encuentran por `IDE_URL` o por
`ide ls`); si no, fallan con "No hay `ide run` activo". El resto trabaja directo en disco.
Salida: código 0 = ok, 1 = error con `error: <mensaje>` en stderr (scripts: su propio exit code).

### `ide session new` [server]
Crea la carpeta y lanza `claude` en ella (o la encola si se llegó a `max_running`).

| Flag | Efecto |
|---|---|
| `--id X` | id explícito (se normaliza). Sin id: `--notion` lo deriva; si no, al azar `s-xxxxx` |
| `--notion <url>` | id = `n-<últimos 10 hex del page id>` y `notion_url` = la URL. Si el id ya es de otro ticket → `id_collision`. Deja el link del ticket en sus Adjuntos (`attachments/ticket-notion.url`) |
| `--main` | sesión principal (una sola por workspace; `main_exists` si ya hay) |
| `--template <nombre>` | renderiza `templates/<nombre>.md` como prompt (§7) |
| `--var k=v` (repetible) / `--vars-file f.json` / `--vars-file -` (stdin) | variables de la plantilla; JSON = objeto `{"k": "v"}`; `--var` pisa al archivo. Prefiere JSON para textos con comillas, `\|` o saltos de línea |
| `--prompt "…"` / `--prompt-file f` | prompt libre (sin plantilla) |
| `--title T` | título (si no, sale de la variable `title`) |
| `--permissions analyze\|full\|default` | perfil (§5) |
| `--review <pr-url>` | sesión de revisión: id `pr-<repo>-<n>`, worktree detached en el head del PR, `gh` requerido |
| `--if-missing` | si el id ya existe: no hace nada y sale 0 (imprime `existe`). Usalo siempre al despachar |
| `--dry-run` | valida todo y muestra id + prompt, sin crear ni lanzar |

Salida: `<id>\t<running|queued|existe>\t<ruta>`; con `--dry-run`: `<id>\tdry-run` + el prompt.

### Otros comandos de sesión
- `ide session ls [--json]`: sesiones desde disco (id, kind, status, proceso, título, repos, ⚠ error). El proceso sale `?` si no hay server.
- `ide session open <id>` [server]: si está parada, la lanza con `claude --continue` (retoma la conversación de esa carpeta) o con `PROMPT.md` si no hay historia.
- `ide session stop <id>` [server]: mata el proceso; carpeta y worktrees quedan.
- **Archivar** (botón de la card en la UI; canal `sessions.archive {id, force}`; solo de ida, sin
  CLI por ahora): para el proceso, corre `archive` de cada repo (si falla, se puede forzar), deja
  cada worktree en **detach** (la rama queda libre; los cambios sin commitear se conservan), borra
  los ignorados (`git clean -fdX`: `node_modules`, venvs…), mueve los worktrees a
  `.ide/archive/worktrees/<id>/<repo>` (`git worktree move`) y la carpeta a
  `.ide/archive/sessions/<id>`; libera `[ports]` y anota `[archived] at` + `branches` (rama de cada
  repo antes del detach) en `.session.toml`. La conversación de `claude` no se puede retomar ahí
  (Claude Code la guarda por path). Un id archivado no se puede reusar (`session_archived`).
- `ide session review-stack <url> [<url>…]`: lo mismo que "Revisar stack" de la UI (ver Revisiones):
  una sesión `stack-<repo>-<n>` que revisa esas PRs de un stack (tienen que estar pendientes de tu
  review); con **una sola URL** toma todas las pendientes de su stack. Archiva las sesiones de
  revisión individuales de esas PRs y lanza la nueva. Solo la sesión principal (manager) puede: va
  con su token (`IDE_MANAGER_TOKEN`, como `ide session send`); a mano, usa el botón de la UI.
  Imprime `<id>\t<creada|existe>\t<proceso>`. HTTP `POST /api/reviews/stack {urls, token}`.
- `ide session rm <id> [--force]`: si hay cambios sin commitear en algún repo, **se niega antes de tocar nada** (`--force` lo fuerza); si no: para el proceso, corre `archive` de cada repo, quita los worktrees y borra la carpeta. Las branches quedan.

### Repos y scripts
- `ide repo add <repo> [--branch b] [--session id]`: worktree en `.ide/worktrees/<id>/<repo>`, symlink en la sesión, reserva `IDE_PORT` y corre `setup` (espera y muestra la salida). Branch default = `IDE_DEV_BRANCH` (`<login>/d<n>-<nombre>`; sin número, `<id>`); si está ocupada → error que sugiere `--branch`. `setup` fallido → exit 1, el worktree queda marcado `setup failed` (reintenta con `ide script setup <repo>`).
- `ide repo rm <repo> [--force]`: misma regla de cambios sin commitear; corre `archive`; quita worktree y symlink.

### Rutear a un desarrollo (`ide session send`)
- `ide session send <id | #n> --prompt-file - | --prompt "…"`: encola un prompt a la sesión de un
  desarrollo (id de la sesión o su número `#8`). Si su `claude` corre, entra a su cola (lo toma al
  terminar el turno); si está parada, se lanza con él; en cola por `max_running` → `queued`. Solo la
  **principal**: lo prueba con `IDE_MANAGER_TOKEN`, que el IDE le pasa solo a su `claude` (vive en
  memoria, nuevo en cada arranque del server; sin archivo); sin él → `forbidden`. Es una barrera más,
  no aislamiento: una sesión que puede correr cualquier comando corre con tu usuario y llega a lo
  local; esa frontera la ponen los permisos de cada sesión. El texto va por stdin (no por la shell) y
  llega con el encabezado `[Mensaje de la sesión manager]` (nunca empieza con `!`, que claude
  correría como shell). No está en los permitidos automáticos de la principal: cada envío pide OK
  (contenido ajeno, como un ticket o una PR, podría intentar que mande cosas). Queda en el historial
  (`prompt`). Canal `sessions.send {id, text, token}`, HTTP `POST /api/sessions/{id}/send`.
- **Nueva conversación** (módulo Desarrollo, con confirmación): para la misma sesión (carpeta,
  worktrees, `SESSION.md`) cierra la conversación de claude y arranca una nueva con contexto limpio
  (la anterior queda en su transcript); a las de ticket/revisión les pide leer su `SESSION.md` y
  resumir dónde quedaron. Un desarrollo = una sesión; esto evita abrir otra cuando la conversación se
  alarga o se ensucia. Canal `sessions.fresh {id}`.
- **Sesión principal = manager** (en la UI se llama **Manager**; el id queda en el tooltip): `.ide/manager.md` (sembrado por `ide init`, editable) se copia como
  `CLAUDE.md` de su carpeta en cada lanzamiento: no implementa, coordina; mira `ide dev ls`, rutea
  con `ide session send` (pregunta si no está claro a qué desarrollo va) y ayuda a destrabar.

### Telegram ↔ sesión manager
- `ide telegram setup`: pide el token del bot (de @BotFather), lo guarda en el llavero de macOS
  (servicio `ide-telegram`) y da un código: mandarle `/start <código>` al bot vincula ese chat (10 min;
  el IDE tiene que estar corriendo). `ide telegram status`. Sin token o sin chat, no hace nada.
- El IDE lee el bot por long polling (nada expuesto a internet). Solo acepta mensajes privados del
  chat vinculado; los demás se ignoran. Cada mensaje se le encola a la principal como
  `[Mensaje de Telegram del usuario]`.
- `ide reply [texto | --prompt-file -]`: la principal le contesta al usuario (solo a ese chat).
- `ide session propose <id | #n> --prompt-file -`: la principal propone mandarle algo a una sesión; le
  llega al usuario con botones **Sí / No** y el IDE lo encola solo con el Sí de ese chat (la sesión no
  puede autoaprobarse). Ambos solo para la principal (token) y permitidos sin preguntar.
  Canales `telegram.reply`, `sessions.propose`, `telegram.status`; HTTP `POST /api/telegram/reply`,
  `POST /api/sessions/{id}/propose`.

### Traspaso desde Conductor (`ide handoff`)
- `ide handoff --from <worktree> [--notion <id|url>] [--status <estado>] [--title t] [--session id] --summary-file <f|->`:
  **mueve** el worktree entero (`git worktree move`; tiene que ser un worktree de un repo del
  workspace, no su checkout principal) a `.ide/worktrees/<sesión>/<repo>`: viajan los cambios sin
  commitear, `node_modules` y los `.env*` (en la api, con ellos su base y su proyecto docker). Lo
  recibe la sesión del mismo ticket de Notion si existe (queda fullstack), si no una de ticket nueva
  (título: `--title` o la primera línea `# …` del resumen). Al `SESSION.md` se agrega "Traspaso desde
  Conductor" (rama, de dónde vino, rutas de los transcripts de Claude de esa carpeta) + el resumen;
  `--status` fija el estado (si no, `analyzing`). **No lanza `claude`.** Se niega si hay procesos
  corriendo desde esa carpeta (`busy`; `--force` lo fuerza). No pasa por el server (anda con el IDE
  apagado); desde fuera del workspace, con `IDE_WORKSPACE=<workspace>`.
- `ide handoff --install-skill`: instala `~/.claude/skills/ide-handoff/SKILL.md`, la skill
  `/ide-handoff` para que una sesión de Conductor escriba el resumen y se traspase sola.
- `ide script <nombre> [<repo>]`: corre `.ide/scripts/<repo>/<nombre>` en el worktree (repo inferido si la sesión tiene uno solo). Devuelve el exit code del script.

## 7. Plantillas (`.ide/sessions/templates/*.md`)

Texto con `{{variable}}`. Una variable sin valor es **error** (`missing_vars`), nunca se manda
un placeholder literal. Siempre disponible: `{{id}}`. Con `--notion`: `{{notion_url}}`.

| Plantilla | Variables | Uso |
|---|---|---|
| `ticket.md` | `id`, `title`, `notion_url` | qué hace cada sesión de ticket (analizar, `ide repo add`, escribir `SESSION.md`) |
| `review.md` | `id`, `title`, `pr_url`, `author`, `repo` (las completa el IDE con `gh`) | qué hace cada revisión |

Puedes crear plantillas nuevas (`templates/x.md`) y usarlas con `--template x`. La principal
**no** usa plantilla: la ★ de la UI la crea sin prompt y arranca esperando al usuario.

## 7a. Skills del IDE (`.ide/skills/<nombre>/SKILL.md`)

Skills de Claude Code que el IDE instala en la **sesión principal**: en cada lanzamiento se
copian a su `.claude/skills/` (skills de proyecto del cwd de su `claude`). `ide init` siembra:

- **`/backlog`**: busca en Notion (DB Desarrollo, una sola consulta SQL: la cuota es de ~5) los
  tickets en `Backlog` donde estás en `Asignee` o en `Células` (ambos campos de personas), los
  prueba con `ide session new --dry-run`, muestra una tabla (sesión, ticket, prioridad, size, por
  qué es tuyo, si ya tiene sesión) y **espera tu OK**; después lanza `ide session new --if-missing
  --notion <url> --template ticket` por cada uno. Cada sesión hace su revisión preliminar
  (`SESSION.md`) y suma sus worktrees con `ide repo add`. No escribe en Notion. El perfil `main`
  permite las herramientas de Notion necesarias (MCP de claude.ai o del plugin); a la CLI solo le
  pasa el **id** del ticket (`--notion <32 hex>`, el IDE arma la URL): nada de texto de Notion pasa
  por la shell. El título lo escribe la sesión en `SESSION.md` al leer el ticket.

## 7b. Prompts (`.ide/prompts/*.md`)

Texto libre (sin `{{variables}}`), uno por archivo; el nombre del archivo (sin `.md`) es el ítem
del módulo **Prompts** (ícono en el menú de acciones; la lista aparece en la sidebar interna;
requiere `prompts` en `[ui] modules`). Al hacer click se **pega en el input** de
`claude` de la sesión abierta en el panel principal, **sin enviarlo**: el usuario lo revisa,
edita y manda con Enter. Deshabilitado si la sesión no está corriendo. Se releen al abrir el
módulo (editar el archivo no requiere reiniciar).

Excepción: `review-pr.md` sí usa `{{pr_url}}`, `{{title}}`, `{{author}}`, `{{repo}}`, `{{id}}`;
lo envía el botón de revisión (ver §9b), no se pega a mano.

`[reviews] plugins`: al lanzar una sesión de revisión el IDE escribe `enabledPlugins` en
`.ide/sessions/<id>/.claude/settings.json` (config de proyecto del cwd de su `claude`), así que
esos plugins se cargan solo en revisiones. Útil cuando los plugins están habilitados por repo y
la sesión, que corre fuera de los repos, no los ve. Aplica también a revisiones existentes la
próxima vez que se lanzan (las que ya corren hay que pararlas y abrirlas).

`ide init` siembra `tickets-y-prs.md`: el despacho de la principal. Edítalo con la base
(URL o `collection://…`), el filtro (asignado, estados que entran) y si debe pedir OK antes de
lanzar (recomendado: `--dry-run` + tabla + esperar OK, luego `--if-missing`).

## 8. Scripts por repo (`.ide/scripts/<repo>/<nombre>`)

Un archivo **ejecutable** (`chmod +x`, con shebang) por script; el nombre del archivo es el nombre
del script. Reservados: **`setup`** (corre solo tras `ide repo add`) y **`archive`** (antes de
quitar el worktree). Cualquier otro (`run`, `test`, …) se corre con `ide script` o desde el `⋯`
del repo en la UI (abre una terminal).

cwd = el worktree. Env: `IDE_SESSION_ID`, `IDE_DEV_INDEX`/`IDE_DEV_SLUG`/`IDE_DEV_BRANCH` (§9b, número del desarrollo), `IDE_REPO`, `IDE_ROOT_REPO` (repo principal: para
copiar `.env`, etc.), `IDE_WORKSPACE`, `IDE_PORT` (base de un bloque de 10 puertos reservado por
sesión+repo, desde 8100, persistido en `.session.toml`). stdin es `/dev/null`.

Ejemplo `setup`:
```sh
#!/bin/sh
set -e
cp "$IDE_ROOT_REPO/.env" .env 2>/dev/null || true
uv sync
```

Un script que **no** debe correr solo al agregar el repo (p.ej. un build pesado de docker) va con
otro nombre (`build`) y se corre a mano desde Servidores.

**Base alternativa** (`IDE_DB_PATH=<archivo>`): el IDE usa esa base en vez de `.ide/ide.db`. Sirve
para probar un cambio (sobre todo de reglas de estado) contra una copia sin tocar la real:
`cp .ide/ide.db /tmp/ide-copia.db && IDE_DB_PATH=/tmp/ide-copia.db ide run --port 8799 --no-browser
--no-supervise`. Dos IDEs con reglas distintas sobre la **misma** base se pisan (p.ej. una migración
de estados que va y vuelve). Con `IDE_DB_PATH` el IDE no se conecta a Telegram (si no, le roba los
mensajes al IDE real).

## 8b. Servidores y Archivos (UI)

**Servidores** (menú de acciones, id `servers`): un **bloque por stack de cada repo** del desarrollo
actual, más uno por repo de la sesión cuya rama no tiene PR. Un stack se levanta desde la rama de su
PR de más arriba (contiene a las de abajo), así que dos stacks del mismo repo pueden correr a la vez.
Cada bloque dice el repo, sus PRs (`#4890 → #4892`), la **rama** (`⎇`) y **dónde** se levanta:
**sesión** = el worktree de la sesión, si está en la rama de alguna PR del stack (donde trabaja
claude; nunca se le cambia la rama); **aparte** = un worktree propio `.ide/worktrees/wt-<repo>-<n>/
<repo>` en el head de la PR de más arriba; **se prepara al ▶** = todavía no existe: el primer ▶ lo
crea (como "Preparar", con su `setup`) y corre el script. Los worktrees aparte tienen "actualizar al
head" y "quitar worktree". Los **fronts** (repos con `point-api`: embed, admin) tienen un selector
**api**: por defecto la api del bloque de la PR de la que dependen (p.ej. admin#98 → api#4897), si no
la única api corriendo del desarrollo, o "la de su .env.local"; su ▶ run le pasa ese puerto
(`IDE_API_PORT`, el `run` llama a `point-api`). **Lo mismo por CLI** (`ide server`, para las
sesiones): `ls [--json]`, `start <bloque> <script> [--api <bloque> | --no-api]` (crea el worktree
aparte si hace falta; un front sin su api corriendo da error: levantarla primero o `--no-api`),
`stop <bloque> <script>`, `log <bloque> <script> [-n N]`; `--dev <#n|id>` para otro desarrollo (default:
el de la sesión). El bloque se nombra por una de sus PRs (`api#4897`) o por el repo: si el repo tiene varios bloques, el repo a
secas (`embed`) es el de la sesión sin PR, el mismo nombre que muestra `ls`.
La regla vive en `server_blocks.py` (la UI la replica en `servers/place.ts`). Canales
`servers.blocks|start|stop|log`; HTTP `GET /api/devs/{id}/servers`, `POST /api/devs/{id}/servers/start|stop|log`.
Cada bloque muestra sus scripts
(menos `archive`) con ▶/■, estado en palabras (● corriendo · ◌ parando · ✓ terminó · ✗ falló (exit N) ·
■ parado · ⚠ murió; en el tooltip cuándo empezó/terminó; también en la tab del log) y los
link `localhost:<puerto>` del propio servicio: lo que el script declara con `[ide] url: <url>`, si no la línea `Local:` de Vite, si no la primera URL local del log (no las que solo menciona, como la api a la que apunta un front). Si el script escribe `[ide] error: <motivo>` (p.ej. el `run` de la api cuando el host no llega a su puerto porque lo tiene otro proceso), el script se ve **error** con ese motivo en vez de sus links, en Servidores y en `ide server ls`. Click en uno abre su **log** en una
tab del panel principal (solo lectura; se reinicia en cada corrida; ▶/■ también desde ahí). Abajo,
lo que corre en **otros** desarrollos (con ■), cada uno con la **rama** que levantó. Cada corrida guarda
en `meta.json` la rama de su worktree al arrancar (`@<sha>` si estaba en detach); `runs.list` la trae
en `branch`, y `runs.start {place, repo, name, apiPort?}`.

Los servidores son **procesos aparte del IDE**: siguen corriendo si el server se reinicia o se
cierra la UI. Cada corrida vive en `.ide/runs/<lugar>/<repo>/<nombre>/` (`log`, `meta.json` con
pid, `exit` con el código). Corre en su propio grupo de procesos, cwd = el worktree, con el env de
§8 más `FORCE_COLOR=1`; stdin `/dev/null` (un script que pregunta no puede: pasa el valor por
archivo). Parar = SIGTERM al grupo y SIGKILL a los 15 s. "Murió" = ya no existe y no dejó código
(kill -9, reinicio de la máquina). El log termina con `[terminó: exit N]` o `[parado por el IDE]`; las
terminales del IDE (scripts del ⋯, `claude`) también escriben `[terminó: exit N]` al terminar. Archivar o borrar una sesión (o quitar un repo) **para sus
servidores** antes de correr `archive`.

**Base de datos** (módulo propio, id `db`): por cada worktree cuyo `.env` (o `.env.local`) nombra una base
(`POSTGRES_NAME`), **Abrir** levanta `pgweb` (`brew install pgweb`) y lo muestra en una tab: tablas,
filas, estructura y SQL (no es solo lectura: con SQL se puede editar). Solo bases locales: el host
tiene que ser `127.0.0.1`/`localhost`/`::1` o el de docker (`db`, `postgres`, `host.docker.internal`
→ 127.0.0.1); otro → `db_not_local` (un `.env.local` de una PR ajena no puede mandar tu clave a otro
servidor). pgweb escucha en 127.0.0.1, en un puerto libre y en su propio origen (otro puerto que el
IDE: lo que muestre no tiene acceso a la API del IDE), bajo un prefijo aleatorio (`/<token>/`) que
solo conoce la UI: sin el token responde 404. Los pgweb mueren con el server. Canales
`db.list {place}`, `db.open {place, repo}` (→ `{url, name}`).

**Evidencias** (módulo, id `evidence`): la guía de pruebas de un desarrollo con sesión, con capturas.
La sesión define los pasos con **`ide evidencias set [--label PR] [--file f|-]`** (markdown: cada
ítem de lista `1.`/`-`/`- [ ]` es un paso, las líneas siguientes su detalle; `📸` o `[captura]` = lleva
captura) o el usuario los edita en el módulo (lápiz: título, detalle, "lleva captura", ↑↓, borrar,
+ paso). El paso actual es el primero sin hacer: una captura pegada (click en el módulo y ⌘V),
arrastrada o subida (+ de cada paso, para uno en particular) se guarda en `attachments/` de la sesión
(`<fecha>-evidencia-<corrida>-paso<n>-<k>.png`), se suma al paso (puede tener varias), lo marca ✓ y
avanza; el checkbox marca/desmarca a mano. Varias **corridas** por sesión (chips arriba): + crea una
vacía, **Duplicar** copia los pasos sin capturas (p.ej. "PR" y después "Ticket"). **Copiar** deja el
markdown en el portapapeles (para Notion: cada captura va como `[captura: <nombre>]`; las imágenes se
arrastran desde Adjuntos). **Subir a
GitHub** (elige la PR del desarrollo, con confirmación) publica un comentario con los pasos y las
capturas (`gh pr comment --body-file - --attach <cada captura>`: gh sube cada imagen y reemplaza su
ruta en el texto; máx. 50). `ide evidencias ls [--json]` muestra las corridas con las rutas de las
capturas; la sesión adjunta capturas con `ide evidencias shot <n> <archivo…> [--label L]` (al paso n
de la última corrida o la de ese nombre; lo marca hecho) y marca un paso con `ide evidencias done <n>
[--undo]`. Archivo: `.ide/sessions/<id>/evidence/<corrida>.json`; canales `evidence.list|new|save|
duplicate|delete|shot|markdown|github`; HTTP `GET/POST /api/sessions/{id}/evidence`, `POST …/evidence/shot`, `POST …/evidence/save`.

**Para después** (módulo, id `later`): pendientes de los desarrollos que el usuario no puede resolver
ahora (p.ej. una pregunta que tiene que conversar con el equipo), para que no se pierdan. Los deja la
sesión con **`ide later add "<pregunta>" -m "<contexto>"`** (dentro de la sesión; `--session <id>`
afuera) o el usuario desde el módulo ("Agregar a" el desarrollo actual). El módulo lista los abiertos
de todos los desarrollos, agrupados por desarrollo (el actual primero), con de quién y hace cuánto;
arriba el total ("N pendientes · M de este desarrollo") y el ícono del módulo en el menú de acciones
lleva el número de pendientes abiertos (los módulos pueden mostrar un conteo así: `useBadge`).
**Responder** le manda la respuesta a la sesión (encolada o la lanza; encabezado `[Respuesta del
usuario a un pendiente que quedó para después]`) y lo cierra; en desarrollos sin sesión solo queda
anotada. **Resuelto** (✓) lo cierra sin mandarle nada a la sesión (se resolvió en el chat). ✕ lo
descarta. La sesión cierra los suyos con **`ide later done <id> [-m "cómo se resolvió"]`** (`ide later
ls --mine` los lista con su id). La card muestra "⏱ N" (click abre el módulo). La sesión sigue con lo que
pueda; si ya no puede avanzar pasa a `blocked -m "pendiente: …"`. La manager los ve con **`ide later
ls`** (`--all` incluye cerrados, `--json`) y en el material de la revisión nocturna (recuerda los de
más de 7 días). Base: `kv` `later:<id>` = `{id, key, text, context, actor, created, status
(open|answered|resolved|dismissed), answer, resolved}`; canales `later.add {key, text, context}`, `later.list
{all}`, `later.answer {id, answer}`, `later.resolve {id, note}`, `later.dismiss {id}`; HTTP `GET/POST /api/later`, `POST /api/later/{id}/resolve`;
`sessions.tree` trae `later` (los abiertos).

**Pines** (módulo, id `pins`): mensajes de claude guardados para usar después (p.ej. un texto para
mandar por un hilo), por desarrollo. Se pinea desde la tab `claude`: al pasar el mouse por una línea de
un mensaje de claude aparece 📌 y pinea el mensaje completo, sacado del transcript (texto limpio en
markdown, no lo que muestra la terminal); si la línea no se reconoce (tablas, bloques de código),
seleccionar texto muestra "📌 Pinear selección" (pinea el mensaje que lo contiene o, si no, la
selección). El módulo lista solo los pineados, con Copiar, ver todo y desfijar. Se guardan en la base (`kv` `pins:<clave>`).
Canales `session.messages {id, limit}`, `pins.list`, `pins.add {key, text, source}`,
`pins.remove {key, id}`; evento `pins.changed`.

**PR sin sesión** (y stacks del desarrollo que no están en el worktree de la sesión): el primer ▶ de
su bloque hace lo que antes era **Preparar**: crea `.ide/worktrees/wt-<repo>-<n>/<repo>` en
el head de la PR (`refs/pull/<n>/head`, en detach: no ocupa la rama, no choca con otro checkout ni
con una sesión que se cree después) y corre su `setup`. Después: **Actualizar al head** (si no
tiene cambios sin commitear) y **Quitar worktree** (para sus servidores, corre `archive` y lo
borra con sus `.env`). En un stack se usa la PR de más arriba.

**Archivos** (id `explorer`): árbol de cada worktree del desarrollo actual (sin `.git`) y accesos
directos a sus `.env*` (los que faltan de `.env`/`.env.local` aparecen punteados: se crean al
guardar). Click en un archivo lo abre en una tab con editor (resaltado para ts/js/py/json/md/yaml);
**Guardar** (o ⌘S) se habilita con cambios. El editor mira el archivo cada 2 s: si cambió en disco
(p.ej. un script reescribió el `.env`) y no tienes cambios, se recarga solo; si tienes cambios, avisa
y eliges **Recargar** (pierdes los tuyos) o **Sobrescribir** (los tuyos encima). Guardar nunca pisa
un cambio de disco sin preguntar (`changed_on_disk`). Confinado al worktree (rutas resueltas, symlinks incluidos),
máx. 2 MB, solo texto UTF-8.

## 9. Estado de sesiones

**Kinds:** `main` (principal, una), `ticket`, `review`. Cada sesión de ticket o revisión tiene su **`SESSION.md`** (estado en el frontmatter, análisis, plan y la sección `## Feedback` donde anota las correcciones del usuario; ver §9e). Las de antes (`TICKET.md`/`REVIEW.md`) se migran solas al leerlas: se renombran a `SESSION.md` y el nombre viejo queda como symlink. Estados de ticket: ver "Estado del desarrollo" (§9b).

**`SESSION.md` / `SESSION.md`:** frontmatter + cuerpo. El IDE siembra el frontmatter al crear;
la sesión solo cambia `status` y escribe el cuerpo.
```markdown
---
status: analyzing
title: Exportar facturas
notion_url: https://www.notion.so/...
---
## Scope … ## Repos … ## Plan … ## Bloqueantes … ## Dudas …
```
- Ticket: las fases y pausas del estado del desarrollo (`investigating` · `developing` · … · `blocked` · `paused`; ver "Estado del desarrollo"; los nombres viejos se migran).
- Review: `reviewing` · `commented` · `approved` · `changes-requested`.
- Derivados por el server (no se escriben): proceso `running` / `queued` / `stopped`;
  revisiones `stale` (el PR tiene commits nuevos; "Refrescar" en la UI) / `merged` / `closed`;
  `attention: "trust"` (ver §10).

## 9b. Revisiones de GitHub y barra de usage (UI)

**Revisiones** (sidebar principal): cada `github_interval` s el server hace un `gh api graphql`
(org-wide, no depende de la sesión abierta; al arrancar, mientras llega la primera consulta, muestra
lo de la última guardada en la base) y la UI muestra cards en dos grupos:
**Pendientes** (PRs abiertos de la org con review pedida a vos) y **Pedí cambios** (sus sesiones no se pueden archivar: siguen vivas hasta la próxima ronda; PRs abiertos donde tu
última review con veredicto es `CHANGES_REQUESTED`; las respuestas en hilos no la tapan y no te re-pidieron review). Si el PR ya tiene sesión
(`pr-<repo>-<n>`) la card es la sesión; si no, una card del PR. Las sesiones de revisión que no
están en esas dos listas van en **Aprobé** (PR abierta y tu última review es aprobación; si
GitHub no lo dice, `status: approved` de `SESSION.md`), **Cerradas** (PR mergeada o cerrada) u
**Otras** (el resto, p.ej. solo comentaste). Bajo el título, chips `@revisor N`: cuántos PRs abiertos de
la org tienen review pedida a cada **miembro de la org** (los pedidos a equipos y a gente de
afuera no cuentan; pagina hasta 1000 PRs, el tope de la búsqueda de GitHub; si se pasa, se marca
con `+`); el tuyo resaltado. El módulo Configuración (⚙ de Revisiones) elige qué miembros se ven (checkbox); se
guarda en la base (`.ide/ide.db`); sin selección se ven todos los que
tienen pendientes. La sección se colapsa desde su título; Pendientes / Pedí cambios / Otras son
grupos fijos; el número junto al título es el de **pendientes de tu review**, y el grupo **Cerradas**
tiene **archivar todas** (con confirmación: archiva las sesiones de revisión de PRs ya mergeadas o
cerradas). En las pendientes, el botón de revisión (hover) envía
`.ide/prompts/review-pr.md` (pega + Enter) a la sesión del PR: si no existe la crea (como
`--review <url>`, con ese prompt en vez de la plantilla `review`); si está parada la retoma con el
prompt; si está en cola falla con `queued`. En las pendientes y en "Pedí cambios", **Aprobar** (✓) y
**Pedir cambios** (hover) abren una ventana con el comentario (precargado con la sección "Review para
GitHub" de la sesión de revisión, editable; obligatorio para pedir cambios) y piden confirmar antes de
publicar (`gh pr review`, canal `review.submit`). **Revisar stack** (hover, en las pendientes de un
stack con 2 o más PRs que te pidieron revisar; con confirmación): una sola sesión de revisión
`stack-<repo>-<n de la de abajo>` para esas PRs, con el worktree en el head de la de arriba y el prompt
`.ide/prompts/review-stack.md` (`{{prs}}` = la lista de abajo hacia arriba): las revisa una por una,
cada una contra su base, deja por PR en SESSION.md `## <repo>#<n>` con `### Veredicto`, `### Hallazgos`
y `### Review para GitHub`, y al final pide OK para publicar todas. **Mover PRs entre revisiones:** en una PR suelta de
Revisiones, ⇄ (hover) "Mover a otra revisión…" la suma a una sesión de revisión (lo mismo que `ide dev link`);
en la card de una revisión de varias PRs, ⇄ lista sus PRs para sacar una (queda aparte) o moverla a otra
revisión. Las que vienen de otro repo van al final de la card. Las sesiones individuales de esas
PRs se archivan. Con la sesión creada, sus PRs se ven en **una sola card** (la de la sesión, con una
chip por PR de abajo hacia arriba; click en una chip abre esa PR); Aprobar / Pedir cambios de cada PR
usan el review de su sección. `.session.toml` guarda `stack_prs` (la sesión trae `stackPrs`);
canal `reviews.startStack {urls}` (también `ide session review-stack`). Errores de `gh` se ven como `⚠ github`.

**Mis PRs** (sidebar principal, bajo Revisiones): tus PRs abiertas de la org (del mismo poll),
agrupadas como el inbox de Graphite: **Devueltas** (`reviewDecision` = `CHANGES_REQUESTED` y sin reviews pedidas pendientes),
**Esperando revisores** (con reviews pedidas pendientes, aunque antes hayan pedido cambios), **Sin revisores**, **Draft** y
**Aprobadas** (`APPROVED`). Prioridad: draft > aprobada > esperando > devuelta > sin revisores (como Graphite).
Son cards sin sesión: click la selecciona como desarrollo (el módulo Stack muestra su stack);
se abre en GitHub solo con el botón de hover, igual que en Revisiones. Todas las cards
de PR (y las de sesión con PR) marcan el CI: ✓ pasó, ✗ falló, ◌ corriendo (y aparte ⚠ conflicto,
⇣ atrasada; ver "esquina superior derecha"); el título muestra el total y los grupos se
colapsan. Cada card muestra quién la revisa (chips: azul review pedida, verde aprobó, amarillo
pidió cambios; una review re-pedida cuenta como pedida). Si la PR es parte de un stack, la card
muestra su posición (`2/4`, 1 = la de abajo).

**Mergear** (hover en Mis PRs; solo PRs tuyas, fuera de draft, que son la de abajo de su stack o no
están en uno; **se puede armar antes de que la aprueben**: arma el **auto-merge de GitHub**
(`gh pr merge --auto --squash`), que mergea al pasar el CI y la aprobación aunque el IDE esté
apagado; si ya está lista, mergea directo. Si el repo no tiene habilitado el auto-merge en GitHub
(p.ej. finnecto-admin), lo hace el IDE: espera el CI y la aprobación y la mergea él. En stacks nativos el IDE espera CI y aprobación y la
mergea él (`merge-async`). La card dice "auto-merge armado" y su ✕ lo **desarma** (`gh pr merge
--disable-auto`, canal `reviews.mergeCancel {url}`); nunca PRs desde forks; el `origin` local del repo tiene que ser el mismo repo de
GitHub; deshabilitado si el CI falló; pide confirmación; canal `reviews.merge {url}`). No
bloquea: valida, cierra el diálogo y sigue en segundo plano; la card muestra el paso y se pinta
**ámbar** mergeando, **roja** con error (reintentar: `reviews.mergeRetry {url}`) y **morada**
mergeada (24 h, en el grupo **Merges** de Mis desarrollos cuando ya no está abierta; ahí se puede
**archivar**: sale de la lista, canal `reviews.mergeDismiss {url}`, no toca GitHub).
1. **Rebasea solo si hace falta**: si GitHub exige la rama al día con la base (`mergeStateStatus`
   `BEHIND`), hay conflicto (`DIRTY` / `CONFLICTING`) o la rama arrastra commits de una madre
   squasheada (abajo). Si no, se mergea tal cual: un rebase innecesario cambia los commits y vuelve a
   correr todo el CI. Cuando hace falta, en un worktree propio por repo
   (`.ide/worktrees/_merge/<repo>`, detached) rebasea la rama sobre `origin/<base>` y la empuja con
   `--force-with-lease` (si hay conflicto aborta: `conflict`). El trabajo guarda `rebased`.
   Si la rama arrastra commits de una PR madre que ya se mergeó con squash (estaba apilada y
   GitHub la re-apuntó a la base), busca el último commit que fue head de otra PR mergeada
   (`GET /repos/{o}/{r}/commits/{sha}/pulls`) y rebasea con `--onto` desde ahí: solo viajan los
   commits propios de la PR.
2. Fuera de stacks nativos: arma el auto-merge de GitHub (justo después de un push GitHub todavía
   calcula si es mergeable: reintenta unas veces) y el IDE vigila (cada 30 s) hasta que GitHub la
   mergea. En stacks nativos: el IDE espera a que el CI pase, la PR sea mergeable y esté aprobada, y
   pide `PUT /repos/{o}/{r}/pulls/{n}/merge-async` (squash), el único endpoint que GitHub acepta ahí.
   Si el CI falla o hay conflicto, error.
3. Ya mergeada: si la PR está en un **stack nativo** (trae `stack`), GitHub rebasea y re-apunta
   solo las de arriba. Si no, el IDE restackea las de arriba en orden: cada una `git rebase --onto
   <nueva madre> <sha viejo de la madre>` + push `--force-with-lease`; la de encima pasa a apuntar
   a la base (`gh pr edit --base`); después borra la rama mergeada. Solo se reescriben PRs tuyas y
   no de forks: las ajenas (y las que estén encima) quedan sin tocar, la card lo marca como error y
   la rama mergeada no se borra (GitHub cerraría las que la apuntan).
Los trabajos viven en la base `.ide/ide.db` (sobreviven reinicios; un rebase cortado por un reinicio
queda en error para reintentar). Errores: `not_bottom`, `not_approved`, `ci_failed`,
`merge_pending`, `conflict`, `merge_failed`, `unknown_pr`, `no_merge`.

**Dependencias entre PRs** (solo lectura): se leen de la sección `## Dependencias` de la
descripción de cada PR abierta (las casillas `[ ]`/`[x]` se ignoran). Referencias `owner/repo#N`,
`repo#N`, `#N` (hereda el último repo explícito de la línea; si no, el de la PR) o URLs de PR; en
"merge en orden: A → B → este PR → C" solo cuenta lo de antes de "este/esta PR"; una línea que dice
que otras "dependen de esta" (p.ej. "las PRs X e Y dependen de esta") no declara dependencias (son al
revés). `ide dev show` lista cada una como "⏸ espera a" (con ", vía X" si es indirecta) o "va junto
con" (dependencia mutua). **Declaradas en el IDE** (además de la descripción; las dos valen): `ide dep add <pr> <dep…>`
(PR como `repo#n` o URL), `ide dep rm <pr> <dep…> [--ignore]` (saca las agregadas en el IDE; con
`--ignore` el IDE ignora también una que está en la descripción, que sigue escrita en GitHub) e `ide
dep ls <pr> [--json]` (las directas con su origen: descripción / ide / ignorada). Las usan las
sesiones, la manager y el usuario. Se recalculan al momento (poll). Base: `kv` `deps:<url>` =
`{add, ignore}`; canales `dep.list {pr}`, `dep.add {pr, deps}`, `dep.rm {pr, deps, ignore}`; HTTP
`GET /api/deps?pr=…`, `POST /api/deps/add|rm`; quedan en el historial (`dep-add`, `dep-rm`). Se siguen las
dependencias de las dependencias (entre repos), y el estado de las ya mergeadas/cerradas se
consulta a GitHub. Si dos PRs se piden mutuamente, **van juntas** (⇄): se muestran pero no
cuentan como pendientes. Las cards (y el selector) muestran `⛓ N` ámbar si faltan N por mergear
o `⛓ ✓` verde; la cadena completa (✓ mergeada, ◌ abierta, ✗ cerrada, ⇄ juntas, "vía X" si es
indirecta) está en el módulo Revisión y en la vista de la PR. Al mergear con dependencias
pendientes el diálogo avisa y el botón pasa a **Mergear igual** (no bloquea). Fuera de esa
sección también se leen frases sueltas ("Depende de finnecto-api#4624", "depends on", "requiere el
PR", "requires", "blocked by", "bloqueada por"): solo las referencias después del verbo; "no
depende de …" se descarta.

**Stacks:** si GitHub tiene la PR en un **stack nativo**, el orden es el de GitHub pero posición
y tamaño se cuentan solo sobre las PRs **abiertas** (GitHub sigue contando las mergeadas: una PR
quedaba "4 de 4" con las 3 de abajo mergeadas y no se podía mergear).
Si no, se infieren: una PR está en un stack si su rama base es la rama (head) de otra PR
abierta del mismo repo; se calculan sobre todas las PRs abiertas de la org en cada poll. Si un
stack se ramifica, la posición sigue el orden en profundidad.

**Módulo Stack** (menú de acciones, id `stack`; antes "GitHub"): muestra el stack de la card de PR seleccionada
o, si no hay, las PRs de la sesión abierta (la PR
revisada, o las PRs cuyas ramas son las de los repos de la sesión), cada una con todo su stack
(arriba la de más arriba). Color por review: verde aprobada, azul en revisión (reviews pedidas
pendientes), amarillo pidieron cambios (y no re-pediste review), sin color sin review. Hover → abrir la PR. Cada ítem muestra título (truncado; completo con hover) y
`repo#número · autor`; las PRs del stack que no son tuyas ni te tienen como revisor van tachadas y
atenuadas. El título muestra el total; los grupos se colapsan.

**Módulo Revisión** (menú de acciones, id `review`): para las PRs del desarrollo actual (la PR
elegida, o las de las ramas de la sesión) muestra el estado (veredicto, CI con los checks que
fallaron y su log, conflicto, revisores), los **hilos en el código** (abiertos primero, con
`archivo:línea`; resueltos colapsados; desactualizados marcados) y la **conversación** (reviews
con veredicto o texto + comentarios generales, por fecha). Se pide a GitHub a demanda (canal
`reviews.discussion {url}`) al abrirlo y cada 60 s mientras está abierto (o con ↻). El texto se
muestra limpio (sin HTML ni imágenes), los largos recortados con "ver más".

**Módulo Stack** (id `stack`): los stacks de las PRs del desarrollo actual (abajo = la base), por repo. El stack es un árbol por la base real de cada PR: su **madre** es la PR cuya rama es su base, y las que comparten base son **hermanas** (no una cadena). Si se bifurca, la rama más larga (si empatan, la de número menor) sigue en la columna de su madre y cada hermana siguiente va un nivel más adentro, en escalera, con una línea a la izquierda. En un stack bifurcado no se muestran los números de posición. Bajo el título de cada PR va solo su `#número` (el repo ya está en la cabecera del stack; rama, autor y base en el tooltip). Una PR cuya base es la rama de una PR de un **stack nativo** de GitHub (p.ej. abierta con `gh pr create --base`, fuera del stack nativo) se suma a ese stack arriba de su madre: posición y tamaño son del conjunto (módulo Stack, Servidores, `ide server ls`, `ide dev ls`), y al mergear la de abajo GitHub mueve las nativas y el IDE restackea las sumadas cuando GitHub ya movió a su madre (espera hasta 10 min; si no, error en la card). "Quedó atrás" compara cada PR con su madre, y "Re-apilar" rebasea cada una sobre su madre (nunca sobre una hermana). `ide server ls` lo escribe igual: `api#4950 → {api#4971, api#4976}`.
Click en una PR despliega bajo su rama sus **archivos cambiados** contra su base (en un stack, la rama
de abajo: solo lo de esa PR; si la rama está en un worktree del IDE, incluye lo no commiteado y lo no
trackeado): letra del cambio, nombre, carpeta debajo y +/−. Click en un archivo abre su **diff** en una
tab (lado a lado o unificado, sin cambios colapsados) y queda destacado en la lista. Doble click en una
PR la abre en el panel principal (resumen + descripción). Cada stack es una card; los avisos aparecen
solo cuando hace falta: "#n quedó atrás de su madre → **Re-apilar**" (una rama no contiene el head
actual de su madre) y "develop avanzó N commits → **Poner al día con develop**" (canal
`stack.status {url}` → `{behindParent, baseAhead, base}`). El server guarda
los cambios 30 s y el módulo los precarga al abrirse (el fetch a GitHub es lo lento). Sale de git local: las refs se traen a `refs/ide/pr/<n>` y `refs/ide/base/<rama>`
del repo principal (no tocan sus ramas). Acciones: **Mergear** en la de abajo (tuya y aprobada; el
flujo de merge de siempre), **Restack** (cada PR sobre su madre) y **Actualizar desde <base>**
(también la de abajo sobre su base), solo en stacks enteros tuyos y con confirmación: rebase
`--onto` desde el primer commit propio de cada PR (no arrastra commits viejos de la madre) y push
`--force-with-lease`. Se niega si una de esas ramas está en un worktree con cambios sin commitear o
commits sin pushear (`uncommitted_changes`, `unpushed`); si estaba limpia, la deja en el head nuevo.
Canales `pr.files {url, fresh}`, `pr.fileDiff {url, path, oldPath}`, `stack.restack {url, updateBase}`.

**Tabs por desarrollo (panel principal):** cada desarrollo tiene su propia fila de tabs: `claude`
(la terminal de la sesión; si está parada se lanza al abrirla), `SESSION.md`, el
**resumen** de cada PR y las terminales de los scripts. Al cambiar de desarrollo cambia la fila y al
volver está como la dejaste (también tras recargar; las de scripts no, mueren con el server). La
primera vez, una sesión abre `claude` y una PR su resumen; click en una fila de PR abre/enfoca su
resumen. El `+` **crea**: una **terminal nueva** (shell en la carpeta de la sesión; varias); en una
PR tuya sin sesión, una **sesión en su rama** (ver abajo); en una PR de otro sin sesión su
**sesión de revisión** (se abre su `claude`); y **reabre** lo cerrado
(doc, resúmenes de las otras PRs del desarrollo). × cierra la tab sin parar nada. Sin límite de tabs.

**Pestañas Manager | IDE | Recursos** (arriba de la sidebar principal): las dos sesiones fijas, la elegida
destacada y con el punto de actividad (trabajando / te espera); a la derecha solo el **+** (nueva
sesión). La sesión **IDE** (kind `ide`, id `ide`) existe si `[ide] repo` está en config.toml: se crea
sola al arrancar el server (`.ide/sessions/ide/.session.toml` con `cwd`), su claude corre en ese repo
con los permisos de siempre (`default`), retoma la conversación de `[ide] resume` la primera vez, y
no cuenta como desarrollo (sin número, fuera de Mis desarrollos y de "te esperan").
La sesión **Recursos** (kind e id `recursos`, tercera pestaña) se crea sola al arrancar el server: un
claude que mira qué consume el computador con `ide procs` y corta **solo lo abandonado**
(`ide procs stop` se lo niega con lo que está en uso; eso te lo propone). Su `CLAUDE.md` y sus permisos
(`.claude/settings.json`: `ide procs`, `ps`, `docker ps/stats`, `pmset -g`…) se escriben si faltan.
Tampoco cuenta como desarrollo. Aparte, el **vigilante** del server (sin IA, cada `watch_seconds`)
manda una notificación de macOS cuando algo pasa `cpu_alert` % de CPU dos miradas seguidas o la
batería baja 10 puntos en media hora (a lo más una vez cada 2 h por culpable) y lo anota en
`.ide/sessions/recursos/alertas.log`; no corre en un IDE de prueba (`IDE_DB_PATH`).

**Tab `claude`**: va siempre primera y destacada (ícono, fondo de acento y el punto de actividad de
la sesión: trabajando / te espera, con la nota en el tooltip). **Terminales en memoria**: cada
terminal (claude o script) se crea una vez y queda viva aunque cambies de desarrollo (sigue
recibiendo la salida de fondo): volver a ella es instantáneo. Solo la primera apertura carga lo que
ya imprimió el proceso (replay, hasta 2 MB). Se guardan hasta 10; se liberan las que llevan más
tiempo sin abrirse, y al reconectar con el server se descartan las que no están a la vista (la
próxima apertura recarga).

**Adjuntar archivos a la conversación** (tab `claude`): arrastrar archivos encima, pegarlos con ⌘V
(p.ej. una captura) o el botón 📎. Se guardan en `attachments/` de la carpeta de la sesión (su
`claude` los lee sin pedir permiso; máx. 10 MB c/u) y, si `claude` corre, su ruta se pega en el input
como un paste de terminal (sin Enter): las imágenes entran como `[Image #n]`, igual que arrastrarlas a
una terminal. Canal `sessions.attach {id, name, data(base64), paste}` → `{path, pasted}`.
**Módulo Adjuntos** (id `attachments`): los adjuntos de la sesión del desarrollo, del más nuevo al más
viejo: click los abre en una tab (imagen o PDF en línea, texto legible, lo demás para descargar);
**links** (pegar una URL con ⌘V sobre el módulo o "link": se guardan como `<nombre>.url`, acceso directo estándar con `URL=…` que claude lee; click los abre en otra pestaña), renombrar (si el nombre nuevo no trae extensión, se mantiene la original), descargar, copiar la ruta, borrar (con confirmación) y subir más (sin pegarlos en la
conversación). Las sesiones saben (su `CLAUDE.md`) que `attachments/` es lo que el usuario comparte y
dejan ahí lo que generan para él. Se sirven por `GET /api/sessions/{id}/attachments/{nombre}[?download=1]`
(mismos chequeos de origen; el tipo sale de la extensión o, si no tiene, del contenido; lo que no es PDF/imagen se sirve como texto en sandbox). Canales
`attachments.list|rename|delete|link`. **Artefactos:** cada ~20 s el IDE revisa lo nuevo de los
transcripts de las sesiones y, si su claude publicó un artefacto (herramienta `Artifact`: "Published
<archivo> at https://claude.ai/…artifact/…"), guarda el link en sus Adjuntos como
`<fecha>-artefacto-<nombre>.url` (sin repetir links; también recoge los ya publicados).

**Sesión para una PR propia** (`+` de las tabs o **Crear sesión** en el resumen; canal
`sessions.newForPr {url}`): sesión de ticket `dev-<repo>-<n>` con el worktree en la rama de la PR
(en un stack, la de más arriba: contiene a todas). Trae la rama de `origin` y, si no existe local,
la crea siguiendo a `origin/<rama>` (no desde HEAD). Queda en el mismo desarrollo (sus PRs pasan a
la card de la sesión) y se lanza su `claude`. Si ya existe la devuelve; PR de fork → `fork_pr`;
cerrada → `pr_closed`; rama checkouteada en otro lado → `branch_occupied` (el mensaje dice en qué
worktree está, para cambiarla de rama ahí).

**Estado y revisores (resumen de la PR):** arriba, el estado de la PR en GitHub en una palabra (Draft,
Sin revisores, En revisión, Cambios pedidos, Aprobada) y el CI; los revisores con lo que hizo cada uno
(aprobó, pidió cambios, pendiente). En tus PRs: **+ revisor** (busca entre los miembros de la org y le
pide revisión), **×** en un revisor pendiente (lo saca) — `gh pr edit --add-reviewer/--remove-reviewer`,
canal `pr.reviewers {url, add, remove}` — y, si está en draft, **Mandar a revisión** (`gh pr ready`).

**Descripción de la PR (resumen):** el resumen de cada PR muestra su descripción, pedida fresca a
GitHub al abrirlo (canal `pr.body {url}` → `{body, state}`), **Renderizado** (markdown GFM: tablas,
checkboxes, links en otra pestaña) o **Crudo** (toggle a la derecha). En Crudo el markdown se edita
directo; en Renderizado las casillas se marcan con click. Los cambios quedan pendientes ("cambios sin
guardar", Renderizado muestra el borrador) hasta **Guardar**, que se habilita solo si hay cambios y
reemplaza la descripción en GitHub (canal `pr.bodySave {url, body}`, `gh pr edit --body-file -`) y
deja el evento `pr-body-edited` (actor `ide`) en el historial.

**Panel principal con una PR:** si el desarrollo es una PR sin sesión, el panel principal muestra
la PR (título, rama, stack, CI, revisores), el botón para abrirla en GitHub y, si te toca
revisarla, **Revisar** (crea su sesión de revisión con el prompt `review-pr`).

**Terminales:** el server guarda lo último que imprimió cada terminal (2 MB). Una terminal que se
abre en el navegador con el proceso ya corriendo arranca con eso (`terminal.replay`) y después solo
recibe lo nuevo (cada evento trae `end` = bytes impresos en total): se ve como estaba, sin
reimprimir ni quedar en blanco.

**Desarrollos y selector:** un *desarrollo* es una sesión o una PR sin sesión de las listas de
la sidebar. El desarrollo actual se muestra como card arriba del menú de acciones y la sidebar
interna (los empuja hacia abajo); click → lista de todos los desarrollos (Sesiones / Revisiones /
Mis PRs) con buscador para cambiar. En el módulo Stack, click en una PR del stack abre su
desarrollo (su sesión, o la PR si está en las listas).

## 9c. Base local (`.ide/ide.db`)

SQLite (stdlib). Guarda las PRs abiertas de la org (nodo GraphQL completo), las PRs ya
mergeadas/cerradas que se referencian como dependencia (no cambian más), los miembros de la org,
los trabajos de merge y los ajustes (revisores visibles, marcas del poll). **Las sesiones no viven
acá** (siguen en disco). Todo lo de GitHub es reconstruible: si la base se corrompe se renombra a
`ide.db.bak` y se arma de nuevo. La primera vez migra `merges.json` y `reviews.json` (quedan como
`.json.migrated`).

**Poll de GitHub** (cada `github_interval`): incremental (`updated:>=` último poll − 1 min, abiertas
y recién cerradas) + refresco por ID de lo dinámico (CI, conflicto, review: no cambian
`updatedAt`) de las PRs relevantes (tuyas, las que revisás, sus stacks y dependencias) +
resincronización completa cada 30 min y al arrancar. **Optimista**: lo que hace el IDE se refleja al
instante, sin esperar el poll: pedir (re)review deja la PR "esperando revisor" (punto azul; en Mis PRs
pasa al grupo correspondiente) y publicar Aprobar / Pedir cambios cambia tu review en la card; el
poll siguiente lo confirma o corrige. La resincronización saca de la base las PRs
que ya no vienen, **salvo que la respuesta de GitHub sea sospechosa**: vacía (con PRs guardadas:
nunca se acepta), a medias (el total no cuadra con lo que llegó) o que sacaría más del 30% de golpe
(y más de 10; se acepta si la siguiente trae lo mismo). En ese caso guarda lo que llegó, no borra
nada y reintenta en el próximo ciclo. Cada resincronización queda en el log del server con sus
números (nodos, issueCount, en caché, sacadas); las sospechosas además en el historial
(`resync-suspect`) y en la UI: **⚠ sync** junto al título de Mis desarrollos y Revisiones, con los
números en el tooltip, hasta que una salga bien (`kv` `last_sync`; `reviews.github` trae `sync`). Miembros de la org: una vez por día.

**Cards de la sidebar** (sesiones y PRs, mismo cascarón): arriba **repo y número** (`API #4581`,
en negrita; en Revisiones el autor como chip; ● ○ = `claude` corriendo/parado), después el título
y una línea de detalle (posición en el stack `◫ 2/4`, "⟳ commits
nuevos desde tu revisión", estado del merge; en Mis PRs, los revisores como chips con su estado:
✓ aprobó, ✗ pidió cambios, ◌ pendiente). Cada persona tiene siempre el mismo color de chip (también
en los chips de conteo de Revisiones). **Fondo** tenue = review: verde aprobada, amarillo cambios
pedidos, azul esperando revisor, morado mergeada (también mientras se mergea). En la **esquina
superior derecha**: **⏸ N** = N dependencias sin mergear (al pasar el mouse, cuáles) y la marca de
**CI**: ✓ verde pasó, ✗ roja falló (**con pulso** = falló un check pero otros siguen corriendo:
GitHub ya la da por fallida; solo en tus PRs y las que revisas, que se refrescan con el detalle de
cada check), ⟳ amarilla girando corriendo. Una PR en **draft** lleva un cuadrado gris con un punto: ahí los
tests no corren (quedan en "skipping"), solo los checks livianos (CI Gate, styleguide); el punto es rojo si
alguno de esos falló. Aparte del CI: **⚠** conflicto con la base (no se puede
mergear) y **⇣** atrasada respecto de su base (develop avanzó: aviso, no bloquea salvo que GitHub
exija la rama al día). La misma marca en filas de stack, selector, módulo Stack y resumen. Cuando una PR
tuya **pasa a conflicto** (p.ej. se squasheó la de abajo del stack, en el IDE o en GitHub), el IDE le
avisa a la sesión de su desarrollo (o se lo deja en Para después si está parada) y queda un evento
`conflict`; solo avisa, no rebasea. Mientras GitHub recalcula (`mergeable` UNKNOWN) no cuenta como cambio. El punto
de review de una PR aprobada con revisores pendientes dice en el tooltip "falta X". Las cards traen
`ci`, `ciRunning`, `conflict` y `behind`. El borde es siempre el normal. La seleccionada
lleva un contorno claro. Al pasar el mouse, el estado en palabras.

**Módulo Dependencias** (menú de acciones, id `deps`): para las PRs del desarrollo actual, de qué
dependen (cadena completa: ✓ mergeada, ◌ abierta, ✗ cerrada, ⇄ van juntas, "vía X" indirecta) y
qué PRs abiertas las declaran como dependencia.

**Mis desarrollos** (reemplaza a la lista de sesiones de ticket y a "Mis PRs"): una card por
desarrollo. **Un desarrollo con sesión tiene una sola línea por repo**: la rama de su worktree y lo
apilado sobre ella. Si una sesión abre una PR tuya con su prefijo (`<login>/d<n>-…`) en **otra** rama
de un repo que ya tiene (una línea paralela), el IDE la separa sola en un **desarrollo nuevo**: crea la
sesión (`d<n>-<rama>`, sin lanzar su claude), su worktree en la PR de más arriba de esa línea, le
asigna esas PRs (pegajosas; queda en el historial de los dos) y le deja un PROMPT.md y un SESSION.md con el
origen. Si la rama sigue tomada en un worktree extra de la sesión de origen, igual crea el desarrollo
con sus PRs (sin worktree), lo dice en su SESSION.md y le deja a la de origen un pendiente para
soltarla. La PR no recibe número propio antes que su desarrollo nuevo. Si
una PR de otro repo del desarrollo original depende de esa línea, queda un **pendiente** (Para
después) en el original para decidir si se va con ella ("si van juntas, que queden en el mismo
desarrollo"). Las PRs asignadas a mano con `ide dev link` no se tocan. Regla (spec 2026-10-16-desarrollos, P1), cada PR en un solo desarrollo: (1) la sesión de
ticket cuyos worktrees están en esa rama (los suyos o uno **extra** que armó aparte: con otro nombre en
su carpeta de worktrees, dentro de su carpeta o en el scratchpad de su claude; salvo que sea una línea
paralela), más el resto de su stack — **pegajoso**: el IDE recuerda
la PR en ese desarrollo (base, `kv` `devpr:<url>`) y sigue ahí aunque el worktree cambie de rama,
hasta que se mergea/cierra; "sacar de este desarrollo" (hover de su fila, o `ide dev unlink`) la deja
aparte y no vuelve por rama; "mover a otro desarrollo…" (hover de su fila, o `ide dev link`) la
asigna a otro: pisa lo que tuviera y queda pegajosa ahí (avisa si su rama no está en ningún worktree
del destino); (2) un stack tuyo sin sesión; (3) una PR suelta. **Precedencia**: asignación explícita
(`link`) > pegajosa > por rama > stack (el stack trae a sus compañeras, salvo las asignadas a otro
desarrollo o sacadas). Los movimientos quedan en el historial (`ide dev show`) del origen y del
destino (`pr-moved {from, to}`, `pr-unlinked`). Canales `dev.unlinkPr {id, url | prs}` y `dev.linkPr
{id, prs}` (PR como URL o `repo#n`); HTTP `POST /api/devs/{id}/link|unlink {prs, token}`;
`sessions.tree` trae `devPrs`. Las sesiones sin PR también son desarrollos (grupo "Sin PR"). La card es compacta:
título y una chip `REPO #n` por PR (punto = review; click = elegir esa PR). El detalle va en el
módulo **Desarrollo** (id `dev`): las PRs por repo y stack (punto de review, número, título, CI, ⏸,
y en hover Mergear en la de abajo de cada stack, abrir en GitHub y sacar del desarrollo) y los
worktrees de la sesión (repo, rama, setup, ⋯ con sus scripts). En la card solo queda un aviso si
falta un worktree o falló un setup.
**Título de toda card** (sesiones, PRs, stacks, también en Revisiones): el nombre del desarrollo puesto
en el IDE o, si no hay, el título de la PR / del ticket; debajo, chips con repo y número
(`EMBED #2552`; en un stack o fullstack, una chip por repo y los números en las filas).
**Fullstack** (una sesión con worktrees de varios repos): chips de cada PR (`API #4654` `EMBED #2553`);
en el módulo Desarrollo, agrupadas por repo y stack, cada repo/stack con su propio Mergear.
En una sesión con varias PRs el fondo lo da la peor review y la marca de CI el peor CI. Agrupa por
estado (Merges, Devueltas, Esperando revisores, Sin revisores, Draft, Aprobadas, Sin PR); con varias
PRs manda la **peor**: devuelta > sin revisores > esperando > draft > aprobada. También por repo o
sin agrupar (⚙). Los grupos sin nada van juntos en uno solo, **Vacíos** (cerrado); apenas tienen
un desarrollo vuelven a su lugar. Junto al nombre de cada grupo (en Mis desarrollos y Revisiones) va
cuántos claude te esperan (● naranjo) y cuántos trabajan (◐ celeste); el que está en 0 no se muestra. Los módulos Stack, Revisión y Dependencias muestran **todo** el desarrollo (aunque
se haya elegido una fila), con una cabecera por repo si es fullstack.

**Card:** el título usa todo el ancho; las marcas (⏸, CI) van en la esquina superior derecha y las
acciones aparecen en hover en una **columna a la derecha de la card**, pegada a ella, con el ícono y
el **nombre** de cada acción (no tapan el título; se quedan mientras el mouse esté en la card o en la
columna, con un margen mínimo para cruzar; al entrar a otra card, la columna de la anterior se
esconde al instante: solo hay una a la vez). Las
cards no tienen "parar claude" (se para desde la terminal). En Mis desarrollos, si un revisor pidió
cambios, **Pedir re-review** (↺, con confirmación) se lo vuelve a pedir a quienes pidieron cambios en
cada PR del desarrollo (`gh pr edit --add-reviewer`, canal `pr.reviewers`).
En un desarrollo **listo para revisión**, **Asignar revisor** (👤+ en las acciones de hover) pide
revisión a una o más personas de la org en las PRs tuyas que elijas: todas, las de un repo o una por una
(agrupadas por repo); a quien ya revisa una PR no se le vuelve a pedir en esa, y antes de pedir muestra
el detalle para confirmar. Funciona también con las PRs en draft.

**Nombre del desarrollo:** el lápiz (acciones de hover de la card, o junto al título en el módulo
Desarrollo) o doble click lo renombra **solo en el IDE** (no toca SESSION.md ni GitHub); vacío vuelve al original, que queda en el tooltip. Se guarda en
la base (`kv`, clave `devname:<s:sesión | st:stack | p:url>`); si una PR o stack con nombre pasa a
tener sesión, la sesión lo hereda. Lo muestran las cards, el selector de desarrollo (y su búsqueda) e
`ide dev ls`/`show` (campo `name`). Canal `dev.rename {key, name}`; `sessions.tree` trae `devNames`.

**Número del desarrollo:** cada desarrollo (sesiones, stacks, PRs sueltas y revisiones; no la
principal) tiene un índice correlativo que nunca se reutiliza (`#12`; base, `kv` `devidx:<clave>`,
asignado de forma atómica). Una PR/stack con número que pasa a tener sesión se lo hereda. Se ve en
las cards, el selector (y se busca por `#12`), el módulo Desarrollo e `ide dev ls`/`show`
(`index`). Lo reciben el `claude` de la sesión y sus scripts: `IDE_DEV_INDEX` (12), `IDE_DEV_SLUG`
(`d12_<nombre>`, ≤ 32, para bases y proyectos docker nuevos) e `IDE_DEV_BRANCH`
(`<login de GitHub>/d12-<nombre>`): es la rama por defecto de `ide repo add`. `sessions.tree` trae
`devIndex`.

**Estado del desarrollo** (uno solo, unificado con el de la PR; solo local): una **fase** y, encima,
una **pausa** opcional. Fases: `investigating` (investigando), `developing` (desarrollando),
`ready-for-review` (listo para revisión), `testing` (en testeo: PRs fuera de draft sin revisores),
`in-review`, `changes-requested`, `approved`, `merged` (y "mergeando" mientras el IDE mergea). Con
PRs fuera de draft la fase la da GitHub (la peor de sus PRs; mergeado si todas lo están). Una PR en draft
que ya tiene revisores pedidos o una revisión también cuenta (en revisión / cambios pedidos / aprobada):
en el equipo se revisa en draft y el CI corre después de aprobar; un draft sin revisores no. Cualquier
fase se puede poner a mano desde la UI: guarda la fase de GitHub de ese momento (`gh`) y gana hasta
que GitHub cambie (una review, un merge); "↺ usar la de GitHub" la suelta. Las que pone una sesión
con `ide status` no se fijan (manda GitHub). Sin nada puesto se deduce (draft = desarrollando); un
`investigating` puesto por la sesión queda viejo apenas hay una PR abierta (pasa a desarrollando,
salvo que el usuario lo haya fijado a mano).
Pausas (tapan la fase sin borrarla, con nota y desde cuándo): `blocked` (la nota dice por qué o de
quién), `paused`; `unblock` vuelve a la fase. ("esperando tu input" ya no es un estado del desarrollo:
es la **actividad** de la sesión, ver abajo; los `waiting-input` que quedaron puestos se ven hasta que
los cambies, y `ide status waiting-input` ya no hace nada: responde que no hace falta.) Las sesiones también pueden
cambiarlo encima de lo puesto a mano. Mientras el desarrollo está activo sus PRs van en draft (si la
fase puesta es activa y una PR salió de draft, la card dice "PR fuera de draft"). Se cambia con la
acción de hover 🚩 de la card (menú flotante **a la derecha de la card**: arriba el estado actual y de
dónde sale —lo dice GitHub, lo puso la sesión, lo pusiste tú, deducido— y desde cuándo; "¿En qué está
el trabajo?" con las tres fases a mano; "¿Está frenado?" con Bloqueado…, que pide el motivo, y
Pausado, o "Quitar pausa"; y plegado "Corregir lo que dice GitHub" con las fases de GitHub),
en el módulo Desarrollo (en PRs sin sesión, también "borrar estado") o con `ide status
<fase|pausa|unblock> -m nota` desde la sesión. Con `ready-for-review`, **Mandar a revisión** saca de
draft sus PRs (`gh pr ready`; solo las tuyas).

**Actividad de la sesión** (otra dimensión, automática): el IDE instala hooks de Claude Code en
`.claude/settings.json` de cada sesión (UserPromptSubmit, Stop, Notification → `ide hook`, que le
avisa al IDE por `POST /api/sessions/{id}/activity`; canal `sessions.activity`; en cada mensaje tuyo
además le pasa a claude la hora local y la zona, porque Claude Code solo le da la fecha y los horarios de
GitHub y de los logs vienen en UTC). Estados:
**trabajando** (empezó un turno), **esperando tu input** (terminó el turno o pide un permiso; nota =
primera línea de su último mensaje, o el texto del permiso; si el turno terminó en «No response
requested.», el IDE no lo marca como esperándote: le pide a la sesión que cierre con un resumen para ti,
una vez cada 2 min a lo más) y **stale** (el claude no corre y el
desarrollo sigue activo: no mergeado ni pausado; revisión sin veredicto publicado). Se ve en el punto
junto al título de la card (◐ celeste girando = trabajando, ● naranjo fijo = te espera, rojo = stale, ○ =
parado sin pendientes) y, si te espera, la nota debajo en naranjo con la **hora en que claude terminó el turno** (también en el
tooltip de la pestaña `claude` y de las pestañas fijas); las que te esperan suben al
principio de su grupo; la barra de abajo cuenta "N te esperan" (sin la manager), y al pasar de
trabajando a esperarte llega una notificación de macOS. Al aprobar un permiso en la terminal vuelve
a trabajando. Los claude lanzados antes de esto no tienen hooks hasta relanzarlos (se ven como
"corriendo"). `sessions.tree` trae `activity` por sesión; `ide dev ls` muestra `TE ESPERA` /
`trabajando` con la nota. Mis desarrollos agrupa **por
estado** (pausas primero; después el flujo) y el fondo de cada card es el color de su estado; si
agrupa por estado la card no lo repite (solo la nota), si no, lo muestra como píldora. Las PRs
**mergeadas** de un desarrollo con sesión siguen en su card (chips moradas ✓, click = GitHub; detrás de un
**✓ N** que las muestra o esconde, recordado por card: escondidas si la card tiene PRs abiertas): el IDE
las guarda al cerrarse (`kv` `prclosed:<url>`; las vinculadas que ya estaban cerradas se consultan una
vez) y `reviews.github` las trae en `closed`. Los estados de antes se migran solos (analyzing /
ready / ready-to-develop → investigating, in-progress → developing, done → ready-for-review,
questions → waiting-input, blocked-definitions / blocked-client / blocked-dev → blocked con el motivo
en la nota, needs-reviewers → testing) y se aceptan en `ide status`. Las sesiones de revisión siguen
con los suyos, pero su veredicto **sale de GitHub**: tu última review publicada en esa PR la deja
`approved` / `changes-requested`, y si te vuelven a pedir review pasa a `reviewing` (actor `github`
en el historial; no aplica a las de stack). Base: `kv` `devstate:<clave>` = `{phase, block, note, since, actor, gh?}`; canales
`dev.state {key, status, note, gh?}` (fase, pausa, `unblock` o null; `gh` = fase de GitHub al
ponerla a mano) y `prs.ready {urls}`; `sessions.tree` trae `devStates`.

## 9d. Estado de los desarrollos en la base (y la sesión principal)

La **base** (`.ide/ide.db`, tabla `devs`) es la fuente de verdad del estado de cada desarrollo con
sesión: tipo, título, ticket de Notion, PR (revisiones) y `status`. Las sesiones lo cambian con
**`ide status <estado>`** (opcional `-m "nota"`; el estado se refleja en `SESSION.md`
para quien lo lea). Si una sesión edita a mano el `status:` del archivo, se adopta y queda en el
historial como "archivo". Estados válidos — ticket: las fases y pausas de arriba (y `unblock`);
revisión: reviewing | approved | changes-requested | suggests-approve | suggests-changes, más las
pausas `blocked` | `paused` | `unblock`, que van aparte, encima del veredicto (la card de Revisiones
las muestra con su nota, y marcar un veredicto las quita). Que te espera (p.ej. el OK para publicar)
lo dice su actividad.

**Historial** (tabla `events`): quién hizo qué y cuándo — el IDE (sesión creada, archivada,
revisión lanzada, merge: rebasando / esperando CI / mergeada / error), las sesiones (`ide status`
→ actor `claude:<id>`), la CLI (`cli`), los archivos (`archivo`) y **GitHub**, también lo hecho por
fuera del IDE (review pedida / aprobada / cambios pedidos por X, CI pasó o falló, lista para
review, mergeada, cerrada). El poll de GitHub guarda una foto de cada PR relevante y deja un evento
por cada cambio (la primera vez no, para no inundar). Los estados de Notion no se sincronizan.

**Para la sesión principal** (permiso `Bash(ide dev:*)`):

| Comando | Qué muestra |
|---|---|
| `ide dev ls [--json]` | todos los desarrollos (con su nombre del IDE si tiene): los de sesión (estado de la base, claude corriendo/parado, repos y ramas) y los que son solo PRs (tuyas, pendientes de revisar —`review-pending`— o a las que les pediste cambios —`review-changes`—); una revisión de varias PRs lista todas; por cada PR: autor, review, CI, revisores, draft, stack, dependencias pendientes |
| `ide dev show <id> [--json]` | lo mismo para uno (id de sesión, `#n` —también de una revisión o PR sin sesión— o `repo#n`) + dependencias pendientes + historial |
| `ide dev link <#n\|id> <pr…>` | asigna PRs (URL o `repo#n`) a ese desarrollo: pisa la asignación que tuvieran y quedan pegajosas ahí; una línea por PR `<pr>\t<anterior> → <nuevo>` (y `aviso:` si su rama no está en ningún worktree del destino). La manager lo corre con su token; desde la terminal del usuario va sin token (mover PRs solo cambia datos locales del IDE, no es una barrera de seguridad). Con una **revisión** de destino (sesión `review`): la PR se suma a su lista de PRs (como una revisión de stack; si estaba en otra revisión, sale de esa), queda en su card en Revisiones, y la sesión recibe un aviso con las nuevas (si está corriendo, en su cola; si no, como pendiente); avisa si el repo de la PR no está en la sesión |
| `ide server ls\|start\|stop\|log [<bloque> <script>]` | servidores del desarrollo por bloque (stack de un repo), como el módulo Servidores; ver §8b |
| `ide dep add\|rm\|ls <pr> [<dep…>]` | dependencias entre PRs declaradas en el IDE, además de la descripción (`rm --ignore` ignora también una de la descripción); ver "Dependencias" |
| `ide dev unlink <#n\|id> <pr…>` | saca PRs del desarrollo: quedan aparte y no vuelven por rama hasta un `link`. De una revisión: sale de su lista y queda como revisión aparte (no se puede dejar una revisión sin PRs) |
| `ide status <estado> [-m nota] [--session id]` | cambia el estado (dentro de una sesión usa la suya) |
| `ide db <prod\|staging> "<SQL>"` | una consulta de solo lectura a la base de prod o staging por `~/.claude/skills/db-connect.sh` (túnel SSM + psql en Docker, usuario read-only). Solo el SQL llega a psql: rechaza cualquier `\` (comandos de psql como `\!`, `\o`, `\copy`) y otros argumentos. Los perfiles `analyze`/`main` lo permiten sin preguntar |
| `ide procs [--json]` / `ide procs stop <id>` | qué consume el computador: batería, servidores del IDE (`run:<lugar>/<repo>/<script>`), contenedores (`docker:<proyecto compose>`, asociados a su sesión por el worktree), cantidad y consumo de los `claude`, y los procesos con ≥5% de CPU. Cada recurso del IDE sale **ABANDONADO** (con el motivo) si es un contenedor huérfano, su sesión ya no existe, su desarrollo está mergeado/pausado, o nadie lo usa hace `idle_hours` (ni el log del servidor ni la conversación de claude). `stop` para un servidor (y sus contenedores) o un proyecto compose; desde la sesión Recursos solo lo abandonado, desde otras sesiones nada, desde tu terminal cualquiera |
| `ide browser ls\|new <nombre> <url> [--note …]\|rm <nombre>\|login <nombre>` | perfiles de navegador del workspace, uno por cuenta (`.ide/browsers/<nombre>/`: `profile.toml` + `state.json` con las cookies). Cada claude arranca con `--mcp-config .ide/browsers/mcp.json`: un Playwright MCP por perfil (`browser-<nombre>`, Chrome `--isolated` con esa sesión), así una sesión usa varias cuentas a la vez y dos sesiones la misma. `login` abre Chrome; al cerrar la ventana se guarda la sesión, solo la del sitio exacto del perfil (fuera cookies de otros dominios y del dominio padre, p.ej. `.finnecto.com`, y localStorage de otros orígenes: navegar a otro cliente llega sin sesión) (el próximo navegador que se abra la toma; un perfil nuevo lo ven las sesiones al relanzar su claude). `ls` marca `local` (localhost y tech.finnecto.com: sus tools van en `--allowedTools`, sin pedir permiso) o `REAL` (cualquier otro dominio: pide permiso por acción, y las sesiones con permisos `full` no lo reciben). Desde una sesión solo `ls`: crear, borrar y el login los hace el usuario en su terminal |
| `ide update [<repo>] [--dry-run] [--session id]` | pone al día la rama de cada worktree de la sesión (o solo `<repo>`) sobre su base **solo si hace falta**: su PR está en conflicto, su madre del stack se mergeó (rebase `--onto` sobre la base de la madre y cambia la base de la PR) o arrastra commits de una madre squasheada. Si solo está atrás de su base (BEHIND), sin PR, o GitHub todavía calcula el conflicto, se niega con el motivo. Rebasea en el mismo worktree (sin cambios sin commitear) y sube con `--force-with-lease`; si choca, deja el rebase a medias y dice cómo seguir. `--dry-run`: solo dice qué haría. Desde una sesión, solo las suyas |
| `ide push [<repo>] [--force] [--branch b]… [--session id]` | sube a `origin` la rama actual de cada worktree de la sesión (o solo de `<repo>`; con `--branch`, esas ramas locales en vez de la actual), con `-u`. Se niega con la principal del repo (la de `origin/HEAD`) y con main/master/develop/staging/production, con una rama detached o inexistente. `--force` = `--force-with-lease` (nunca `--force` a secas). Una línea por rama (`subida` / `FALLÓ (…)`); exit 1 si alguna falló. Desde una sesión (por `IDE_SESSION_ID` o por la carpeta) solo sube las suyas: `--session` de otra se rechaza, y `--branch` no acepta una rama que esté en el worktree de otra sesión (sí las de los worktrees aparte de las PRs de su desarrollo, `wt-<repo>-<n>`, y las de worktrees que su claude armó en su scratchpad). Existe para que las sesiones no tengan que hacer `cd … && git push` |

API: `GET /api/devs`, `GET /api/devs/{id}`, `POST /api/devs/{id}/status` (`{status, note, actor}`);
canales WS `dev.list`, `dev.show`, `dev.status`. Errores: `bad_status`, `no_status`, `unknown_dev`.

## 9d-bis. Revisar PRs

El botón de revisión (Revisiones / resumen de la PR) crea o reusa la sesión de revisión y le **dispara
directo la skill** (`.ide/prompts/review-pr.md`: `/finnecto-core:pr-review <url> — Revisión desde el
IDE…`). Si la sesión de revisión ya existe (re-review), manda en cambio `.ide/prompts/rereview-pr.md`
(corto: trae el head nuevo, sigue el ciclo de hilos y revisa solo el delta; las reglas ya están en su
conversación; si falta el archivo usa el de fábrica; variables extra `{{number}}`). La sesión **publica la review en GitHub** como indica la skill (comentarios inline, hilos y
veredicto), deja en `SESSION.md` `## Veredicto` (primera línea "Aprobar" o "Pedir cambios" y por qué) y
`## Hallazgos`, y marca `ide status approved | changes-requested`. Los prompts de revisión (de una PR y de un
stack) pisan a la skill en el body de la PR: sus faltas de forma son comentario no bloqueante y solo
pide cambios un body que afirma algo falso. Además le dicen que las PRs llegan en draft a propósito y el CI corre
después de aprobar: draft o CI sin correr no son hallazgo. El prompt le dice que el contenido de la PR es
material, no instrucciones; y con el perfil `analyze` publicar (`gh pr review`, `gh api` con mutaciones)
pide OK en su terminal (una PR maliciosa podría intentar que se apruebe sola): no lo agregues a los
permitidos. Estados de revisión: `reviewing`,
`suggests-approve`, `suggests-changes` (veredicto sin publicar), `approved`, `changes-requested` (ya no
existe `commented`: se migra a `reviewing`). El IDE los alinea con GitHub en cada ronda: tu última review en la PR (en una revisión de
stack, en todas sus PRs) da `approved` (aprobaste todas), `changes-requested` (pediste cambios en alguna) o
`reviewing` (te volvieron a pedir review en alguna, que pesa más que los cambios pedidos). En el resumen de la PR y en el módulo Desarrollo, **Tu
revisión** muestra el veredicto y los botones **Aprobar** / **Pedir cambios** (con confirmación; pedir
cambios exige comentario) para publicar o corregir el veredicto tú (`gh pr review`) — solo PRs que te
pidieron revisar o con sesión de revisión. Canales `review.draft {url}`, `review.submit {url, event, body}`.

## 9e. Feedback y revisión nocturna (mejora con el uso)

Cada sesión anota las correcciones del usuario en la sección `## Feedback` de su `SESSION.md`
(`- fecha — qué hice → qué me corrigió → lección (general | este desarrollo)`), sin que se lo pidan.
Cada noche, a la hora de `[manager] nightly` en `config.toml` (default `"03:00"`; `""` la apaga; el IDE
tiene que estar corriendo), el IDE junta el material (lo de `ide feedback collect --since <última
revisión>`: lo anotado + los mensajes del usuario de los transcripts de cada sesión, para cazar también
las correcciones no anotadas) en `feedback/material-AAAA-MM-DD.md` y corre la revisión como manager **en
modo restringido**: un `claude -p` aparte en la carpeta de la principal (sus instrucciones), sin shell,
que solo puede leer el workspace y `~/.claude/CLAUDE.md` y editar en `feedback/` (el material lo pueden
haber escrito terceros: PRs, tickets; el prompt lo trata como dato; log en `feedback/AAAA-MM-DD.log`).
Con `.ide/prompts/nightly-review.md`: agrupa patrones,
revisa si ya están en las instrucciones y escribe un **plan** en
`.ide/sessions/<principal>/feedback/AAAA-MM-DD.md` (`status: pending`) con evidencia, archivo y texto
exacto de cada cambio propuesto. **No aplica nada**: la barra de abajo muestra "plan de feedback
pendiente"; el usuario le dice a la principal qué aplicar (los `CLAUDE.md` de repos van por PR) y ella
lo marca `status: applied`. `ide feedback run` (o `POST /api/manager/nightly`, canal
`manager.nightly`) la pide ya; `ide feedback collect [--since AAAA-MM-DD[THH:MM]] [--json]`.


## 10. Problemas comunes

Cada sesión fija su conversación de `claude`: `claude_session` (nueva con `--session-id`,
retomada con `--resume <id>`; las sesiones viejas adoptan la transcripción más reciente) y
`claude_name` (`--name "<id> · <token>"`, se ve en el borde del input).

| Síntoma | Causa / solución |
|---|---|
| Sesión con badge **⚠ confiar carpeta** | Claude Code pregunta si confías en la carpeta nueva. Abre la terminal de la sesión y acepta. También aparece con el aviso del modo `full` (acéptalo una vez). |
| `No hay ide run activo` | Levanta `ide run` en el workspace (o exporta `IDE_URL`). |
| `claude_missing` | `claude` no está en el PATH del server. |
| `setup failed` en un repo | Mira la salida; arregla el script; `ide script setup <repo>`. |
| `⚠ no ejecutable` en un script | `chmod +x .ide/scripts/<repo>/<nombre>`. |
| `⚠ error` en una sesión | `.session.toml` o el frontmatter de `SESSION.md` está roto; el mensaje dice cuál. |
| `⚠ poll` en una revisión | `gh` falló (auth/red); el title muestra el último OK. `gh auth status`. |
| La UI dice "desconectado" | El server se cayó; lo de la pantalla puede estar viejo. |
| Al reiniciar el server todas quedan `○` | Normal: no hay auto-resume. Click → Abrir: si la conversación sigue viva en segundo plano (el daemon de Claude Code la conserva al morir el PTY) se reengancha con `claude attach` **solo si la lanzó el IDE** (coincide `claude_session` o `claude_name` de `.session.toml`; una lanzada a mano podría tener otros permisos); si no, `--resume <claude_session>`. **Parar** también detiene la de fondo. |
| `⚠ error` "sigue en segundo plano" | No se pudo reenganchar: `claude agents` (attach o stop) y vuelve a Abrir. |
| "Transcript saving is off — inherited CLAUDE_CODE_CHILD_SESSION" | Server viejo lanzado desde dentro de un `claude`: el server actual limpia esas variables al lanzar sesiones; reinícialo. |

## 11. Códigos de error (`{code, message}`)

`invalid_id`, `invalid_kind`, `invalid_permissions`, `invalid_name`, `session_exists`,
`main_exists`, `unknown_session`, `id_collision`, `id_exhausted`, `missing_vars`,
`unknown_template`, `bad_prompt`, `bad_var`, `bad_vars_file`, `bad_prompt_file`, `bad_notion_url`,
`bad_pr_url`, `forbidden`, `unknown_repo`, `repo_exists`, `repo_not_in_session`,
`ambiguous_repo`, `uncommitted_changes`, `setup_failed`, `archive_failed`, `script_not_found`,
`script_not_executable`, `script_failed`, `gh_failed`, `fetch_failed`, `checkout_failed`,
`not_a_review`, `session_archived`, `pr_closed`, `bad_status`, `no_status`, `unknown_dev`, `not_bottom`, `not_approved`, `ci_failed`, `merge_pending`,
`conflict`, `merge_failed`, `unknown_pr`, `no_merge`, `not_yours`, `fork_pr`, `repo_mismatch`,
`forbidden_origin`, `github_off`, `bad_settings`, `unknown_prompt`, `queued`, `queue_full`, `not_running`, `no_doc`, `claude_missing`, `no_server`, `no_session`, `server_error`,
`timeout`, `bad_frontmatter`, `bad_request`, `unknown_channel`, `already_running`,
`unknown_worktree`, `bad_place`, `git_failed`, `bad_path`, `not_a_dir`, `not_found`, `too_large`,
`binary`, `changed_on_disk`, `busy`, `unpushed`, `no_db`, `telegram_off`, `db_not_local`, `pgweb_missing`, `pgweb_failed`.

## 12. API (para integraciones)

Seguridad: el WebSocket y `/api/*` exigen `Host` loopback (`localhost`, `127.0.0.1`, `::1`;
frena DNS rebinding) y rechazan requests de navegador cuyo `Origin` no sea la propia UI (mismo
host) o `IDE_CORS_ORIGINS` (dev): cualquier página que visites podría si no hablarle a
`localhost`. Sin `Origin` (CLI, scripts) se acepta. Rechazo: WS cerrado con 1008, HTTP 403
`forbidden_origin`.

HTTP: `GET /api/sessions` (árbol), `POST /api/sessions` (body = flags de `session new` en
snake_case: `id`, `notion`, `main`, `template`, `vars`, `prompt`, `title`, `permissions`,
`review`, `if_missing`, `dry_run`, `caller`), `POST /api/sessions/{id}/open|stop`. Errores:
409/400/500 con `{code, message}`.

WebSocket `/ws`: canales `sessions.tree|new|open|stop|rm|archive|script|doc|refreshReview|repoRm`,
`ui.config`, `prompts.list` (`{prompts: [{name, text}]}`), `terminal.replay` (`{id}` → `{data, end}`),
`server.status` (`{pending, supervised, idleBefore}`), `server.restart`; evento `server.update`, `reviews.github`
(`{pending, changesRequested, mine: {returned, waiting, missing, draft, approved}` (cada PR con `deps`, `depsPending`), stacks: {<id>: [pr…]}, me, reviewers: [{login, count}], reviewersTruncated, members, selected, error, lastOk, orgs}`), `sessions.newForPr` (`{url}`), `reviews.setReviewers` (`{logins}`), `reviews.merge` / `reviews.mergeRetry` (`{url}`), `reviews.discussion` (`{url}`), `reviews.start` (`{url}` → `{id, created,
process}`), `usage.get` (`{sessionId}` → `{context, limits}`), `terminal.*`; eventos
`sessions.changed` (mismo payload que `sessions.tree`) y `reviews.github`. Servidores (§8b):
`runs.list` (→ `{runs: [{place, repo, name, state, exitCode, pid, started, ended, urls}], places:
[{id, repos}]}`), `runs.start|stop` (`{place, repo, name}`), `runs.log` (`{place, repo, name,
offset}` → `{data, end, reset}`, `offset` -1 = lo último), `prwt.ensure|update` (`{url}`),
`prwt.remove` (`{place, force}`); evento `runs.changed`. Archivos: `wtfiles.list` (`{place, repo,
path}`), `wtfiles.envs`, `wtfiles.read` (→ `{text, mtime}`, `mtime` en texto), `wtfiles.stat` (→ `{mtime}`), `wtfiles.write` (`{…, text, mtime}`; `mtime` null = sobrescribir).
