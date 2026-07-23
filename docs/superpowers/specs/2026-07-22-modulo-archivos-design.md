# Spec — Módulo Archivos (navegar + abrir en vim)

> Fecha: 2026-07-22. Módulo nuevo del rail: un **explorador de archivos** navegable (estilo VSCode) que
> lista el árbol del worktree de la sesión activa y, al clickear un archivo, lo **abre en vim** (o
> `$EDITOR`) dentro de un tab de terminal — reusando toda la infra de terminal existente.

## Objetivo

Navegar los archivos del proyecto en un árbol (expand lazy, muestra **todo** sin filtros) y, al clickear
un archivo, editarlo con el editor real del usuario (vim/`$EDITOR`) en un tab de terminal. Sin construir
un editor de código en el browser: **vim es viewer y editor a la vez**.

## Decisiones (brainstorming 2026-07-22)

1. **Editar = terminal + vim.** `terminal.open` ya acepta `cmd`, así que "abrir archivo" delega en él con
   `cmd: [$EDITOR||vim, <path>]`. Cero editor propio, cero `files.read`, cero tipo de tab nuevo (reusa el
   tab `"terminal"` existente). Idea del dueño.
2. **El árbol muestra todo** — incluido `.git`, dotfiles, `node_modules`. Sin ocultar nada (v1).
3. **Raíz = worktree de la sesión activa** (`resolve_cwd(root, {sessionId})`, como terminal/chat/changes).
4. **Expand lazy:** cada carpeta pide sus hijos al abrirse (`files.list` de un nivel), no se camina todo.
5. **Módulo del rail = plugin** (`registerModule`), 7º módulo — exactamente lo que habilita la regla de
   extensibilidad.

## Arquitectura

### Backend — `capabilities/files.py`

- `_safe_join(root, rel) -> Path`: `(root/rel).resolve()`; debe ser `root` o un descendiente (si no,
  `ValueError` — evita escapar con `..` o symlinks). **Seguridad de path.**
- `files.list {sessionId, path}` → `{entries: [{name, type: "dir"|"file"}]}`: resuelve la raíz de la
  sesión (`resolve_cwd`), joinea `path` (default `""` = raíz), lista el directorio (dirs primero, luego
  files, alfabético). `path` que no es dir / escapa → `ValueError` (envelope).
- `files.open {sessionId, path}` → delega en `terminal.open`: `editor = shlex.split($EDITOR or "vim")`;
  `await registry.dispatch("terminal.open", {sessionId, cmd: editor + [str(abs_path)]})`; devuelve su
  resultado (`{id, cwd}`). Reusa el spawn del PTY sin duplicar.
- Wire en `app.py`: `files_cap.register(registry, root)`.

### Frontend

- **`transport/filesChannel.ts`**: `FileEntry {name, type}`; `listFiles(ws, sessionId, path)`;
  `openFile(ws, sessionId, path) -> {id, cwd}`.
- **`state/store.ts`**: agregar `"files"` al union `PanelId`.
- **`modules/files/FilesPanel.tsx`**: árbol recursivo. Componente `TreeNode` por entrada:
  - carpeta → click togglea expand; al abrir por primera vez, `listFiles(path)` y renderiza los hijos
    como `TreeNode` (recursión, indentado por profundidad);
  - archivo → click hace `openFile(path)` → `openTab({id, type:"terminal", label: name})` (+ activa el
    tab). Vim corre en ese tab de terminal.
  - La raíz (`FilesPanel`) lista `path=""` de la sesión activa; sin sesión → "Seleccioná una sesión".
- **`modules/files/register.tsx`**: `registerModule({ id:"files", title:"Files", icon: FolderTree, Panel: FilesPanel })`.
- **`App.tsx`**: `import "./modules/files/register";` (junto a los otros módulos).

## Manejo de errores (sin fallos silenciosos)

- `path` fuera de la raíz / no-dir → `ValueError` → envelope (no se listan datos falsos).
- `files.open` que falle (p.ej. terminal.open falla) → propaga como envelope; el panel no abre tab.
- `listFiles` que falle en el front → nodo sin hijos (`[]`), no rompe el árbol.

## Plan de tests (TDD)

**Backend:**
1. `_safe_join`: ok para subpath y `""`; `ValueError` para `../escape`.
2. `files.list`: lista entradas (dirs primero); subdirectorio; `../..` → `ValueError`. (`resolve_cwd`
   monkeypatcheado a `tmp_path`.)
3. `files.open`: delega en `terminal.open` con `cmd = [editor, abs_path]` y el `sessionId`; devuelve su
   resultado. (`$EDITOR` seteado a `vim`; `terminal.open` fake registrado en el Registry.)

**Frontend:**
4. `filesChannel`: `listFiles`/`openFile` pegan a `files.list`/`files.open` con `{sessionId, path}`.
5. `FilesPanel`: con sesión activa, lista la raíz; click en carpeta la expande (pide hijos); click en
   archivo llama `openFile` y abre un tab de terminal; sin sesión → mensaje.

**Verificación en vivo (fuera del plan):** abrir el módulo, navegar, clickear un archivo y ver vim
abrirse en el tab de terminal.

## Fuera de alcance (siguientes)

- Resaltado de sintaxis / viewer read-only propio (vim ya edita y ve).
- Acciones de archivo (crear/renombrar/borrar), gitignore-awareness, búsqueda en archivos.
- Recordar el árbol expandido entre reaperturas.

## Fidelidad de UI

Panel con el idiom de los otros paneles del rail (`aside w-64`, `Label`, filas `text-xs hover:bg-accent`).
Íconos de carpeta/archivo (lucide). Sin estética por defecto.
