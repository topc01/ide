# Spec — R5a: Graphite stack (lectura) + restack

> Fecha: 2026-07-18. Sub-rebanada A de R5 del roadmap (R5 = Graphite + Branch detail).
> R5b (checkout, submit/PRs) va después en su propio ciclo. Referencia de dominio: el tool
> **Graphite (`gt`)** que el dueño usa; `finnecto/graphite.js` NO aplica (es integración `gh`,
> otro diseño).

## Objetivo

Entregar el ítem "Graphite" del rail (hoy stub) end-to-end: un **stack de branches** del repo
de la sesión activa, todo inline en una columna — branch → (expand) commits → (expand)
archivos → (click) diff del archivo en ese commit. Marca visualmente las branches
**desactualizadas** (`needsRestack`, conector punteado estilo VSCode) y permite **restackear**
una branch con confirmación.

## Decisiones tomadas (brainstorming 2026-07-18)

1. **Fuente = Graphite real (`gt`).** La estructura del stack (branch → padre/hijos +
   revisiones) se lee del **SQLite de gt** `<repo>/.git/.graphite_metadata.db`, tabla
   `branch_metadata` (columnas: `branch_name`, `parent_branch_name`, `parent_branch_revision`,
   `branch_revision`, `children`, …), vía `sqlite3` de la stdlib — sin parsear el grafo de
   texto de `gt log`, sin checkouts. Commits y archivos salen de **git** (reusa `git.py` de R4).
2. **Repo = repo de la sesión activa.** La metadata gt vive en el `.git` del repo (compartido
   entre worktrees), así que se resuelve el **repo** (no el worktree) desde la sesión. Nuevo
   helper `workspace.resolve_repo`. Sin sesión → estado neutro "selecciona una sesión".
3. **Refresco = fetch al abrir + botón refrescar + re-fetch al cambiar de sesión.** Sin
   polling (la estructura del stack cambia poco y cada refresh dispara varios `git log`).
4. **Interacción inline, sin lupa ni tab de detalle:** una sola columna; branch expande a
   commits, commit expande a archivos, archivo abre el diff. El expand/collapse es estado de UI.
5. **Archivo → diff reusando `DiffTab` de R4**, extendido para el diff del archivo *en ese
   commit* (`git show <sha> …`), no el working-tree.
6. **`needsRestack`** por branch = tiene padre Y su `parent_branch_revision` (commit del padre
   sobre el que fue apilada) ≠ `branch_revision` actual del padre. Conector **punteado** cuando
   está desactualizada, sólido cuando está al día; tint/flecha ámbar de aviso.
7. **Restack ejecuta en R5a** (única mutación; local, sin PRs) con **confirmación**.
8. **Fuera de R5a → R5b:** checkout, submit/PRs, crear/mover branches, resolver conflictos de
   restack in-app.

## Arquitectura

Mismo molde de plugin que R4 (changes) y R6 (customizations): módulo puro backend + capability
en `app.py` + transport + store Zustand + módulo del rail. **Reusa R4**: `git.parse_numstat`,
el patrón subprocess, y el `DiffTab`/`MainPanel` (ruteo `type:"file"`, sin cambios de layout).

### Backend

**`server/ide_server/graphite.py`** — módulo puro/inyectable:

- `class GraphiteError(Exception)`.
- `read_stack(repo_path: Path) -> list[dict]` — abre `<repo>/.git/.graphite_metadata.db`
  (`sqlite3`), lee `branch_metadata` → `[{name, parent, parentRevision, revision, children}]`.
  Guarda: db ausente / tabla ausente / error sqlite → `GraphiteError` (→ envelope). No es un
  repo git → `GraphiteError`.
- `build_stack(rows: list[dict], current: str | None) -> list[dict]` — **puro**. DFS desde el
  trunk (`parent is None`) siguiendo `children`, produce lista ordenada trunk→hojas. Cada item:
  `{name, parent, isTrunk, current, needsRestack, revision}`.
  `needsRestack = parent is not None and parentRevision != <revision del row del padre>`.
- `branch_commits(repo_path, revision, parent_revision) -> list[dict]` — trunk
  (`parent_revision is None`) → `[]`; si no, `git log --format=%h%x1f%s <parent_revision>..<revision>`
  → `[{hash, message}]`.
- `commit_files(repo_path, sha) -> list[dict]` — `git show --numstat --format= <sha>` →
  `git.parse_numstat` → `[{path, added, removed}]`.
