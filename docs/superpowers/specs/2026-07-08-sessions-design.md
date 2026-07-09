# R1 — Sesiones (sidebar + creación) · Design

Fecha: 2026-07-08 · Estado: **aprobado** · Rebanada: R1 del `docs/design/ROADMAP.md`.
Depende de: R0 (Fundación).

## Objetivo

El **sidebar de sesiones** y —su corazón— la **creación de sesiones**. Esta es la parte
del producto que más iteración necesitaba, así que el modelo está diseñado en detalle.
Entrega: lista de repos del workspace, árbol recursivo de sesiones, modal de nueva sesión,
selección, rename inline, y la mecánica real de **worktree × branch**.

## Fidelidad de UI (prioridad)

La UI es **alta fidelidad** y prioritaria. Fuente de verdad: `docs/design/handoff/HANDOFF.md`
+ `mockup.dc.html`, dirección visual **1a — Terminal/amber** (tokens en
`docs/design/REFERENCES.md`). El `SessionsPanel` y el `NewSessionModal` deben reproducir con
precisión el mockup: indentación 16px/nivel, chevron que rota, status dot, pill de rol
(accent sobre `#2e2820`), "+" inline y la fila punteada "+ Agregar sesión hija", selección
con borde/fondo accent. Nada de estética "por defecto": se implementa contra el mockup.

## Concepto base: workspace, no repo

El IDE opera sobre un **workspace**: una carpeta (ej. `~/Finnecto/finnecto/`) que **contiene
uno o más repos git**. El descriptor `.ide/` vive en la raíz del workspace — **no** dentro
de un repo, y **no se commitea** (es estado local/máquina). El comando `ide` hace *walk-up*
hasta encontrar `.ide/`, identifica el workspace y descubre los repos adentro.

```
Workspace  finnecto/          (contiene repos + .ide/)
├── .ide/                      ← local, NO commiteado
│   ├── config.toml            workspace name, roles, hooks
│   ├── sessions.json          árbol de sesiones (runtime, local)
│   ├── tasks/                 artefactos (handoff/contexto/tareas) — links a Notion
│   └── worktrees/<slug>/      worktrees de las sesiones
├── repo-a/                    (SIN sesión — monitoreado)
├── repo-b/                    (SIN sesión — monitoreado)
└── … sesiones (ver modelo) …
```

**El repo principal de cada repo no es una sesión.** Se monitorea: aparece en la lista
Repos, se puede abrir su terminal, y las tabs superiores muestran "qué está pasando en el
repo". Esto evita el conflicto de git de tener su branch (p.ej. `main`) tomada por un
worktree.

## Modelo de sesión

Árbol recursivo. Una sesión **puede o no tener branch**:

- **Coordinadora** (sin branch): maneja **contexto + tareas** del feature/ticket y **comanda
  a sus hijas**. No toca código. Es el "King". Puede tener hijas en **repos distintos** del
  workspace → una coordinadora ≈ un "desarrollo" de finnecto, descompuesto en hijas por repo.
- **De trabajo** (con branch), en dos modos de acceso:
  - **read-write** → `git worktree add <path> <branch>`: la branch queda **exclusiva**
    (regla de git: 1 branch = 1 worktree).
  - **read-only** → `git worktree add --detach <path> <commit-de-la-branch>`: HEAD
    desanclado, **no ocupa** la branch → **repetible/compartible** sobre la misma rama.

Nodo (persistido en `.ide/sessions.json`):
```
{ id, name, description?, role?, status,
  repoId?,                       # repo al que pertenece (null si coordinadora sin repo)
  branch?,                       # null si coordinadora
  access: 'rw' | 'ro' | null,    # null si coordinadora
  worktreePath?,                 # <workspace>/.ide/worktrees/<slug> (null si coordinadora)
  expanded, terminals[], children[] }
```

`status` (dot de color, tokens 1a): running `#7fb069`, idle `#7d7568`, done `#6b8fbf`.

