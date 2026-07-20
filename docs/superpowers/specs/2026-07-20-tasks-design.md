# Spec — Tasks (markdown local) Fase 1

> Fecha: 2026-07-20. El ítem "Tasks" del rail (hoy stub) pasa a gestionar archivos `.md` en
> `.ide/tasks/`: listar, abrir, **crear** y **editar** (guardado local, sin API externa). Era
> parte del R6 original, no construido.

## Objetivo

Un gestor de tareas simple y **local**: cada tarea es un archivo markdown en `.ide/tasks/` (dir
que `ide init` ya crea). El rail lista las tareas; abrir una la muestra en un tab del panel
principal con un **editor de markdown crudo** que guarda al archivo con debounce. Se puede crear
una tarea nueva desde el panel. Sin render estructurado ni API externa (a diferencia de Notion).

## Decisiones tomadas (brainstorming 2026-07-20)

1. **Lectura + crear + editar** (no solo-lectura). Sin borrar en esta fase.
2. **Editor markdown crudo edit-in-place**: textarea con el markdown, guardado **debounced** al
   `.md` (mismo patrón que `NotionPageTab`). Sin render estructurado (toggle vista → Fase 2).
3. **Convenciones livianas** (según el mockup): **título** = primer `# H1` del archivo (fallback:
   el nombre del archivo sin `.md`); **status** = valor de la primera línea `status: <x>` (opcional;
   sin ella no se muestra badge).
4. **id de tarea** = nombre de archivo (`.ide/tasks/<slug>.md`).

## Arquitectura

Módulo nuevo `tasks`, siguiendo la plantilla del módulo Notion (capability + transport + store +
panel + tab). Reusa la infra de módulos del rail (`registerModule`) y de tabs (`MainPanel` rutea
por `tab.type`, que ya incluye `"task"`).

### Backend (`server/ide_server/tasks/`)

- **`parse.py` (puro):** `parse_meta(markdown: str) -> dict` → `{"title": str | None, "status":
  str | None}`. `title` = texto de la primera línea que empieza con `# ` (un solo `#`), stripeado;
  `status` = valor de la primera línea que matchea `^status:\s*(.+)$` (case-insensitive), stripeado.
  Ambos `None` si no aparecen. Testable en aislamiento.
- **`store.py`:**
  - `_tasks_dir(root) -> Path` = `root/.ide/tasks` (lo crea si falta).
  - `_task_path(root, task_id) -> Path`: valida que `task_id` sea un filename pelado
    (`re.fullmatch(r"[A-Za-z0-9._-]+", task_id)` y sin `..`/`/`); si no, `raise InvalidTaskId`.
    Devuelve `_tasks_dir(root)/f"{task_id}.md"`.
  - `list_tasks(root) -> list[dict]`: por cada `*.md` en el dir, `{"id": <stem>, "title":
    parse_meta(...).title or <stem>, "status": parse_meta(...).status}`. Ordenado por id.
  - `read_task(root, task_id) -> dict`: `{"id", "title" (parseado con fallback al id), "status",
    "markdown"}`. Si el archivo no existe → `raise KeyError`.
  - `write_task(root, task_id, markdown) -> dict`: escribe el `.md`; devuelve el meta re-parseado
    `{"id", "title", "status"}` (para refrescar el rail). Si el archivo no existe → `KeyError`.
  - `create_task(root, name) -> dict`: `slug = slugify(name)` (reusar `sessions_store.slugify`);
    si `<slug>.md` ya existe → sufijo `-2`, `-3`, … ; escribe template
    `f"# {name}\nstatus: todo\n"`; devuelve `{"id": slug, "title": name, "status": "todo"}`.
  - Excepción `InvalidTaskId(ValueError)`.
- **`capabilities/tasks.py`:** `register(registry, root)` con handlers:
  - `tasks.list {}` → `{"tasks": list_tasks(root)}`.
  - `tasks.read {id}` → `read_task(root, id)`.
  - `tasks.save {id, markdown}` → `write_task(root, id, markdown)` (devuelve el meta).
  - `tasks.create {name}` → `{"task": create_task(root, name)}`.
  - Errores (id inválido, KeyError, IO) → propagan → envelope en `bus.py` (sin fallos silenciosos).
- Registrar en `app.py`: `tasks_cap.register(registry, root)`.

### Frontend (`ui/src/`)

- **`transport/tasksChannel.ts`:**
  - `listTasks(ws) -> Promise<TaskRef[]>` (`TaskRef = {id, title, status: string | null}`).
  - `readTask(ws, id) -> Promise<TaskDoc>` (`TaskDoc = {id, title, status, markdown}`).
  - `saveTask(ws, id, markdown) -> Promise<TaskMeta>` (`{id, title, status}`).
  - `createTask(ws, name) -> Promise<TaskRef>`.