- `restack(repo_path, branch) -> None` — corre
  `gt restack --branch <branch> --only --no-interactive -q --cwd <repo>`. Si falla (conflicto,
  gt ausente): intenta cleanup defensivo (`git -C <repo> rebase --abort`, ignorando su error) y
  levanta `GraphiteError` con mensaje claro. **Nunca deja el repo a medio-rebase en silencio.**

**`server/ide_server/git.py`** — extensión (R4):
- `file_diff_at_commit(cwd: Path, sha: str, path: str) -> list[dict]` —
  `parse_diff(git show <sha> --format= -U1000000 -- <path>)` (full context, maneja root commit;
  el header de commit se suprime con `--format=`).

**`server/ide_server/workspace.py`** — extensión:
- `resolve_repo(root: Path, payload: dict) -> Path` — `sessionId` → `root/<repoId de la sesión>`
  (`KeyError` si la sesión no existe o no tiene repoId); `repoId` → `root/<repoId>`; si no →
  `KeyError`. (Distinto de `resolve_cwd`: devuelve el **repo**, no el worktree.)

**`server/ide_server/capabilities/graphite.py`** — registrada en `app.py`:
- `graphite.stack` `{sessionId?, repoId?}` → `{stack, current}`. `current` = branch de la
  sesión activa (o HEAD del repo).
- `graphite.branch` `{sessionId?, repoId?, branch}` → `{commits:[{hash, message,
  files:[{path,added,removed}]}]}` (lee el stack para obtener revision+parentRevision de la
  branch, luego `branch_commits` + `commit_files` por commit).
- `graphite.restack` `{sessionId?, repoId?, branch}` → `{stack, current}` (corre `restack`,
  luego re-fetch del stack).

**`server/ide_server/capabilities/changes.py`** — extensión (R4):
- `changes.diff` acepta un `sha?` opcional: si viene → `git.file_diff_at_commit(cwd, sha, path)`;
  si no → comportamiento R4 (`git.file_diff_full`). El cwd sigue siendo el worktree de la
  sesión (comparte el object db, `git show <sha>` funciona).

Errores gt/git → envelope `{type:"error",payload:{code,message}}` vía `bus.py` (sin fallos
silenciosos).

### Frontend

**`ui/src/transport/graphiteChannel.ts`**:
- Tipos `StackBranch {name, parent, isTrunk, current, needsRestack, revision}`,
  `Commit {hash, message, files: FileChange[]}` (reusa `FileChange` de `changesChannel`).
- `fetchStack(ws, {sessionId?}) -> {stack: StackBranch[], current: string}`.
- `fetchBranch(ws, {sessionId?, branch}) -> Commit[]`.
- `restackBranch(ws, {sessionId?, branch}) -> {stack, current}`.

**`ui/src/transport/changesChannel.ts`** — extensión:
- `fetchDiff` acepta `sha?` opcional y lo pasa en el payload de `changes.diff`.

**`ui/src/state/graphite.ts`** (Zustand):
- `{ stack: StackBranch[], current: string | null, commitsByBranch: Record<string, Commit[]>,
  expandedBranches: Set<string>, expandedCommits: Set<string>, loading, error }`.
- `load(sessionId)` — fetchStack; en error limpia stack/commits y setea error (sin datos viejos).
  Guard de sesión anti-race (patrón de R4: descarta la respuesta si `activeSessionId` cambió).
- `toggleBranch(sessionId, branch)` — expande/colapsa; si expande y no hay commits cacheados,
  `fetchBranch` y guarda en `commitsByBranch`.
- `toggleCommit(hash)` — expande/colapsa archivos.
- `restack(sessionId, branch)` — `restackBranch` → actualiza stack; en error setea error.

**`ui/src/modules/graphite/`**:
- `GraphitePanel.tsx` — reemplaza el stub. "Stack de branches": por branch un dot (color según
  estado: current ámbar `#e0863f`, needsRestack tint ámbar, normal neutro), nombre, badge
  "actual" en la current. Click en la branch → `toggleBranch`. Inline: commits (hash ámbar
  `#e0863f` + mensaje); click commit → `toggleCommit`; archivos (`path`, `+added` `#7fb069`,
  `-removed` `#c96a4e`); click archivo → `openTab({id:'diff:'+sessionId+':@'+sha+':'+path,
  type:'file', label: basename})`. Fiel al mockup (líneas 155-195). Estado neutro sin sesión,
  estado de error, botón refrescar.
