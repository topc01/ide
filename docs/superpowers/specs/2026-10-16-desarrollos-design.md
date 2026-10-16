# Desarrollos (modelo unificado + base de datos local) — Diseño

> Unifica las cards de la sidebar (sesiones, Revisiones, Mis PRs) en un solo modelo,
> **desarrollo**, y guarda en una base local lo que hoy se baja de GitHub en cada poll.
> Fecha: 2026-10-16. Estado: **aprobado** (P1 y P2 confirmadas el 2026-10-16).

## Problema

- Hay tres tipos de card con reglas distintas: la de **sesión** (carpeta + worktrees, puede
  tocar varias ramas/PRs), y las de **PR** en Revisiones y Mis PRs. Una misma PR puede aparecer
  como sesión en un lado y como PR en otro; los botones y lo que se muestra cambian según dónde.
- Cada 2 min se baja todo de nuevo (~125 PRs abiertas con su texto, miembros de la org, estado
  de dependencias ya mergeadas). Casi todo es estático; el poll es pesado y GitHub ya cortó con
  502 por eso.

## Decisiones cerradas

> **Actualización 2026-10-16:** la base pasa a ser la **fuente de verdad del estado** de cada
> desarrollo con sesión (antes: "las sesiones viven en disco y la base no las duplica"). La carpeta
> sigue siendo el lugar de trabajo de `claude`; el estado se cambia con `ide status` y todo deja
> historial (tabla `events`), incluido lo que pasa en GitHub por fuera del IDE. Notion no se
> sincroniza (lo hace el usuario a mano). Ver REFERENCE §9d.

1. **Base local SQLite en `.ide/ide.db`** (stdlib `sqlite3`, sin dependencias; no se commitea).
   `merges.json` y `reviews.json` migran a tablas. Las **sesiones siguen viviendo en disco**
   (`.ide/sessions/<id>/`, fuente de verdad, ver spec de sesiones-carpeta): la base no las
   duplica, solo guarda a qué desarrollo pertenecen.
2. **Un modelo, una card.** Todo lo que se lista es un *desarrollo*. Revisiones y Mis PRs pasan a
   ser **filtros** de la misma lista; cambian los botones según el contexto, no la card.
3. **Ramas en stack: ideal, no obligatorio.** Un desarrollo puede tener ramas sueltas.
4. **Se construye directo** (sin pasar por aprobación de spec otra vez) una vez cerradas las
   propuestas de abajo, en tres rebanadas.

## Modelo

```
Desarrollo ── 0..1 Sesión de claude (carpeta + worktrees)
     └── 1..N Rama (repo, rama, posición en su stack) ── 0..1 PR
```

- **Desarrollo:** `id`, `title`, `kind` (`mine` | `review`), sesión (opcional), ramas, `created`.
- **Rama:** `repo`, `branch`, `stack_id` (nativo o inferido), `position`, PR (opcional).
- **PR (cache):** repo, número, título, autor, head/base, texto, dependencias parseadas, estado
  (`OPEN`/`MERGED`/`CLOSED`), `updated_at`. Lo dinámico (review, CI, conflicto, revisores
  pendientes) también se guarda, pero se refresca en cada poll.

### P1 — Qué ramas forman un desarrollo

Regla única, en orden de prioridad; **una rama pertenece a un solo desarrollo**:

1. **Sesión:** todas las ramas de sus worktrees (y las PRs de esas ramas) son de su desarrollo.
   Es la única forma de que un desarrollo cruce repos.
2. **Stack sin sesión:** todas las PRs del stack (nativo de GitHub o inferido por ramas) son un
   desarrollo.
3. **PR suelta sin sesión:** un desarrollo de una rama.

Las dependencias entre PRs (`## Dependencias`, "van juntas") **se muestran, no agrupan**.

**PR no relacionada desde una sesión:** si en una sesión de ticket aparece algo que merece su
propia PR, la sesión no la mete en su desarrollo: acción **Nuevo desarrollo** (desde la card o
la CLI `ide session new …`) crea otra sesión. Así cada desarrollo queda con un solo propósito.

### P2 — Revisiones por stack

Los pedidos de review llegan por PR (rama), pero se agrupan por stack:

- Un pedido para la PR X se ubica en el stack de X (nativo o inferido); el **desarrollo de
  revisión es el stack entero**. Las PRs que te pidieron se marcan "a revisar"; las otras se
  ven atenuadas (como en el módulo GitHub).
