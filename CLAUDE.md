# CLAUDE.md — Agentic IDE (working name)

Instrucciones para cualquier agente que trabaje en este repo. Lee también `README.md` y
`docs/` antes de tocar código.

**¿Te piden instalar, configurar o usar el IDE (no programarlo)?** Sigue «Primeros pasos» del
`README.md` en orden y, con `ide` ya instalado, lee la referencia completa con `ide docs`. El resto
de este archivo es para quien desarrolla el IDE.

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
   La UI es prioridad del dueño del proyecto. (Cambiado 2026-07-09.)
2. **TDD.** Test que falla → implementación mínima → test que pasa → commit. El plan ya viene
   en pasos TDD; síguelos.
3. **Rebanadas verticales.** Se construye por rebanadas (R0–R6, ver `docs/design/ROADMAP.md`),
   una a la vez. **R0 (Fundación) primero**; el resto se planifica sobre la realidad de R0.
   No planifiques rebanadas futuras en detalle antes de tiempo.
4. **Sin fallos silenciosos.** Todo error del backend viaja como envelope `{type:"error",
   payload:{code,message}}`; el frontend muestra "desconectado", no datos viejos como vivos.
5. **Extensibilidad primero.** Los 6 módulos del rail son plugins detrás de una interfaz
   común. Agregar un módulo (o un meta-agente futuro) = un `register` de cada lado.
6. **Usa superpowers.** Antes de trabajo creativo, brainstorming; para ejecutar planes,
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
  (`gh`) con polling.
- **Roles = presets funcionales** (`{model, system_prompt, read_only, tools}`) en
  `.ide/config.toml`, extensibles. **Permisos por sesión** (skip vs approve/deny inline),
  default desde el rol.

Cómo funciona hoy cada parte: `server/ide_server/REFERENCE.md` (`ide docs`). Las specs y planes viejos
(`docs/superpowers/`) se borraron el 2026-11-19; siguen en la historia de git.

## Estructura del código

- `server/` — backend Python (paquete `ide_server`), gestionado con **`uv`**.
- `ui/` — frontend React + Vite + TS.

## Glosario de la UI (usar estos nombres en código, docs y conversación)

**Desarrollo** = lo que está seleccionado para trabajar: una sesión, o una PR de las listas de la
sidebar (Revisiones / Mis PRs) que no tiene sesión.

De izquierda a derecha:

| Nombre | Componente | Qué es |
|---|---|---|
| Sidebar principal | `MainSidebar` (`ui/src/modules/sessions/`) | sesiones (★ principal, tickets, revisiones) + customizaciones abajo |
| Selector de desarrollo | `DevSelector` (`ui/src/layout/`) | card arriba del menú de acciones + sidebar interna con el desarrollo actual; click = lista de todos para cambiar |
| Menú de acciones | `ActionMenu` (`ui/src/layout/`) | columna angosta de íconos: colapsar, módulos, prompts |
| Sidebar interna | `InnerSidebar` (`ui/src/layout/`) | panel del módulo activo (ej. Terminal); colapsable |
| Panel principal | `MainPanel` (`ui/src/layout/`) | la sesión abierta (tabs `claude`, `TICKET.md`, scripts) |

**Convención de botones:** todo botón (y todo elemento clickeable con ícono) lleva `title` con
una explicación corta de qué hace. `HoverTips` (`ui/src/layout/`) la muestra como tooltip
dibujado en la página (sale en las capturas; el nativo del navegador no). En `QueueItemAction`
el `title` sale del `aria-label` si no se pasa.

## Probar en vivo (servidor de prueba)

Un IDE aparte en otro puerto, **contra una copia de la base** (si no, escribe en la real del usuario y
dos versiones distintas del IDE se pisan los estados):

```bash
cp <workspace>/.ide/ide.db /tmp/ide-copia.db
cd server && IDE_DB_PATH=/tmp/ide-copia.db uv run ide run --cwd <workspace> --port 8799 --no-browser --no-supervise
```

Ojo: igual comparte los worktrees, los servidores y las sesiones reales. Antes de elegir una sesión en
la UI de prueba, deja sus tabs sin la de `claude` (`ide.devTabs` en localStorage): abrirla lanza un
`claude` duplicado de esa sesión. No toques acciones que publican en GitHub.

## Cómo correr los tests

```bash
cd server && uv run pytest -v      # backend
cd ui && npm test                  # frontend (vitest)
```

## Estado actual

El IDE está en uso diario sobre sesiones-carpeta (los módulos viejos quedan ocultos vía `[ui] modules` en
`.ide/config.toml`). Lo que hace hoy está en `ide docs`; el historial de cambios, en `git log`.

## Documentación del IDE

`server/ide_server/REFERENCE.md` (se imprime con `ide docs`) es la referencia para que un agente
configure y opere el IDE. **Todo cambio de comportamiento visible (flags, config, plantillas,
permisos, estados, errores) actualiza ese archivo en el mismo commit.**

## Commits

Conventional commits, atómicos, en español. Un commit por tarea del plan.
