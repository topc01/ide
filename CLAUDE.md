# CLAUDE.md — Agentic IDE (working name)

Instrucciones para cualquier agente que trabaje en este repo. Leé también `README.md` y
`docs/` antes de tocar código.

## Qué es

Un **IDE agéntico que corre en el navegador (localhost)** para orquestar **sesiones
paralelas de Claude Code** sobre múltiples repos y git worktrees. Backend **Python/FastAPI**,
frontend **React + Vite + TS**. Proyecto nuevo, separado de `finnecto-ide` (que se usa **solo
como referencia de dominio**, no como base de código).

## Reglas de oro (no negociables)

1. **Fidelidad de UI.** Identidad visual **1a — Terminal/amber** (paleta ámbar/terminal,
   tokens en `docs/design/REFERENCES.md`) implementada vía **shadcn/ui + Tailwind**:
   componentes con el look/pulido nativo de shadcn, **tematizados** a los tokens 1a. El
   mockup (`docs/design/handoff/`) es **referencia de layout/identidad**, no objetivo pixel.
   La UI es prioridad del dueño del proyecto. (Cambiado 2026-07-09; ver
   `docs/superpowers/specs/2026-07-09-ui-shadcn-design.md`.)
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
- **Workspace + `.ide/`** (local, no se commitea). El comando `ide` lo detecta por walk-up
  (`ide init` lo crea). Contenido: `config.toml`, `sessions/`, `worktrees/`, `scripts/`,
  `permissions/`, `tasks/`.
- **Sesión = carpeta** `.ide/sessions/<id>/` con un `claude` **interactivo** en un PTY del
  server. Kinds `main/ticket/review`. Repos = worktrees en `.ide/worktrees/<id>/<repo>`
  enlazados por symlink; scripts por repo en `.ide/scripts/<repo>/` (`setup`, `run`, ...).
  CLI `ide session|repo|script`; despacho por plantilla, `max_running`, revisiones de PR
  (`gh`) con polling. Spec: `docs/superpowers/specs/2026-10-13-sesiones-carpeta-design.md`.
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
especificar. **Sesiones-carpeta hechas** (backend + UI; los módulos viejos quedan ocultos vía
`[ui] modules` en `.ide/config.toml`). Próximo: chat propio sobre sesiones-carpeta y
re-habilitar módulos ocultos; ver `docs/superpowers/HANDOFF.md`.

## Documentación del IDE

`server/ide_server/REFERENCE.md` (se imprime con `ide docs`) es la referencia para que un agente
configure y opere el IDE. **Todo cambio de comportamiento visible (flags, config, plantillas,
permisos, estados, errores) actualiza ese archivo en el mismo commit.**

## Commits

Conventional commits, atómicos, en español. Un commit por tarea del plan.