## Creación de sesión (el flujo)

Modal de nueva sesión (campos del handoff, refinados):

1. **Nombre** (requerido) → genera `slug`.
2. **Descripción** (opcional) → se pasa como contexto a Claude Code al arrancar.
3. **Rol** (opcional, ver §Roles) → preset que define modelo/prompt/acceso.
4. **Tipo de sesión**:
   - **Coordinadora** (sin branch) — solo contexto + tareas + comanda hijas.
   - **De trabajo** → elegir **repo** del workspace + **branch**:
     - **Branch nueva**: nombre **editable** (default `<slug>`), **base elegible**
       (default = branch del ancestro más cercano que tenga branch → *stacked*; si no hay,
       default del repo, p.ej. `main`).
     - **Branch existente**: picker con búsqueda.
   - **Acceso**: `rw` (worktree exclusivo) o `ro` (worktree `--detach`, compartible).
     Puede derivarse del rol (Lector/Revisor → `ro`).

**Multi-repo** (coordinadora con hijas en varios repos): todas las hijas usan **el mismo
nombre de branch** por default (ej. `FIN-123-*`) para que el ticket quede coherente entre
repos; editable por hija.

**Al crear**:
- Sesión de trabajo → se crea el worktree y se **auto-arranca Claude Code** en él, sembrado
  con `description` + el preset del rol.
- Coordinadora → arranca su Claude Code (el orquestador), sin worktree.

**Afordancias** (del handoff): "+" arriba crea coordinadora root; "+" inline de una fila o
la fila punteada "+ Agregar sesión hija" crea hija de ese nodo (modal con `parentId`).

### Conflictos de branch (el caso `v2`)

- Crear `rw` sobre una branch **ya ocupada** por otro worktree (incluida la del repo
  principal, p.ej. `main`) → git falla. El IDE lo **detecta antes** y ofrece
  **"crear branch nueva a partir de ella"** (o cancelar). Nunca un error crudo.
- Crear `ro` sobre cualquier branch → siempre permitido (detached), aunque esté ocupada o
  ya haya otra `ro` sobre la misma. **Read-only = repetible.**
- Dos sesiones **`rw` sobre la misma branch** → imposible (regla de git); el picker marca
  las branches ocupadas.

## Roles (presets funcionales, extensibles)

Definidos en `.ide/config.toml`, cada rol = `{ model, system_prompt, read_only, tools? }`.
Presets de arranque:

| Rol | Acceso | Idea |
|-----|--------|------|
| Sin rol | rw | Claude Code default |
| Lector | ro | modelo barato, solo lectura |
| Revisor | ro | prompt de code review |
| Arquitecto | rw | prompt de diseño, modelo capaz |
| Diseñador | rw | enfoque frontend/UI |

Agregar un rol = una entrada en `.ide/config.toml`. Es el lugar natural donde configurás
**modelo + comportamiento** de cada Claude Code (lo que hoy hacés a mano con "el King").

## Ciclo de vida — cerrar

- **Sesión de trabajo `rw`**: al cerrar se **remueve el worktree**; la **branch se preserva**
  (los commits quedan). Si hay cambios sin commitear en el worktree → **advertir/confirmar**.
  Nunca toca la branch base ni `main`.
- **Sesión `ro`**: cerrar solo remueve el worktree detached (no hay nada que preservar).
- **Coordinadora**: al cerrar, **confirmar** qué pasa con las hijas (cerrarlas también vs
  dejarlas huérfanas). Las tareas en `.ide/tasks/` **persisten**.

## Extensión futura (anotada, fuera de R1)

- **Hook post-creación**: un **script configurable** (en `.ide/config.toml`) que el IDE
  corre al crear una sesión, p.ej. para **duplicar el stack** (DB clonada / docker / puertos),
  estilo finnecto. Encaja en el modelo de plugins/hooks.
