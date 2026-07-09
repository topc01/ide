# R2 — Terminal · Design

Fecha: 2026-07-08 · Estado: **en revisión** · Rebanada: R2 del `docs/design/ROADMAP.md`.
Depende de: R0 (Fundación), R1 (Sesiones).

## Objetivo

El módulo **Terminal** del rail y el streaming de PTYs locales. Permite **abrir terminales
on-demand** desde el `cwd` de la sesión seleccionada, verlas en el panel principal como
pestañas, e interactuar en tiempo real (bytes en ambos sentidos, resize, ciclo de vida).

## Fidelidad de UI (prioridad)

Contra el mockup 1a (`docs/design/handoff/`, tokens en `REFERENCES.md`). Terminal body
`#0f0e0c`, path en accent, comandos en texto primario, output muted, éxito verde; prompt
`$` con **cursor accent parpadeante** (`@keyframes blink`, ~1.1s). Header: `cwd` mono muted
+ chip de branch.

## Modelo

- **Terminal es un módulo del rail** (no se auto-crea por sesión). Al seleccionar una sesión,
  el módulo muestra un **card de contexto** (nombre + `cwd`) y la **lista de terminales
  abiertas** de esa sesión.
- Un botón **"+"/abrir** crea una terminal nueva: un **PTY** con el shell (`zsh` por default)
  en el **`cwd` de la sesión** (su worktree, o el dir del repo si es una terminal del repo
  principal monitoreado). Clic en una terminal la abre como **pestaña** en el panel principal.
- Una terminal = un PTY con un comando (shell por default; también procesos como
  `npm run dev`, `vitest --watch`). Un punto de color marca procesos corriendo.
- **Scope**: las terminales pertenecen a la sesión activa. El **repo principal** (monitoreado,
  sin sesión) también puede abrir su terminal desde la lista Repos.

### Branch en el header
- Terminal de **sesión**: branch es **display** (la del worktree, inmutable).
- Terminal del **repo principal**: el picker con búsqueda puede hacer `checkout` real, y
  **marca las branches ocupadas** por worktrees (reusa la lógica de R1). *(Simple en R2.)*

### Terminales de arranque (opcional)
`.ide/config.toml` puede declarar comandos que se abren al entrar a una sesión (ej.
`npm run dev`). **Default: manual** (solo se abre lo que pedís). Extensible.

## PTY ↔ WebSocket ↔ xterm.js

- **Backend**: gestor de PTYs (stdlib `pty`/`os.openpty` + asyncio `add_reader`, o
  `ptyprocess`). Cada terminal tiene un `id`. Referencia: `term.js` de finnecto (patrón
  `node-pty`).
- **Canal WS por terminal**: mensajes `terminal.data` (bytes salida→cliente y entrada→PTY),
  `terminal.resize` (`cols`, `rows`), `terminal.exit`. Usa el envelope de R0 con un
  `channel` por terminal id; el payload de datos va en base64/texto.
- **Frontend**: `xterm.js` + addon fit; envía input y resize, pinta la salida. Estilo 1a.
- **Ciclo de vida**: cerrar la pestaña/terminal **mata el proceso** y libera el PTY.

## Persistencia

La **lista** de terminales por sesión (nombre/comando) se persiste en `.ide/sessions.json`
(runtime, local). Los **procesos** son runtime: al reabrir el IDE, la lista se muestra pero
los PTYs no se re-lanzan automáticamente (se relanzan al abrir la terminal).

## Componentes (unidades)

### Backend
| Unidad | Qué hace |
|--------|----------|
| `capabilities/terminals.py` | `terminal.open` (spawn PTY en cwd), `terminal.write`, `terminal.resize`, `terminal.close`, `terminal.list`. Gestiona el ciclo de vida de los PTYs. |
| `pty_manager.py` | Wrapper de PTY sobre asyncio: crear, leer no-bloqueante, escribir, resize (`TIOCSWINSZ`), matar. |

### Frontend
| Unidad | Qué hace |
|--------|----------|
| `modules/terminal/TerminalPanel` | Módulo del rail: card de contexto de la sesión activa + lista de terminales + abrir. |
| `main/TerminalTab` | `xterm.js` montado, conectado al canal WS del terminal id; maneja input/resize/salida. |
| `transport/terminalChannel` | Suscripción al canal WS de una terminal; encode/decode de datos. |

## Flujo de datos

Abrir: `terminal.open({sessionId})` → backend spawnea PTY en el cwd, responde `{id}` →
frontend abre `TerminalTab`, se suscribe al canal → bytes fluyen por WS. Resize del contenedor
→ `terminal.resize`. Cerrar → `terminal.close` → mata proceso.

## Manejo de errores

- Fallo al spawnear el PTY (shell inexistente, cwd inválido) → `error` tipado, renderizado
  en la pestaña, nunca silencioso.
- WS caído → el `TerminalTab` muestra "desconectado" y reintenta; no pinta output viejo como
  vivo.

## Testing

- **Backend (pytest)**: abrir PTY con `echo hola` → la salida contiene `hola`; resize aplica
  `cols/rows`; close mata el proceso (PID no vive). 
- **Frontend (vitest/RTL)**: `TerminalPanel` lista terminales de la sesión activa; abrir
  agrega una pestaña; el canal encode/decodea datos correctamente.

## Criterios de aceptación (R2 hecho)

1. Selecciono una sesión → el módulo Terminal muestra su `cwd` y sus terminales.
2. Abro una terminal → PTY en el `cwd` correcto, interactiva (escribo, veo salida), estilo 1a.
3. Resize funciona; cerrar mata el proceso.
4. Terminal del repo principal disponible desde la lista Repos.
5. Tests de back y front pasan.

## Fuera de alcance

Chat con Claude (R3), diffs (R4), graphite (R5), tasks/notion (R6). El branch-switcher
avanzado y las terminales de arranque ricas quedan como extensión.
