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

- `docs/design/handoff/HANDOFF.md` — spec de diseño (fuente de verdad, alta fidelidad).
- `docs/design/handoff/mockup.dc.html` — prototipo interactivo (formato propietario `.dc.html`).
- `docs/design/ROADMAP.md` — descomposición en rebanadas (R0–R6).
- `docs/design/REFERENCES.md` — tokens 1a, mapeo a módulos de finnecto, integración con Claude Code.
- `docs/superpowers/specs/` — specs por rebanada. Empezamos por **R0 (Fundación)**.

## Estado

En diseño. La primera rebanada a implementar es **R0 — Fundación**
(ver `docs/superpowers/specs/2026-07-07-foundation-design.md`).
