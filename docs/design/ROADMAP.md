# Roadmap — rebanadas verticales

El producto se construye en **rebanadas verticales**: cada una es entregable y funciona
por sí sola, y se especifica → planifica → implementa en su propio ciclo. Cada rebanada
se apoya en la **Fundación (R0)** y en las anteriores.

La lógica de dominio se **porta desde finnecto-ide como referencia** (ver
`REFERENCES.md`), reescrita en Python — no se copia código Node.

| # | Rebanada | Qué entrega | Referencia finnecto |
|---|----------|-------------|---------------------|
| **R0** | **Fundación** | FastAPI + WebSocket, shell React de 3 regiones, **theming 1a**, arquitectura de estado, **esqueleto de plugins** (los 6 módulos como slots), y un "esqueleto que camina" (listar repos reales de punta a punta). | `git.js`, `developments.js` |
| R1 | Sidebar de sesiones | Árbol recursivo de sesiones, lista de repos, modal nueva-sesión, rename inline, selección. Worktrees por sesión (`<dir>/.wt/<slug>`, branch `<slug>-wt`). | `sessions.js`, `worktrees.js`, `developments.js` |
| R2 | Terminal | PTY local ↔ WebSocket ↔ `xterm.js`; card de contexto de la sesión activa; branch selector con búsqueda. | `term.js` (patrón `node-pty`) |
| R3 | Chat | Manejar **Claude Code local** (sesión programática); render de mensajes, chips de tool calls + edits (+/-), footer de tokens; composer. | `transcript.js`, `orq.js`, `conductor.js` |
| R4 | Changed files + File diff | Lista de archivos cambiados (+/-); vista de diff con líneas add/del/context. | `git.js` |
| R5 | Graphite + Branch detail | Branch-stack lineal, expand a commits, expand a archivos; vista de detalle de branch. | `graphite.js` |
| R6 | Tasks + Notion + Settings | Módulo Tasks (markdown), Notion (páginas editables), modal de Settings + footer Customizations (8 items). | (nuevo) |

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
