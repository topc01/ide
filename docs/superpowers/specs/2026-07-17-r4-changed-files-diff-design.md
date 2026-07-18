# Spec — R4: Changed files + File diff

> Fecha: 2026-07-17. Rebanada R4 del roadmap. Referencia de dominio: `finnecto-ide/src/git.js`
> (se reescribe en Python, no se copia código Node).

## Objetivo

Entregar el ítem "Changed files" del rail (hoy stub) end-to-end: un panel que lista los
archivos modificados del **worktree de la sesión activa** con contadores `+add/-del`, y una
**tab de diff** que muestra el archivo completo con las líneas de cambio resaltadas.

## Decisiones tomadas (brainstorming 2026-07-17)

1. **Fuente git = worktree de la sesión activa.** El panel corre `git status`/`diff` contra
   `activeSessionId → worktreePath`. Si no hay sesión seleccionada, cae al root del workspace.
   Mismo criterio que la terminal (`terminals._cwd`).
2. **Refresco = polling periódico** (~4s) mientras el panel `changes` está visible. Sin
   watchers de FS. El polling se limpia al desmontar o cambiar de panel/sesión.
3. **Vista de diff = archivo completo con cambios resaltados** (`git diff HEAD -U1000000`,
   equivalente a `getFileDiffFull` de finnecto). No hunks-only, no toggle.

## Arquitectura

Mismo molde de plugin que R6 (customizations) y R2 (terminal): módulo puro backend +
capability registrada en `app.py` + transport + store Zustand + módulo del rail + tab.

### Backend

**`server/ide_server/git.py`** — módulo puro, funciones testeables:

- `parse_numstat(raw: str) -> list[dict]` — `{path, added, removed}`; `-` (binario) → `None`.
- `parse_porcelain(raw: str) -> list[dict]` — `{path, status}` con status `M/A/D/R/?`
  (código `??` → `?`; renames `a -> b` toman `b`).
- `merge_changes(porcelain, numstat) -> list[dict]` — une por path en
  `{path, status, added, removed}`.
- `parse_diff(raw: str) -> list[dict]` — `{type, text}` con `type ∈ {hunk, add, del, ctx}`;
  descarta cabeceras (`diff `, `index `, `+++`, `---`); recorta la línea de contexto vacía
  final que git siempre emite.
- `untracked_lines(path: Path) -> int` — cuenta líneas de un archivo untracked; `0` si
  binario (contiene `\0`) o supera un guard de tamaño (~5 MB).
- `repo_status(cwd: Path) -> dict` — corre `git status --porcelain -uall` +
  `git diff --numstat HEAD` + branch + head; arma
  `{name, path, branch, head, files[], total_added, total_removed}`. Cuenta líneas de los
  untracked. Ante error de git, propaga para que la capability lo convierta en envelope.
- `file_diff_full(cwd: Path, path: str, status: str) -> list[dict]` — untracked (`?`) → todo
  el contenido del archivo como líneas `add`; si no, `parse_diff(git diff HEAD -U1000000 -- path)`.
  Binario → una línea `ctx` con "(binario)".

**`server/ide_server/capabilities/changes.py`** — registrada en `app.py`:

- `changes.list` `{sessionId?, repoId?}` → `{status}`.
- `changes.diff` `{sessionId?, repoId?, path, status}` → `{lines}`.
- Resolución de cwd: se **reutiliza la lógica de `terminals._cwd`** (worktree de sesión →
  path de repo → root). Se extrae a un helper compartido (p. ej. `workspace.resolve_cwd`)
  para no duplicar; `terminals.py` pasa a usar el mismo helper.
- **Sin fallos silenciosos**: si el cwd no es un repo git (o git falla), la capability
  devuelve el envelope `{type:"error", payload:{code, message}}`. El front muestra
  "desconectado", nunca una lista vieja como viva.

### Frontend

**`ui/src/transport/changesChannel.ts`** (molde de `settingsChannel.ts`):
- Tipos `FileChange {path, status, added, removed}`, `RepoStatus {name, branch, head,
  files, totalAdded, totalRemoved}`, `DiffLine {type, text}`.
- `fetchChanges(ws, {sessionId?}) -> Promise<RepoStatus>`.
- `fetchDiff(ws, {sessionId?, path, status}) -> Promise<DiffLine[]>`.

