# Handoff — estado del proyecto (Agentic IDE)

> Última actualización: 2026-07-18. Documento vivo para retomar en otra sesión sin recontexto.

## Dónde estamos

**R5a Graphite stack (lectura) + restack: COMPLETO y mergeado a `main`** (merge `1e75aa7`).

Rebanadas cerradas end-to-end: **R0** (fundación), **R1** (sesiones), **R2** (terminal),
**R3** (chat), **UI shadcn/1a** (identidad ámbar/terminal), **R6** (settings/customizations),
**R4** (changed files + diff), **R5a** (graphite stack lectura + restack).

## Qué se construyó en R5a (último trabajo)

Ítem "Graphite" del rail (antes stub): **stack de branches** del repo de la sesión activa,
todo inline en una columna — branch → (expand) commits → (expand) archivos → (click) diff del
archivo *en ese commit*. Marca branches desactualizadas (`needsRestack`, conector punteado) y
permite **restackear** con confirmación.

- **Backend** (`server/ide_server/`): `graphite.py` — `read_stack` lee el **SQLite de gt**
  (`<repo>/.git/.graphite_metadata.db`, tabla `branch_metadata`) vía `sqlite3` stdlib;
  `build_stack` (puro) arma el stack ordenado con `needsRestack` (parentRevision registrada ≠
  tip actual del padre); `branch_commits`/`commit_files` de git (reusa `git.parse_numstat`);
  `restack` corre `gt restack --branch X --only --no-interactive -q` con `rebase --abort`
  defensivo. Helper `workspace.resolve_repo` (repo de la sesión, no worktree).
  `git.file_diff_at_commit` (`git show <sha>`) + `changes.diff` acepta `sha`. Capability
  `graphite.stack/branch/restack` en `app.py`. Errores gt/git → envelope.
- **Frontend** (`ui/src/`): transport `graphiteChannel.ts` + `changesChannel.fetchDiff` con
  `sha`; store `state/graphite.ts` (load/toggleBranch/toggleCommit/restack, guard de sesión
  anti-race, invalida cache tras restack); `modules/graphite/GraphitePanel.tsx` (stack inline,
  conector punteado en needsRestack, flecha de restack con confirmación inline, click archivo
  abre tab); `DiffTab` extendido para el id `diff:<sessionId>:@<sha>:<path>` (diff por commit).

Spec: `docs/superpowers/specs/2026-07-18-r5a-graphite-stack-design.md`.
Plan: `docs/superpowers/plans/2026-07-18-r5a-graphite-stack.md` (10 tareas TDD, todas hechas).
Verificación al mergear: backend `uv run pytest -q` → **125 passed**; frontend `npm test` →
**108 passed**, `tsc --noEmit` limpio.

Deuda menor de R5a logueada (no bloqueante, → R5b/follow-up): `build_stack` tiene un guard
muerto en `visit()` (el pre-loop ya valida); `resolve_repo` sin-repoId no testeado y su
`KeyError` viaja como `unknown_channel` (taxonomía de `bus.py`, predata R5a); `restack` sin
timeout de subprocess; `graphite.branch` devuelve `[]` para branch desconocida; segundo trunk
se dropea en silencio en `build_stack`; `GraphitePanel` fallback `?? ""` inalcanzable.

## Qué se construyó en R4

Módulo "Changed files" del rail (antes stub) + tab de diff, contra el **worktree de la sesión
activa**.

- **Backend** (`server/ide_server/`): `git.py` (port puro de `finnecto/git.js`: parsers de
  numstat/porcelain/diff, `repo_status`, `file_diff_full`, `GitError`); helper compartido
  `workspace.resolve_cwd` (extraído de `terminals`); capability `changes.list`/`changes.diff`
  (`capabilities/changes.py`) registrada en `app.py`. Errores git → envelope `handler_error`.
- **Frontend** (`ui/src/`): transport `transport/changesChannel.ts` + store `state/changes.ts`
  (con guard de sesión anti-race y limpieza de estado en error); `modules/changes/ChangesPanel.tsx`
  (lista +/−, branch/totales, **polling 4s**, estado neutro sin sesión, click abre tab
  `diff:<sessionId>:<status>:<path>`); `main/DiffTab.tsx` (diff de archivo completo resaltado,
  `git diff HEAD -U1000000`) ruteado en `MainPanel.tsx`.

