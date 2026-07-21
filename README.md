# Agentic IDE (working name)

> Nombre de trabajo — renombrable. Raíz del proyecto: `~/dev/ide`.

Un IDE **agéntico** que corre en el **navegador (localhost)** para orquestar **sesiones
paralelas de Claude Code** sobre múltiples repos y git worktrees, cada una aislada.
Backend en **Python (FastAPI)**, frontend en **React + Vite**, terminales por
**WebSocket → xterm.js**. Todo pasa por **Claude Code local** (no Managed Agents).

Este proyecto es **nuevo y separado** de `finnecto-ide`. Toma a finnecto-ide únicamente
como **referencia de dominio** (worktrees, árbol recursivo de sesiones, graphite,
parseo de transcripts), no como base de código.

## Layout

Tres regiones (según el mockup, dirección visual **1a — Terminal/amber**):

1. **Sidebar de sesiones** (izq): repos + árbol recursivo de sesiones + customizations.
2. **Rail de actividad + panel** (medio): 6 módulos (Search, Changed files, Graphite,
   Tasks, Terminal, Notion) — **extensibles vía plugins**.
3. **Panel principal** (der): chat con Claude por defecto; abrir archivo/tarea/branch/
   terminal/página lo convierte en una pestaña.

## Stack

| Capa | Elección |
|------|----------|
| Backend | Python + FastAPI (async, WebSocket) |
| Frontend | React + Vite + TypeScript |
| Terminales | PTY local ↔ WebSocket ↔ xterm.js |
| Claude Code | CLI local (programático + PTY), **no** Managed Agents |
| Tiempo real | WebSocket (streams de PTY, chat y sync de estado) |

## Documentación

- **`docs/ide-handoff.md`** — guía para agentes: cómo operar y hacer handoff al IDE (también `ide help`).
- `docs/superpowers/HANDOFF.md` — estado vivo del desarrollo y próximos pasos.
- `docs/design/handoff/HANDOFF.md` — spec de diseño (fuente de verdad, alta fidelidad).
- `docs/design/handoff/mockup.dc.html` — prototipo interactivo (formato propietario `.dc.html`).
- `docs/design/ROADMAP.md` — descomposición en rebanadas (R0–R6).
- `docs/design/REFERENCES.md` — tokens 1a, mapeo a módulos de finnecto, integración con Claude Code.
- `docs/superpowers/specs/` — specs por rebanada. Empezamos por **R0 (Fundación)**.

## Cómo correr

**Requisitos:** [`uv`](https://docs.astral.sh/uv/), Node + npm, y el binario `claude` de Claude
Code en el PATH, logueado por suscripción (**sin `ANTHROPIC_API_KEY`**).

### Un comando levanta todo

```bash
cd server && uv run ide build     # buildea el frontend y lo empaqueta en ide_server/web/
uv tool install ./server          # deja `ide` en el PATH con el frontend adentro

ide run --cwd /ruta/a/tu/workspace   # sirve todo en http://127.0.0.1:8787
```

`ide run` auto-crea `.ide/` si falta y abre el navegador (`--no-browser` lo evita).

### Desarrollo (hot-reload de la UI)

```bash
cd server && uv run ide run --cwd <ws> --no-browser   # backend + frontend servido
cd ui && npm run dev                                   # Vite en :5173 con hot-reload
```

En dev abrí `:5173` (Vite); el WebSocket del frontend siempre pega a `:8787`.

## Tests

```bash
cd server && uv run pytest -q     # backend
cd ui && npm test                 # frontend (vitest)
```

## Estado

En desarrollo activo. Rebanadas cerradas end-to-end: **R0** (fundación), **R1** (sesiones),
**R2** (terminal), **R3** (chat), **UI shadcn/1a**, **R4** (changed files + diff), **R5a**
(graphite stack), **R6** (settings/customizations), **Notion Fase 1 y 2**, **Orquestación entre
sesiones Fase 1** (coordinadora comanda hijas vía MCP), **Tasks Fase 1** (markdown local).

El estado vivo y los próximos pasos están en **`docs/superpowers/HANDOFF.md`** (fuente de verdad
para retomar). Pendiente prioritario: **arranque con un solo comando `ide`** (servir el frontend
desde el backend + auto-init de `.ide/`).
