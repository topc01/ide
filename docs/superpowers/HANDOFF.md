# Handoff — estado del proyecto (Agentic IDE)

> Última actualización: 2026-07-19. Documento vivo para retomar en otra sesión sin recontexto.

## Dónde estamos

**R-Notion Fase 2 (edición estructural): COMPLETO y mergeado a `main`** (merge `49996ea`).

Rebanadas cerradas end-to-end: **R0** (fundación), **R1** (sesiones), **R2** (terminal),
**R3** (chat), **UI shadcn/1a** (identidad ámbar/terminal), **R6** (settings/customizations),
**R4** (changed files + diff), **R5a** (graphite stack lectura + restack), **R-Notion Fase 1**
(lectura + edición de texto de páginas de Notion).

## Qué se construyó en R-Notion Fase 1 (último trabajo)

Ítem "Notion" del rail (antes stub): **lista curada** de páginas por URL, que se abren
renderizadas con **BlockNote** (editor de bloques estilo Notion) y permiten **editar el texto
de bloques existentes** sincronizado a la **API oficial** de Notion, respetando ~3 rps.

- **Backend** (`server/ide_server/notion/`): `config.py` (token en `~/.ide/config.toml
  [notion].token` global, override local/env); `refs.py` (parse de URL + lista curada en
  `.ide/notion.json`); `adapter.py` **puro** (bloques Notion↔BlockNote inline+block, id de
  bloque preservado, `diff_text_ops`); `queue.py` (`RateLimitedRunner` ≤3 rps + retry 429
  acotado); `client.py` (SDK oficial `notion-client`: `fetch_page` paginado, `patch_block_text`
  que traduce 429→backoff). Capability `notion.health/list/add/remove/page/save` en `app.py`.
- **Frontend** (`ui/src/`): transport `notionChannel.ts` + store `state/notion.ts`;
  `modules/notion/NotionPanel.tsx` (lista, "+ por URL", estado "conectá Notion");
  `main/NotionEditor.tsx` (aísla BlockNote) + `main/NotionPageTab.tsx` (carga, **save con
  debounce ~800ms**, banner de cambio estructural + re-sync con `syncKey`, título read-only)
  ruteado en `MainPanel`. Deps nuevas: `@blocknote/core|react|mantine`@0.51.4.

Spec: `docs/superpowers/specs/2026-07-18-rnotion-fase1-design.md`.
Plan: `docs/superpowers/plans/2026-07-18-rnotion-fase1.md` (12 tareas TDD, todas hechas).
Verificación al mergear: backend `uv run pytest -q` → **150 passed**; frontend `npm test` →
**122 passed**, `tsc --noEmit` limpio, `npm run build` ok.

**Conectar Notion in-app (mergeado, `6dac9b9`):** mejora chica encima de la Fase 1 — el panel
tiene una **vista de conexión** (input de token password + "Conectar" + link a
`notion.so/my-integrations`) y "Desconectar". Capability `notion.connect {token}` valida el token
con `users.me` (distingue 401/403 de error de red) y solo persiste si es válido, escribiendo
`~/.ide/config.toml [notion].token` con `tomli-w` (preserva otras secciones); `notion.disconnect`
lo limpia. Verificado en vivo: token inválido → `connected:false`, no persiste.
Spec: `docs/superpowers/specs/2026-07-18-notion-connect-design.md`; plan:
`docs/superpowers/plans/2026-07-18-notion-connect.md`.

Config para probar en vivo: crear una integración interna en `notion.so/my-integrations`, pegar
su secret en el panel "Conectar Notion" (o a mano en `~/.ide/config.toml`), y compartir una
página con la integración antes de agregarla por URL.

## Qué se construyó en R-Notion Fase 2 (último trabajo, merge `49996ea`)

Edición **estructural** de páginas: agregar y borrar bloques, y editar el título — todo
persistido en la API oficial. **Alcance: agregar + borrar + título, SIN reordenar** (Notion no
tiene endpoint "mover"; reordenar sería borrar+recrear, destructivo).