Spec: `docs/superpowers/specs/2026-07-17-r4-changed-files-diff-design.md`.
Plan: `docs/superpowers/plans/2026-07-17-r4-changed-files-diff.md` (8 tareas TDD, todas hechas).
Verificación al mergear: backend `uv run pytest -q` → **110 passed**; frontend `npm test` →
**91 passed**, `tsc --noEmit` limpio.

Deuda menor de R4 logueada (no bloqueante): `git.py` traga `OSError` (port fiel) y emite una
línea `add` vacía final en untracked; error "session not found" viaja como `unknown_channel`
(taxonomía de `bus.py`, predata R4); botón refrescar no guarda sesión null (enmascarado por
render condicional); `DiffTab.parseId` no maneja ids malformados.

## Qué se construyó en R6

Footer de 9 items de customizations al pie del sidebar de sesiones + modal read-only con el
catálogo **global** de Claude Code (`~/.claude/*`, `~/.ide/config.toml`, PRESETS de roles),
marcando lo que está **en uso** en el workspace actual.

- **Backend** (`server/ide_server/customizations/`): lectores puros inyectables (`home: Path`)
  para roles, mcp, instructions, hooks, skills, agents, plugins, tools; `build_items` arma los
  9 items normalizados `{key, title, description, count, rows:[{label, inUse}]}`. Capability
  `customizations.list` registrada en `app.py`.
- **Frontend** (`ui/src/`): transport `transport/settingsChannel.ts` + store `state/settings.ts`
  (Zustand); `modules/settings/SettingsModal.tsx` (nav izq + panel der + badge "en uso");
  `modules/settings/CustomizationsFooter.tsx` (fetch al montar → 9 items clickeables) integrado
  en `modules/sessions/SessionsPanel.tsx`; modal montado en `App.tsx`.
- **Orden fijo de los 9 items**: `overview, roles, agents, skills, instructions, hooks, mcp,
  plugins, tools`.

Plan: `docs/superpowers/plans/2026-07-13-settings-customizations.md` (8 tareas, todas hechas).
Spec: `docs/superpowers/specs/2026-07-13-settings-customizations-design.md`.

## Verificación (verde al mergear)

- Backend: `cd server && uv run pytest -q` → **95 passed**.
- Frontend: `cd ui && npm test` → **80 passed (30 files)**; `npx tsc --noEmit` limpio; `npm run build` ok.
- E2E en vivo verificado con Playwright: footer con counts reales (Overview 8, Roles 4,
  Agents 15, Skills 2, Hooks 3, Plugins 3, Tools 12), modal de Roles con badge "en uso" en
  `lector` y `arquitecto` (roles asignados a sesiones del workspace demo `~/ide-demo`).

## Cómo correr

```bash
# backend + workspace demo (tiene .ide/ con sesiones sembradas)
cd server && uv run ide --cwd ~/ide-demo --no-browser
# frontend
cd ui && npm run dev   # http://localhost:5173  (backend en :8787)
```

## Próximos pasos (sin especificar aún — requieren brainstorming/spec antes de codear)

- **R5b — acciones de Graphite**: checkout de branch + submit (crea/actualiza PRs vía `gh`,
  outward-facing → confirmaciones/auth). El decidido en el brainstorming de R5: R5a (lectura +
  restack) ya está; R5b son las acciones que faltan. Resolver conflictos de restack in-app
  también queda acá.
- **Tasks + Notion** (ítems del rail, hoy stubs "próximamente"; eran parte del R6 original, no
  construidos).
- Deuda menor: el `<aside>` de `SessionsPanel` es `overflow-auto` + footer `mt-auto`; con
  muchas sesiones el footer scrollea con el contenido (aceptable por ahora, no bloqueante).
- Chunk del build > 500 kB (warning de Vite, no error) — code-split si molesta.

## Reglas del repo (recordatorio)

- TDD estricto, un commit por tarea, conventional commits **en español**.
- Sin fallos silenciosos: errores viajan como envelope `{type:"error",...}`; el front muestra
  "desconectado", no datos viejos como vivos.
- UI: identidad **1a ámbar/terminal** vía shadcn/Tailwind, tokens en `docs/design/REFERENCES.md`.
- Claude Code local (login/suscripción), **sin `ANTHROPIC_API_KEY`**, no Managed Agents.
- Ver `CLAUDE.md` para las reglas completas y decisiones ya tomadas (no re-litigar).