- **`state/tasks.ts`:** store zustand `useTasks`: `{ tasks: TaskRef[], loading, error,
  load(), create(name) }`. `load` llama `listTasks`; `create` llama `createTask` y refresca la lista
  (y devuelve el ref para abrir el tab). Errores → `error`.
- **`modules/tasks/TasksPanel.tsx`:** al montar, `load()`. Muestra:
  - Header "Tareas" + botón **"+ nueva"** que abre un input inline (nombre) → `create(name)` →
    abre el tab de la tarea creada.
  - Lista: cada tarea es un botón (título en `#e8e6e1`; abajo el `id.md` en mono `#75705f` +
    el `status` en ámbar `#e0863f` si existe). Click → `openTab({ id: \`task:${t.id}\`, type:
    "task", label: t.title })`.
  - Estados loading / error / vacío ("todavía no hay tareas").
- **`modules/tasks/register.tsx`:** `registerModule({ id: "tasks", title: "Tasks", icon:
  ListChecks, Panel: TasksPanel })`.
- **`main/TaskTab.tsx`:** `TaskTab({ id })` (id = `task:<taskId>`). Al montar `readTask`. Renderiza
  un header con el título (parseado) + estado de guardado ("guardando…/guardado/error"), y un
  **`<textarea>`** con el `markdown` crudo. `onChange` con **debounce ~800ms** → `saveTask(taskId,
  markdown)`; con el meta devuelto actualiza el título del header (y refresca la lista de tareas
  del store para el rail). Sin fallo silencioso: error de save → estado "error".
- **`layout/MainPanel.tsx`:** agregar la rama `active?.type === "task" ? <TaskTab id={active.id} />`.
- **`modules/stubs.tsx`:** **quitar** el `registerModule` de `tasks` (deja de ser stub). Importar
  el módulo real donde se importan los otros (donde `stubs`/módulos se cargan).

## Flujo de datos

Abrir panel Tasks → `load` → `tasks.list` → rail con las tareas. "+ nueva" → nombre → `tasks.create`
→ nuevo `.md` + refresca lista + abre tab `task:<id>`. En el tab: `tasks.read` → textarea con el
markdown → editar → debounce → `tasks.save` → reescribe el `.md` y devuelve `{title, status}` →
header + rail se refrescan.

## Manejo de errores

- `id` con traversal o caracteres inválidos → `InvalidTaskId` → envelope → el front muestra error.
- Leer/guardar una tarea inexistente → `KeyError` → envelope.
- IO error → excepción → envelope. Nunca se pretende éxito falso.

## Plan de tests (TDD)

**Backend:**
1. `parse.parse_meta`: título desde `# H1`; status desde `status:`; ambos `None` si faltan; no
   confunde `## H2` con título; status case-insensitive.
2. `store`: `list_tasks` (título con fallback al id; status opcional; orden); `read_task`
   (markdown + meta; KeyError si no existe); `write_task` (persiste + devuelve meta re-parseado);
   `create_task` (slug + template + sufijo ante colisión); **`_task_path` rechaza `../x`,
   `a/b`, vacío** (InvalidTaskId). (tmp_path.)
3. Capability `tasks.list/read/save/create` sobre un registry con tmp_path.

**Frontend:**
4. `tasksChannel` (ws mock): cada fn manda el canal + payload correctos.
5. `state/tasks`: `load` puebla `tasks`; `create` refresca la lista.
6. `TasksPanel`: renderiza la lista; "+ nueva" llama `create` y abre el tab; estado vacío.
7. `TaskTab`: carga el markdown en el textarea; editar dispara `saveTask` con debounce; error → estado error.

## Fuera de alcance (Fase 2+)

Borrar tareas; render estructurado (toggle vista con secciones/bullets del mockup); cambiar status
desde el rail sin abrir; subcarpetas, orden manual, filtros por status; sincronización con las
sesiones de Claude Code (que una hija cree/actualice tareas vía una tool).

## Fidelidad de UI

Panel Tasks fiel al mockup (líneas 197-210): título de tarea `#e8e6e1`, archivo en mono `#75705f`,
status en ámbar `#e0863f`. Header "Tareas" en mayúsculas `#75705f`. Botón "+ nueva" con el idiom
de los inputs existentes (NewSessionModal / "+ por URL" de Notion). Textarea con el idiom del
editor de páginas del mockup (líneas 402-403).