- **Backend** (`server/ide_server/notion/`): `adapter.diff_ops(loaded, edited, unsupported_ids,
  id_map)` **puro** reemplaza a `diff_text_ops` — emite ops `append`/`delete`/`patch`; resuelve
  `clientId→notionId` con `id_map` (un bloque nuevo ya subido = PATCH, no re-APPEND); el `after`
  de un nuevo = id del bloque previo, y nuevos consecutivos encadenan; **nunca borra bloques no
  soportados**; PATCH dispara por cambio de `content` **o** de props. `client.append_block`
  (devuelve id minteado), `delete_block`, `set_page_title`, helper `_reraise_rate_limit`
  (429→RateLimited); `patch_block_text` acepta `props` y manda `checked`/`language`. Capability
  `notion.save` reescrita (aplica ops en orden vía `RateLimitedRunner`, mintea ids, resuelve
  `after`, best-effort → `{appended,deleted,patched,failed}`) + canal `notion.setTitle`.
- **Frontend** (`ui/src/`): `notionChannel.savePage` con `idMap` + `setTitle`; `NotionPageTab`
  mantiene el `idMap`, título **editable** (input, guarda on blur), **sin remontar el editor en
  el camino feliz** (cursor preservado; re-fetch de reconciliación solo si una op falla). Se
  eliminó el banner de "Fase 2".

Spec: `docs/superpowers/specs/2026-07-19-rnotion-fase2-design.md` (incluye "Limitaciones
conocidas"). Plan: `docs/superpowers/plans/2026-07-19-rnotion-fase2.md` (5 tareas TDD + fast-follow).
Verificación al mergear: backend `uv run pytest -q` → **184 passed**; frontend `npm test` →
**130 passed**. Ejecutado con subagent-driven-development (review por tarea + review final en opus,
aprobado sin bloqueantes).

**Fast-follow ya incluido:** togglear el checkbox de un `to_do` existente (y cambiar
`code.language`) **se persiste** — el diff compara props además del texto. **Limitación que queda:**
cambiar el *tipo* de un bloque existente con texto idéntico (paragraph→heading) no se persiste
(Notion `blocks.update` no cambia el tipo; requeriría borrar+recrear).

Deuda menor de R-Notion logueada (no bloqueante, → Fase 2/follow-up): `config` no guarda token
no-string; `refs.list_refs` traga json corrupto → `[]`; `notion.add` trae la página entera para
el título; `AsyncClient` no se cierra por llamada; PATCH idempotente en links same-href
adyacentes; import `RateLimited` sin uso; `float(None)` en retry-after (inverosímil); bundle
+1.68MB por BlockNote (code-split pendiente); vulns de `npm audit` son del toolchain dev
(vite/vitest/esbuild), preexisten, no de BlockNote.

## Qué se construyó en R5a

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

- **Comunicación entre sesiones (lo próximo a diseñar)**: hoy existe el **modelo de datos**
  jerárquico (árbol coordinadora↔hijas: `parentId`, `children[]`, `kind`), pero **no hay ningún
  canal de mensajería entre sesiones** — cada sesión tiene su driver de chat aislado
  (`drivers[sessionId]`, eventos `chat.event.{session_id}`). El concepto "coordinadora comanda
  hijas" está en el spec de sesiones pero sin implementar. Es la base para meta-agentes y para
  integrar observabilidad/herramientas externas (langwatch, etc.). Requiere brainstorming/spec.
- **R5b — acciones de Graphite**: checkout de branch + submit (crea/actualiza PRs vía `gh`,
  outward-facing → confirmaciones/auth). R5a (lectura + restack) ya está; R5b son las acciones
  que faltan. Resolver conflictos de restack in-app también queda acá.
- **Tasks** (ítem del rail "Tasks", hoy stub; markdown local en `.ide/tasks/`; era parte del R6
  original, no construido). Rebanada chica y local, buen candidato para retomar.
- **Candidato de infra futuro (anotado, no rebanada):** `rmux` (multiplexer de terminal en Rust
  con SDKs Python/TS) para sesiones persistentes / orquestación multi-agente — reemplazaría el
  `pty_manager.py` de R2; swap grande, evaluar si/cuando se necesite persistencia.
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