**`ui/src/state/changes.ts`** (Zustand): `{ status: RepoStatus | null, loading: boolean,
error: string | null }` + `load(sessionId)`. En error se limpia `status`/se marca `error`
(no se conserva la lista vieja).

**`ui/src/modules/changes/`**:
- `ChangesPanel.tsx` — reemplaza el stub. Header con branch + total `+/−`; botón refrescar;
  lista "Archivos modificados" con `path` (elipsis), `+added` verde (`#7fb069`), `-removed`
  rojo (`#c96a4e`), fiel al mockup (`docs/design/handoff/mockup.dc.html` líneas 144-153).
  Estado de error visible; estado vacío ("sin cambios"). Click en archivo → `openTab`.
- Polling: `useEffect` que arranca `setInterval(load, ~4000ms)` al montar y ante cambio de
  `activeSessionId`; se limpia en cleanup. Un fetch fallido detiene el spinner y muestra el
  error; el intervalo sigue reintentando (es idempotente) pero no acumula timers.
- `register.tsx` — `registerModule({ id: "changes", title: "Changed files", icon: FileDiff,
  Panel: ChangesPanel })`. Se remueve `changes` de `modules/stubs.tsx`. Se importa en `App.tsx`.

**`ui/src/main/DiffTab.tsx`**: `MainPanel.tsx` enruta `type === "file"` a este componente
(hoy placeholder `Tab: ${id}`). El `id` de la tab codifica `diff:<sessionId>:<path>` →
reabrir el mismo archivo enfoca la tab existente y tabs de sesiones distintas conviven. Al
montar, parsea el id, hace `fetchDiff` y renderiza cada línea con `bg`/`color` por `type`
(add=verde, del=rojo, ctx=neutro, hunk=cabecera ámbar), monoespaciada, `white-space:pre`,
fiel al mockup (líneas 376-383). Muestra error si el diff falla.

## Flujo de datos

`ChangesPanel` monta → `load(sessionId)` → `changes.list` → `git.repo_status(cwd)` → lista
renderizada; polling repite cada ~4s. Click archivo → `openTab({id:'diff:'+sid+':'+path,
type:'file', label: basename(path)})` → `DiffTab` monta → `changes.diff` →
`git.file_diff_full(cwd, path, status)` → líneas coloreadas.

## Manejo de errores

- cwd no-git / git falla → envelope de error → store guarda `error`, limpia `status` → panel
  muestra "desconectado / no es repo git", nunca datos viejos.
- Archivo binario → diff con una línea "(binario)".
- Archivo untracked → status `?`, se muestra como todo-add (contenido completo).
- Archivo borrado → status `D`, `git diff HEAD` lo muestra como todo-del.

## Plan de tests (TDD, un commit por tarea)

1. `git.py` puro: `parse_numstat`, `parse_porcelain`, `merge_changes`, `parse_diff`,
   `untracked_lines` con fixtures de strings/archivos temporales.
2. `git.py` integración: `repo_status`/`file_diff_full` contra un repo git temporal sembrado
   en `tmp_path` (modificado, untracked, borrado, binario).
3. `capabilities/changes.py`: resuelve cwd por `sessionId`; envelope de error si no es repo.
   Refactor de `resolve_cwd` compartido con `terminals` (sus tests deben seguir verdes).
4. `changesChannel.ts` con ws mockeado.
5. `state/changes.ts`: `load` éxito y error.
6. `ChangesPanel.tsx`: render de lista, estado de error, estado vacío, click abre tab.
7. `DiffTab.tsx`: render de líneas por tipo, estado de error.
8. `register.tsx` + remoción del stub + wiring en `App.tsx`.

## Fuera de alcance (YAGNI para R4)

- Watchers de FS / auto-refresh por evento de edit del chat (queda el polling).
- Diff hunks-only o toggle a hunks.
- Staged vs unstaged por separado (se usa `git diff HEAD`, todo junto).
- Acciones sobre archivos (stage/discard/revert).
- Selector de repo/sesión propio del panel (sigue a la sesión activa).

## Fidelidad de UI

Tokens 1a ámbar/terminal (`docs/design/REFERENCES.md`); mockup
`docs/design/handoff/mockup.dc.html` como referencia de layout (panel: líneas 143-154; tab de
diff: líneas 376-383). shadcn/Tailwind, sin estética por defecto.