- **Frontends por worktree**: técnica validada en finnecto — `Referer: localhost:3000` para
  que la API crea que todos los worktrees son el mismo origen, + **stacked branches** para
  que los cambios se propaguen. Referencia para la rebanada de "correr frontends aislados".

## Componentes (unidades)

### Backend (capacidades registradas como plugins)
| Unidad | Capacidad / qué hace |
|--------|----------------------|
| `capabilities/workspace.py` | `workspace.repos` — descubre repos del workspace (ya en R0). |
| `capabilities/sessions.py` | `sessions.tree` / `sessions.create` / `sessions.rename` / `sessions.close` — CRUD del árbol; persiste `.ide/sessions.json`. |
| `worktrees.py` | Crear/remover worktree (`rw` attach, `ro` --detach), detectar branch ocupada, listar branches. (Referencia: `worktrees.js`, `git.js` de finnecto.) |
| `roles.py` | Carga presets de `.ide/config.toml`; resuelve `{model, prompt, read_only}` por sesión. |

### Frontend
| Unidad | Qué hace |
|--------|----------|
| `modules/sessions/SessionsPanel` | Lista Repos + árbol recursivo (indent 16px/nivel), chevron, status dot, pill de rol, "+" inline y fila punteada. |
| `modules/sessions/NewSessionModal` | Modal con los campos del flujo; selector de branch nueva/existente con picker+búsqueda; marca branches ocupadas. |
| `state/sessions` | Estado del árbol, `activeSessionId`, edición inline (rename). |

## Flujo de datos

Crear: modal → `sessions.create(payload)` → backend valida (branch ocupada?), crea worktree
vía `worktrees`, arranca Claude Code, persiste `sessions.json`, responde el nodo → store
actualiza el árbol → render. Cambios de status llegan por `event` (WebSocket).

## Manejo de errores

- Branch ocupada → `error` tipado con la opción "crear branch nueva" (no un fallo crudo).
- Worktree/dir inexistente o git no disponible → `error` tipado, renderizado, nunca silencioso.
- `sessions.json` corrupto → backup + re-init con aviso, no crash mudo.

## Testing

- **Backend (pytest)**: crear `rw` sobre branch libre → worktree + branch; sobre branch
  ocupada → error con opción de branch nueva; crear `ro` dos veces sobre la misma branch →
  ambas ok (detached); rename recursivo; close preserva branch y advierte con cambios sin
  commitear.
- **Frontend (vitest/RTL)**: árbol recursivo renderiza con indent por profundidad; modal
  valida requeridos; picker marca branches ocupadas; rename inline (Enter commit / Esc cancel).

## Criterios de aceptación (R1 hecho)

1. `ide` descubre y muestra los repos del workspace.
2. Puedo crear una **coordinadora** (sin branch) y una **hija de trabajo** (worktree + branch).
3. **Branch nueva** con nombre editable + base elegible; **branch existente** vía picker.
4. Crear `rw` sobre branch ocupada → me ofrece **branch nueva** (no falla).
5. Crear `ro` repetido sobre la misma branch → funciona (detached).
6. Rename inline y selección funcionan; el árbol persiste en `.ide/sessions.json`.
7. Los roles cargan de `.ide/config.toml` y afectan la sesión (al menos read-only).
8. Tests de back y front pasan.

## Decisiones confirmadas

- **Auto-arrancar Claude Code al crear** la sesión, sembrado con `description` + rol. ✅
- **Cerrar**: remover worktree, **preservar la branch**, advertir si hay cambios sin
  commitear; nunca tocar base/`main`. ✅
- **`kind: dir`** (path arbitrario, no repo): soportado como working dir con terminales +
  Claude Code, sin branch/worktree. ✅

## Fuera de alcance (rebanadas posteriores)

Terminales/PTY (R2), chat con Claude (R3), diffs (R4), graphite (R5), tasks/notion/settings
(R6), y el stack pesado (DB/docker/puertos) como hook opcional.
