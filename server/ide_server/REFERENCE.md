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
    ├── scripts/<repo>/<nombre>         # §8 (ejecutables)
    ├── worktrees/<id>/<repo>/          # worktrees reales (git worktree add)
    └── sessions/
        ├── CLAUDE.md                   # mapa de repos + uso de `ide`; lo heredan TODAS las sesiones
        ├── templates/{ticket,review}.md   # §7
        └── <id>/                       # una sesión
            ├── .session.toml           # kind, permissions, created, [ports], [setup], pr_url, reviewed_sha, claude_session, claude_name
            ├── PROMPT.md               # prompt inicial (plantilla renderizada)
            ├── TICKET.md | REVIEW.md   # estado + análisis (§9)
            └── <repo> -> ../../worktrees/<id>/<repo>   # symlink relativo
```

`ide init` **siembra** `sessions/CLAUDE.md`, `templates/*.md`, `prompts/tickets-y-prs.md`, `prompts/review-pr.md`, `permissions/*.json` y
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
modules = ["sessions", "terminal", "prompts", "stack", "review", "deps", "config"]   # módulos visibles en el menú de acciones; ver abajo

# [mlx] …                         # modelos locales (opcional; panel Settings → Modelos)
```

Valores inválidos (`default_permissions` fuera de la lista, `max_running` < 1 o no entero) hacen
fallar el arranque con un mensaje que nombra la clave.

`[ui] modules`: ids disponibles `terminal`, `prompts`, `stack`, `review`, `deps`, `config`, `files`, `search`, `changes`, `graphite`, `tasks`,
`notion`, y `chat`. Si `chat` **no** está, el área principal es la vista por sesión (terminal
`claude` + doc + scripts); si está, vuelve el chat propio.

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
`Edit(**/TICKET.md)`, `Edit(**/REVIEW.md)` (crear incluido); MCP de Notion
(`notion-fetch`, `notion-search`, `notion-query-data-sources`). Niega `git diff/log --output`.
Las reglas de archivo se escriben como `Edit(...)`: Claude Code no evalúa `Write(...)`.

Todas las sesiones reciben `--add-dir=.ide/worktrees/<id>` (sus repos); la principal además
`--add-dir=.ide/sessions` (para leer los `TICKET.md` de todas).

**Restricción de seguridad (server):** cuando el pedido viene de una sesión (`IDE_SESSION_ID`
seteada), solo la **principal** puede crear sesiones y **nunca con `full`** (si el default es
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
| `--notion <url>` | id = `n-<últimos 10 hex del page id>` y `notion_url` = la URL. Si el id ya es de otro ticket → `id_collision` |
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
- `ide session rm <id> [--force]`: si hay cambios sin commitear en algún repo, **se niega antes de tocar nada** (`--force` lo fuerza); si no: para el proceso, corre `archive` de cada repo, quita los worktrees y borra la carpeta. Las branches quedan.

### Repos y scripts
- `ide repo add <repo> [--branch b] [--session id]`: worktree en `.ide/worktrees/<id>/<repo>`, symlink en la sesión, reserva `IDE_PORT` y corre `setup` (espera y muestra la salida). Branch default = `<id>`; si está ocupada → error que sugiere `--branch`. `setup` fallido → exit 1, el worktree queda marcado `setup failed` (reintenta con `ide script setup <repo>`).
- `ide repo rm <repo> [--force]`: misma regla de cambios sin commitear; corre `archive`; quita worktree y symlink.
- `ide script <nombre> [<repo>]`: corre `.ide/scripts/<repo>/<nombre>` en el worktree (repo inferido si la sesión tiene uno solo). Devuelve el exit code del script.

## 7. Plantillas (`.ide/sessions/templates/*.md`)

Texto con `{{variable}}`. Una variable sin valor es **error** (`missing_vars`), nunca se manda
un placeholder literal. Siempre disponible: `{{id}}`. Con `--notion`: `{{notion_url}}`.

| Plantilla | Variables | Uso |
|---|---|---|
| `ticket.md` | `id`, `title`, `notion_url` | qué hace cada sesión de ticket (analizar, `ide repo add`, escribir `TICKET.md`) |
| `review.md` | `id`, `title`, `pr_url`, `author`, `repo` (las completa el IDE con `gh`) | qué hace cada revisión |

Puedes crear plantillas nuevas (`templates/x.md`) y usarlas con `--template x`. La principal
**no** usa plantilla: la ★ de la UI la crea sin prompt y arranca esperando al usuario.

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

cwd = el worktree. Env: `IDE_SESSION_ID`, `IDE_REPO`, `IDE_ROOT_REPO` (repo principal: para
copiar `.env`, etc.), `IDE_WORKSPACE`, `IDE_PORT` (base de un bloque de 10 puertos reservado por
sesión+repo, desde 8100, persistido en `.session.toml`). stdin es `/dev/null`.

Ejemplo `setup`:
```sh
#!/bin/sh
set -e
cp "$IDE_ROOT_REPO/.env" .env 2>/dev/null || true
uv sync
```

## 9. Estado de sesiones

**Kinds:** `main` (principal, una), `ticket`, `review`.

**`TICKET.md` / `REVIEW.md`:** frontmatter + cuerpo. El IDE siembra el frontmatter al crear;
la sesión solo cambia `status` y escribe el cuerpo.
```markdown
---
status: analyzing
title: Exportar facturas
notion_url: https://www.notion.so/...
---
## Scope … ## Repos … ## Plan … ## Bloqueantes … ## Dudas …
```
- Ticket: `analyzing` · `blocked` · `questions` · `ready` · `in-progress` · `done`.
- Review: `reviewing` · `commented` · `approved` · `changes-requested`.
- Derivados por el server (no se escriben): proceso `running` / `queued` / `stopped`;
  revisiones `stale` (el PR tiene commits nuevos; "Refrescar" en la UI) / `merged` / `closed`;
  `attention: "trust"` (ver §10).

## 9b. Revisiones de GitHub y barra de usage (UI)

**Revisiones** (sidebar principal): cada `github_interval` s el server hace un `gh api graphql`
(org-wide, no depende de la sesión abierta) y la UI muestra cards en dos grupos:
**Pendientes** (PRs abiertos de la org con review pedida a vos) y **Pedí cambios** (PRs abiertos donde tu
última review con veredicto es `CHANGES_REQUESTED`; las respuestas en hilos no la tapan y no te re-pidieron review). Si el PR ya tiene sesión
(`pr-<repo>-<n>`) la card es la sesión; si no, una card del PR. Las sesiones de revisión que no
están en GitHub van en **Otras**. Bajo el título, chips `@revisor N`: cuántos PRs abiertos de
la org tienen review pedida a cada **miembro de la org** (los pedidos a equipos y a gente de
afuera no cuentan; pagina hasta 1000 PRs, el tope de la búsqueda de GitHub; si se pasa, se marca
con `+`); el tuyo resaltado. El módulo Configuración (⚙ de Revisiones) elige qué miembros se ven (checkbox); se
guarda en la base (`.ide/ide.db`); sin selección se ven todos los que
tienen pendientes. La sección se colapsa desde su título; Pendientes / Pedí cambios / Otras son
grupos fijos. En las pendientes, el botón de revisión (hover) envía
`.ide/prompts/review-pr.md` (pega + Enter) a la sesión del PR: si no existe la crea (como
`--review <url>`, con ese prompt en vez de la plantilla `review`); si está parada la retoma con el
prompt; si está en cola falla con `queued`. Errores de `gh` se ven como `⚠ github`.

**Mis PRs** (sidebar principal, bajo Revisiones): tus PRs abiertas de la org (del mismo poll),
agrupadas como el inbox de Graphite: **Devueltas** (`reviewDecision` = `CHANGES_REQUESTED` y sin reviews pedidas pendientes),
**Esperando revisores** (con reviews pedidas pendientes, aunque antes hayan pedido cambios), **Sin revisores**, **Draft** y
**Aprobadas** (`APPROVED`). Prioridad: draft > aprobada > esperando > devuelta > sin revisores (como Graphite).
Son cards sin sesión: click la selecciona como desarrollo (el módulo Stack muestra su stack);
se abre en GitHub solo con el botón de hover, igual que en Revisiones. Todas las cards
de PR (y las de sesión con PR) marcan el CI: ✓ pasó, ✗ falló (checks o conflicto con la base),
◌ corriendo; el título muestra el total y los grupos se
colapsan. Cada card muestra quién la revisa (chips: azul review pedida, verde aprobó, amarillo
pidió cambios; una review re-pedida cuenta como pedida). Si la PR es parte de un stack, la card
muestra su posición (`2/4`, 1 = la de abajo).

**Mergear** (hover en Mis PRs; solo PRs tuyas, aprobadas, que son la de abajo de su stack o no
están en uno; nunca PRs desde forks; el `origin` local del repo tiene que ser el mismo repo de
GitHub; deshabilitado si el CI falló; pide confirmación; canal `reviews.merge {url}`). No
bloquea: valida, cierra el diálogo y sigue en segundo plano; la card muestra el paso y se pinta
**ámbar** mergeando, **roja** con error (reintentar: `reviews.mergeRetry {url}`) y **morada**
mergeada (24 h, en el grupo **Merges** de Mis PRs cuando ya no está abierta).
1. En un worktree propio por repo (`.ide/worktrees/_merge/<repo>`, detached) rebasea la rama
   sobre `origin/<base>` y la empuja con `--force-with-lease` (si hay conflicto aborta: `conflict`).
   Si la rama arrastra commits de una PR madre que ya se mergeó con squash (estaba apilada y
   GitHub la re-apuntó a la base), busca el último commit que fue head de otra PR mergeada
   (`GET /repos/{o}/{r}/commits/{sha}/pulls`) y rebasea con `--onto` desde ahí: solo viajan los
   commits propios de la PR.
2. El IDE espera (cada 30 s) a que el CI pase y la PR sea mergeable, y recién ahí pide
   `PUT /repos/{o}/{r}/pulls/{n}/merge-async` (squash). Es el único endpoint que GitHub acepta para
   PRs de stacks nativos, y evita `gh pr merge --auto` (que justo después del push falla con "not
   mergeable" porque GitHub todavía está calculando). Si el CI falla o hay conflicto, error.
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
"merge en orden: A → B → este PR → C" solo cuenta lo de antes de "este/esta PR". Se siguen las
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
resincronización completa cada 30 min y al arrancar. Miembros de la org: una vez por día.

**Cards de la sidebar** (sesiones y PRs, mismo cascarón): arriba **repo y número** (`API #4581`,
en negrita; en Revisiones el autor como chip; ● ○ = `claude` corriendo/parado), después el título
y una línea de detalle (posición en el stack `◫ 2/4`, "N dependencias" pendientes, "⟳ commits
nuevos desde tu revisión", estado del merge; en Mis PRs, los revisores como chips con su estado:
✓ aprobó, ✗ pidió cambios, ◌ pendiente). Cada persona tiene siempre el mismo color de chip (también
en los chips de conteo de Revisiones). **Fondo** tenue = review: verde aprobada, amarillo cambios
pedidos, azul esperando revisor, morado mergeada. **Borde** (2 px) = CI/merge/bloqueo, en este
orden: morado girando mergeando, rojo CI falló o conflicto, amarillo girando CI corriendo, café
aprobada pero bloqueada (dependencias pendientes o no es la de abajo de su stack). La seleccionada
lleva un contorno claro. Al pasar el mouse, el estado en palabras.

**Módulo Dependencias** (menú de acciones, id `deps`): para las PRs del desarrollo actual, de qué
dependen (cadena completa: ✓ mergeada, ◌ abierta, ✗ cerrada, ⇄ van juntas, "vía X" indirecta) y
qué PRs abiertas las declaran como dependencia.

**Secciones Revisiones y Mis PRs** (misma estructura): título colapsable con el total, grupos
colapsables y la misma card. El ⚙ de cada sección (y el de la sidebar principal, para Sesiones)
abre el **módulo Configuración** (id `config`) en esa sección: **agrupar por** estado, repo, stack
(con el título de la PR de abajo), autor (solo Revisiones) o sin agrupar; en Revisiones también
los revisores visibles en los chips. El agrupado se recuerda por navegador. La card seleccionada
lleva contorno de acento y una barrita a la izquierda.

**Secciones:** qué secciones están abiertas o cerradas (Revisiones, Mis PRs y sus grupos, grupos
de sesiones, secciones del módulo Revisión) se recuerda entre recargas, por navegador
(`localStorage`).

**Abrir sesión:** seleccionar una sesión parada en la sidebar la lanza (retoma su conversación); si falla queda "Reintentar".

**Barra inferior:** contexto de la sesión abierta (último turno de su transcript en
`~/.claude/projects/`; ventana 1M si `model` de `~/.claude/settings.json` tiene `[1m]` o se pasó de
200k) y las ventanas de 5 h y semanal con el tiempo hasta el reinicio. Los límites salen del
endpoint OAuth de `/usage` (`api.anthropic.com/api/oauth/usage`, no documentado) con el token de
Claude Code (`claudeAiOauth` en el llavero `Claude Code-credentials` o
`~/.claude/.credentials.json`); el server lo consulta cada 60 s (ante 429 duplica la espera, tope
5 min) y la UI lee cada 5 s. Sin tokens. Errores se ven como `⚠ límites: …`.

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
| `⚠ error` en una sesión | `.session.toml` o el frontmatter de `TICKET.md` está roto; el mensaje dice cuál. |
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
`not_a_review`, `session_archived`, `not_bottom`, `not_approved`, `ci_failed`, `merge_pending`,
`conflict`, `merge_failed`, `unknown_pr`, `no_merge`, `not_yours`, `fork_pr`, `repo_mismatch`,
`forbidden_origin`, `github_off`, `bad_settings`, `unknown_prompt`, `queued`, `queue_full`, `not_running`, `no_doc`, `claude_missing`, `no_server`, `no_session`, `server_error`,
`timeout`, `bad_frontmatter`, `bad_request`, `unknown_channel`.

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
(`{pending, changesRequested, mine: {returned, waiting, missing, draft, approved}` (cada PR con `deps`, `depsPending`), stacks: {<id>: [pr…]}, me, reviewers: [{login, count}], reviewersTruncated, members, selected, error, lastOk, orgs}`), `reviews.setReviewers` (`{logins}`), `reviews.merge` / `reviews.mergeRetry` (`{url}`), `reviews.discussion` (`{url}`), `reviews.start` (`{url}` → `{id, created,
process}`), `usage.get` (`{sessionId}` → `{context, limits}`), `terminal.*`; eventos
`sessions.changed` (mismo payload que `sessions.tree`) y `reviews.github`.