- **Conector needs-restack**: el borde izquierdo que une la branch con su padre se dibuja
  `1px dashed` cuando `needsRestack`, `1px solid` cuando está al día (equivalente a los "..."
  de VSCode). Una **flecha de restack** a la derecha de la branch, visible solo cuando
  `needsRestack`.
- **Confirmación de restack**: click en la flecha → confirmación inline (la fila muestra
  "restackear? sí / no"); "sí" → `restack(sessionId, branch)`; en curso muestra estado; error
  → mensaje. (Confirmación inline, no `window.confirm`, para testeabilidad.)
- `register.tsx` — `registerModule({id:"graphite", title:"Graphite", icon:Layers, Panel:
  GraphitePanel})`. Se quita `graphite` de `stubs.tsx`; import en `App.tsx` y en
  `registry.test.ts`.

**`ui/src/main/DiffTab.tsx`** — extensión: `parseId` reconoce el slot de status con prefijo
`@` (`diff:<sessionId>:@<sha>:<path>`) → es un diff de commit; llama `fetchDiff` con `sha`.
Sin prefijo `@` → comportamiento R4 (working-tree). `MainPanel.tsx` no cambia (los tabs de
commit siguen siendo `type:"file"`).

## Flujo de datos

`GraphitePanel` monta → `load(sessionId)` → `graphite.stack` → `read_stack` (sqlite) +
`build_stack` → lista con `needsRestack`. Click branch → `graphite.branch` → commits+archivos
inline. Click archivo → tab `diff:<sid>:@<sha>:<path>` → `DiffTab` → `changes.diff` con `sha`
→ `git.file_diff_at_commit`. Click flecha → confirm → `graphite.restack` → `gt restack` →
re-fetch stack.

## Manejo de errores

- Repo sin gt / db ausente / gt no instalado → `GraphiteError` → envelope → panel "desconectado
  / no es un repo Graphite", nunca stack viejo.
- Restack con conflicto → gt no-interactive falla → cleanup `rebase --abort` → envelope
  "restack con conflictos, resuelve en la terminal".
- Sin sesión activa → estado neutro "selecciona una sesión" (no se llama al backend).
- Guard de sesión anti-race en el store (descarta respuestas de sesión previa).

## Plan de tests (TDD, un commit por tarea)

1. `graphite.build_stack` puro: orden trunk→hojas, `current`, `needsRestack` (revisión padre
   registrada ≠ tip actual del padre) con filas fixture.
2. `graphite.read_stack` integración: `.graphite_metadata.db` SQLite sembrado en `tmp_path`
   (crear la tabla `branch_metadata` con el esquema conocido — sin binario gt); errores
   (db/tabla ausente) → `GraphiteError`.
3. `graphite.branch_commits`/`commit_files` + `git.file_diff_at_commit`: repo git temporal
   con commits sembrados.
4. `workspace.resolve_repo`: por sesión / repoId / KeyError.
5. `graphite.restack`: gt real sobre stack sembrado si `gt` está disponible (skip si no);
   path de conflicto → abort → `GraphiteError` (simulable forzando un conflicto).
6. Capability `graphite.stack`/`branch`/`restack` + extensión `changes.diff` con `sha`:
   resuelve repo por sesión, envelopes de error.
7. Frontend transport (`graphiteChannel`, `changesChannel.fetchDiff` con sha) + `state/graphite`
   (load/toggle/restack, guard de error).
8. `GraphitePanel`: render stack, expand inline branch→commits→archivos, needsRestack punteado
   + flecha, confirmación de restack, click archivo abre tab; `DiffTab` extendido (id con `@sha`
   → `git show`).

## Fidelidad de UI

Tokens 1a ámbar/terminal (`docs/design/REFERENCES.md`); mockup
`docs/design/handoff/mockup.dc.html` (stack: líneas 155-195). Verde `#7fb069`, rojo `#c96a4e`,
ámbar `#e0863f`. shadcn/Tailwind, sin estética por defecto.

## Riesgos anotados

- **Esquema interno de gt**: leer `branch_metadata` acopla al SQLite de gt (versionado con
  kysely). Mitigación: lecturas guardadas → `GraphiteError` si el esquema no matchea (nunca
  crash). Alternativa futura si rompe: parsear `gt log`.
- **Restack de branch con worktree activo**: si la branch está checked-out en un worktree de
  sesión, el rebase puede chocar con la protección de git → se captura como envelope. Edge de
  R5a; la resolución in-app queda para R5b.
