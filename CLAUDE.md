# CLAUDE.md — Agentic IDE (working name)

Instrucciones para cualquier agente que trabaje en este repo. Leé también `README.md` y
`docs/` antes de tocar código.

## Qué es

Un **IDE agéntico que corre en el navegador (localhost)** para orquestar **sesiones
paralelas de Claude Code** sobre múltiples repos y git worktrees. Backend **Python/FastAPI**,
frontend **React + Vite + TS**. Proyecto nuevo, separado de `finnecto-ide` (que se usa **solo
como referencia de dominio**, no como base de código).

## Reglas de oro (no negociables)

1. **Fidelidad de UI.** Se implementa contra el mockup (`docs/design/handoff/`), dirección
   visual **1a — Terminal/amber**, con los tokens exactos de `docs/design/REFERENCES.md`.
   Nada de estética "por defecto". La UI es prioridad del dueño del proyecto.
2. **TDD.** Test que falla → implementación mínima → test que pasa → commit. El plan ya viene
   en pasos TDD; seguilos.
3. **Rebanadas verticales.** Se construye por rebanadas (R0–R6, ver `docs/design/ROADMAP.md`),
   una a la vez. **R0 (Fundación) primero**; el resto se planifica sobre la realidad de R0.
   No planifiques rebanadas futuras en detalle antes de tiempo.
4. **Sin fallos silenciosos.** Todo error del backend viaja como envelope `{type:"error",
   payload:{code,message}}`; el frontend muestra "desconectado", no datos viejos como vivos.
5. **Extensibilidad primero.** Los 6 módulos del rail son plugins detrás de una interfaz
   común. Agregar un módulo (o un meta-agente futuro) = un `register` de cada lado.
6. **Usá superpowers.** Antes de trabajo creativo, brainstorming; para ejecutar planes,
   subagent-driven-development o executing-plans; para debugging, systematic-debugging.

## Decisiones de arquitectura ya tomadas (no re-litigar)

- **Claude Code local, NO Managed Agents.** Manejamos el binario `claude` local (Claude
  Agent SDK de Python, o CLI `--output-format stream-json`). Usa **tu login de Claude Code**
  (suscripción), **sin `ANTHROPIC_API_KEY`**. No usar el SDK `anthropic` (Messages API).
- **Workspace + `.ide/`.** La unidad de trabajo es un directorio con **`.ide/`** (contiene
  los repos). El comando `ide` lo detecta por walk-up (`ide init` lo crea). `.ide/` es
  **local, no se commitea**. Contenido: `config.toml`, `sessions.json`, `tasks/`, `worktrees/`.
- **Sesiones livianas** (worktree + branch + Claude Code). El stack pesado (DB/docker/puertos)
  es un **hook opcional** futuro, no parte de crear una sesión.
- **Modelo de sesión**: coordinadora (sin branch, comanda hijas multi-repo) vs de trabajo
  (**rw** = worktree exclusivo / **ro** = worktree `--detach`, repetible). El **repo principal
  no es una sesión** (se monitorea). Branch ocupada → ofrecer branch nueva (nunca fallar crudo).
- **Roles = presets funcionales** (`{model, system_prompt, read_only, tools}`) en
  `.ide/config.toml`, extensibles. **Permisos por sesión** (skip vs approve/deny inline),
  default desde el rol.

Detalle completo en `docs/superpowers/specs/` (R0 foundation, R1 sessions aprobado, R2
terminal, R3 chat).

## Estructura del código

- `server/` — backend Python (paquete `ide_server`), gestionado con **`uv`**.
- `ui/` — frontend React + Vite + TS.

## Cómo correr los tests

```bash
cd server && uv run pytest -v      # backend
cd ui && npm test                  # frontend (vitest)
```

## Estado actual

Diseño cerrado para R0–R3; **R4–R6** (diffs, graphite, tasks/notion/settings) por
especificar. **Próximo paso: ejecutar `docs/superpowers/plans/2026-07-08-r0-foundation.md`**
(16 tareas TDD) con subagent-driven-development.

## Commits

Conventional commits, atómicos, en español. Un commit por tarea del plan.
