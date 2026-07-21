# Roadmap — rebanadas verticales

El producto se construye en **rebanadas verticales**: cada una es entregable y funciona
por sí sola, y se especifica → planifica → implementa en su propio ciclo. Cada rebanada
se apoya en la **Fundación (R0)** y en las anteriores.

La lógica de dominio se **porta desde finnecto-ide como referencia** (ver
`REFERENCES.md`), reescrita en Python — no se copia código Node.

> **Estado vivo:** este documento es el plan original + su estado. El detalle de qué se
> construyó y los próximos pasos concretos se mantienen en `docs/superpowers/HANDOFF.md`
> (fuente de verdad para retomar).

## Plan original (R0–R6)

| # | Rebanada | Qué entrega | Estado |
|---|----------|-------------|--------|
| **R0** | **Fundación** | FastAPI + WebSocket, shell React de 3 regiones, **theming 1a**, arquitectura de estado, **esqueleto de plugins**, "esqueleto que camina". | ✅ hecho |
| R1 | Sidebar de sesiones | Árbol recursivo de sesiones, repos, modal nueva-sesión, rename inline. Worktrees por sesión. | ✅ hecho |
| R2 | Terminal | PTY local ↔ WebSocket ↔ `xterm.js`; card de contexto; branch selector. | ✅ hecho |
| R3 | Chat | **Claude Code local** (sesión programática); mensajes, chips de tool calls + edits, tokens; composer. | ✅ hecho |
| R4 | Changed files + File diff | Lista de archivos cambiados (+/-); vista de diff. | ✅ hecho |
| R5 | Graphite + Branch detail | Branch-stack lineal, expand a commits/archivos, restack. | ⏳ **R5a hecho** (lectura + restack); **R5b pendiente** (checkout + submit) |
| R6 | Tasks + Notion + Settings | Módulo Tasks, Notion editable, Settings + Customizations. | ✅ Settings/Customizations + Notion + Tasks hechos (ver abajo) |

## Rebanadas más allá del plan original

A partir de R6 el trabajo se descompuso en rebanadas más finas y se sumaron algunas nuevas:

| Rebanada | Qué entrega | Estado |
|----------|-------------|--------|
| UI shadcn/1a | Migración de la identidad 1a a shadcn/ui + Tailwind. | ✅ hecho |
| Settings + Customizations | Modal de Settings + footer Customizations (catálogo global read-only). | ✅ hecho |
| R-Notion Fase 1 | Lista curada de páginas + render BlockNote + edición de texto (API oficial). | ✅ hecho |
| R-Notion Fase 2 | Edición estructural (agregar/borrar bloques, título, checkbox). | ✅ hecho |
| Orquestación Fase 1 | Meta-agente: la coordinadora comanda hijas vía MCP `orq` (`ask_session`/`spawn`). | ✅ hecho (E2E en vivo) |
| Tasks Fase 1 | Gestor de tareas markdown local en `.ide/tasks/` (listar/crear/editar). | ✅ hecho |
| Arranque de un comando | `ide run` sirve frontend+backend en un puerto; `ide build`; instalable global. | ✅ hecho |
| `ide` multi-instancia | Puerto dinámico + `ide ls` + WS same-origin; `ide help` + guía de handoff. | ✅ hecho |

### Pendientes (requieren brainstorming/spec — ver HANDOFF)

- **`ide setup` — traspaso desde otro entorno** (DX de onboarding): detectar worktrees existentes
  (worktrees de **Conductor** en `~/.conductor/…`/`~/conductor/workspaces/…`, y `git worktree list`
  en general) y **adoptarlos como sesiones** del IDE en `.ide/sessions.json`, apuntando a los
  worktrees en su lugar. Interactivo: mostrar lo detectado y confirmar qué importar. **Fase 2:**
  detectar sesiones de **Claude Code** (`~/.claude/projects/…/*.jsonl`) y **resumir la conversación**
  (SDK `resume` por session_id). Nota: el modelo hoy asume worktrees bajo `.ide/worktrees/`; adoptar
  ajenos requiere permitir `worktreePath` fuera de ahí.
- **R5b** — acciones de Graphite (checkout de branch + submit de PRs vía `gh`).
- **Orquestación Fase 2** — `answer_gate` (permisos con humano en el loop), `close_session`,
  timeouts de `ask`, buzón simétrico, panel de orquestación en vivo.
- **Tasks Fase 2** — borrar, render estructurado, cambiar status desde el rail, que una sesión
  cree/actualice tareas vía tool.
- **Observabilidad / langwatch** — enganchar tracing/eval de las sesiones sobre el `SessionHub`.

## Principios

- **Fidelidad de UI (no negociable)**: cada rebanada se implementa contra el mockup
  (`docs/design/handoff/`), dirección visual **1a — Terminal/amber**, con los tokens de
  `REFERENCES.md`. Alta fidelidad: colores, tipografía, spacing, radii e interacciones se
  reproducen con precisión. Prohibida la estética "por defecto".
- **Extensibilidad primero**: los módulos del rail son plugins detrás de una interfaz
  común (definida en R0). Agregar un módulo nuevo — o mañana un meta-agente LangGraph por
  encima de Claude Code — es un plugin, no una cirugía.
- **Aislamiento real**: cada sesión vive en su worktree; DB clonada / docker / puertos
  quedan para rebanadas posteriores (igual que finnecto), no en R0.
- **Un spec por rebanada**: nada de un spec gigante. R0 primero; el resto se especifica
  cuando le toca.