- **Revisar** crea **una sesión por stack**: worktree en el head de la PR de más arriba que te
  pidieron (contiene a las de abajo), y el prompt `review-pr` recibe la lista de PRs a revisar,
  en orden de abajo hacia arriba.
- Las sesiones de revisión existentes (`pr-<repo>-<n>`) se mantienen: quedan como la sesión del
  desarrollo de su stack. Si un stack ya tiene una, no se crea otra.
- PR a revisar fuera de un stack: desarrollo de una rama, como hoy.

## Base de datos (`.ide/ide.db`)

| Tabla | Qué guarda | Se actualiza |
|---|---|---|
| `prs` | cache de PRs (estático + dinámico) | poll incremental |
| `pr_deps` | dependencias parseadas (`from_url`, `to_repo`, `to_number`) | cuando cambia el texto |
| `desarrollos` | id, título, kind, sesión, creado | al crear/derivar |
| `ramas` | desarrollo, repo, rama, stack, posición, PR | poll + sesiones |
| `members` | miembros de la org | 1 vez por día |
| `merges` | trabajos de merge (hoy `merges.json`) | merger |
| `settings` | revisores visibles (hoy `reviews.json`), último poll | UI / poll |

Esquema versionado (`PRAGMA user_version`) con migraciones simples; ante una base corrupta se
renombra a `.bak` y se reconstruye desde GitHub (todo lo de GitHub es reconstruible; lo único
propio son `merges` y `settings`, que se migran desde los JSON la primera vez).

## Poll incremental

Verificado (2026-10-16): el `updatedAt` de una PR **no** cambia cuando termina el CI (p.ej.
api#4556: checks 17:57, `updatedAt` 17:42). Por eso son tres capas:

- **Incremental** (cada 2 min): `is:pr org:X updated:>=<último poll − 1 min>` (abiertas y
  recién cerradas/mergeadas). Trae lo estático, reviews y pedidos de review. Las que dejaron de
  estar abiertas salen de `prs` y quedan en el cache de referencias (no cambian más).
- **Refresco dinámico** (cada 2 min): CI, conflicto, decisión de review, revisores y stack de las
  PRs **relevantes** (mías, las que reviso o me pidieron, las de sus stacks y sus dependencias
  abiertas), con `nodes(ids: …)` en lotes.
- **Resincronización completa** cada 30 min y al arrancar (corrige cualquier desvío).
- Miembros de la org: una vez por día. Dependencias a PRs mergeadas/cerradas: una vez.
- La UI recibe el mismo evento `reviews.github` armado desde la base (sin cambio visible en la
  rebanada 1).

## Decisión: un worktree por repo (no por rama)

Se mantiene `.ide/worktrees/<id>/<repo>` y el worktree se mueve entre las ramas del desarrollo
(`git checkout`). Permite restackear con `git rebase --update-refs` desde la rama de arriba (git no
deja mover una rama checkouteada en otro worktree) y cada repo hace su `setup` una sola vez.
Se pierde correr dos ramas a la vez; si hace falta, un worktree extra temporal más adelante.

## UI

- **Card única** (`DevCard`): título; indicador de sesión (● corriendo / ○ parada) si tiene;
  una fila por rama: `repo · rama · #PR · CI · review · posición en stack · dependencias`;
  badges de merge (ámbar/rojo/morado). Click = seleccionar el desarrollo (abre su sesión si
  tiene). Botones por contexto:
  - Revisión: **Revisar**, abrir en GitHub.
  - Mío: **Mergear** (en la rama de abajo), abrir en GitHub, **Nuevo desarrollo**, archivar
    (si tiene sesión).
- **Sidebar:** una lista de desarrollos con filtros/grupos: *Mis desarrollos* (por estado:
  devueltas, esperando, sin revisores, draft, aprobadas), *Revisiones* (pendientes, pedí
  cambios), *Otros*. El selector de desarrollo y los módulos GitHub/Revisión trabajan sobre el
  desarrollo (todas sus ramas), no sobre una PR.

## Rebanadas

1. **Base + poll incremental** (sin cambio visible): `ide.db`, migración de `merges.json`/
   `reviews.json`, poll incremental, el evento `reviews.github` sale de la base.
2. **Modelo desarrollo + card única:** derivación (P1/P2), `DevCard`, sidebar con filtros,
   selector y módulos sobre el desarrollo, acción Nuevo desarrollo.
3. **Revisiones por stack:** sesión de revisión por stack y prompt con la lista de PRs.

## Fuera de alcance

Editar dependencias desde el IDE, agrupar repos por dependencias, sincronizar la base entre
máquinas, borrar desarrollos (solo archivar sesiones, como hoy).
