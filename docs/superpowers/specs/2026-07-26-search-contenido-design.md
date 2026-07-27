# Buscar contenido (módulo Search) — Diseño

> Rebanada vertical. El módulo `search` del rail (hoy un stub) pasa a ser un buscador de
> contenido con **regex** sobre el worktree de la sesión activa, más un **agente de IA** que
> ayuda a construir el regex. Fecha: 2026-07-26.

## Objetivo

Que el usuario pueda buscar contenido (texto o regex) dentro del worktree de la sesión activa,
con filtros serios (case, whole-word, globs include/exclude, context lines), resultados
navegables tipo VS Code (agrupados por archivo, salto a la línea exacta), y un asistente de IA
que traduce lenguaje natural a un regex de ripgrep e inserta ese regex en el campo de búsqueda.

Fuera de alcance (rebanadas futuras): search & replace, búsqueda cross-repo, live-search por tecla.

## Alcance y decisiones cerradas

- **Dónde busca:** el **worktree de la sesión activa** (coherente con el módulo Archivos; respeta
  el aislamiento por sesión). Cross-repo queda para después (se agregaría como un dropdown de root).
- **Motor:** **ripgrep (`rg`)** con `--json` (salida estructurada: archivo, línea, offsets de cada
  submatch para resaltado). rg ya está disponible en el entorno.
- **Regex flavor:** Rust/ripgrep (no PCRE). El system prompt de la IA lo tiene en cuenta.
- **Agente de IA:** **reusa la infra de chat** (`chat.send` + `mlx_router`), con ruteo
  Auto/Local/Claude y **default Claude** (extensibilidad primero: mañana se puede mover al local
  sin recablear). No se crea infra de IA nueva.
- **El chat de IA abre en el panel principal** como un tab nuevo (`airegex`), con un botón
  "Insertar regex" que escribe el regex en el campo del panel de Search (puente cross-panel).
- **Controles incluidos:** regex on/off, case sensitive, whole word, include/exclude globs,
  context lines. **Replace NO** (rebanada futura).

## Componentes

### Backend (Python, `ide_server`)

**`capabilities/search.py` — nueva capability `search.content`.**
- Entrada: `{sessionId, query, options}` donde
  `options = {regex: bool, caseSensitive: bool, wholeWord: bool, include: [str], exclude: [str], context: int}`.
- Resuelve `cwd` con `resolve_cwd(root, payload)` (worktree de la sesión) y valida con el mismo
  patrón de `_safe_join` de `files.py` (rg nunca sale del root).
- Corre `rg --json` con los flags mapeados (ver abajo), `cwd` = worktree.
- Parsea el stream JSON de rg (eventos `match` con `path`, `line_number`, `submatches`) y **agrupa
  por archivo**.
- Aplica un **cap** (máx. 2000 matches / 500 archivos). Si se corta, `truncated: true`.
- Errores → envelope `{type:"error", payload:{code, message}}`:
  - regex inválido (rg exit 2) → `code: "bad_regex"`, `message` = stderr de rg.
  - rg ausente (FileNotFoundError) → `code: "rg_missing"`.
- Sin matches → `{matches: [], total: 0, files: 0, truncated: false}` (NO es error).

**Mapeo de opciones a flags de rg:**

| Opción | Flag |
|---|---|
| `regex: false` (literal) | `-F` |
| `regex: true` | *(sin flag; regex nativo)* |
| `caseSensitive: false` | `-i` |
| `caseSensitive: true` | `-s` |
| `wholeWord: true` | `-w` |
| `include: [g]` | `-g '<g>'` por cada uno |
| `exclude: [g]` | `-g '!<g>'` por cada uno |
| `context: N` (N>0) | `-C N` |

Siempre: `--json`. rg respeta `.gitignore` por default (no busca en `node_modules`, `dist`, etc.).

**Forma de la respuesta:**
```json
{
  "matches": [
    { "path": "src/app.py",
      "lines": [
        { "line": 42, "text": "  print(x)", "ranges": [[2, 7]] },
        { "line": 88, "text": "  print(y)", "ranges": [[2, 7]] }
      ] }
  ],
  "total": 2, "files": 1, "truncated": false
}
```
`ranges` son pares `[start, end]` de offset de columna (bytes→chars) dentro de `text`, para el resaltado.

**Extensión de `files.open`.** Aceptar `line?: int` opcional en el payload. Si viene, abre
`vim +<line> <archivo>` (para saltar al match). Cambio mínimo y retrocompatible (sin `line`, se
comporta igual que hoy).

**Extensión de `chat._load_session_context`.** Si `session_id` empieza con `airegex:`, es una
sesión efímera de asistente (NO está en `sessions.json`):
- extrae el id real (`airegex:<real>` → `<real>`), resuelve su worktree como `cwd`.
- `system_prompt` = el prompt especializado de regex (ver abajo), precedido por `_LANG`.
- `role = None`, `model = None` (el router decide; default Claude), `is_coordinator = False`.
- No llama a `find_node` para el id sintético (no existe en el árbol).

**System prompt del agente de regex** (constante en el código, no editable en esta rebanada):
- Rol: generar un **regex con sintaxis de ripgrep (Rust `regex`)**, no PCRE.
- Devolver el regex final en un bloque ` ```regex … ``` ` para que el frontend lo extraiga.
- Puede pedir aclaraciones y proponer variantes; explica brevemente qué hace el regex.

### Frontend (React + Vite + TS, `ui`)

**`modules/search/SearchPanel.tsx`** — el panel del rail (reemplaza el stub `search`):
- Campo de query con toggle `.*` (regex on/off) embebido a la derecha.
- Fila de controles: `Aa` (case), `⁠ab⁠` (whole word), inputs include/exclude, stepper de context.
- Botón **"Crear con IA"** (✨) que abre el tab `airegex`.
- Conteo (`N resultados en M archivos`) + lista de resultados agrupada por archivo (colapsable,
  expandida por default), líneas con `Nº` tenue + preview con el match resaltado (ámbar 1a).
- Buscar **on-Enter** (no live por tecla); cambiar un toggle re-ejecuta la última query.
- Estados: vacío inicial (hint), cargando (spinner), sin resultados, error (mensaje bajo el campo),
  truncado (banner).

**`modules/search/register.tsx`** — `registerModule({ id: "search", title: "Search", icon: Search, Panel: SearchPanel })`.
Se importa en `App.tsx` (reemplazando el registro stub de `search` en `modules/stubs.tsx`).

**`main/RegexAiTab.tsx`** — nuevo tab type `airegex` en `MainPanel`:
- Chat enfocado a regex (reusa el transporte de chat: `sendChat`, eventos `Routed/TextDelta/Done`).
- `sessionId` sintético `airegex:<sessionId-real>`.
- Parsea la última respuesta buscando un bloque ` ```regex … ``` `. Si hay, muestra **"Insertar
  regex"**; al click escribe el valor en `store.searchQuery` (y `regex: on`), enfoca el panel Search.
- Dedup: un tab `airegex` por sesión real (si ya existe, lo enfoca).

**`state/store.ts`** — agregar:
- `searchQuery: string`, `searchOptions: SearchOptions`, `searchResults: SearchResult | null`,
  `searchStatus: "idle"|"loading"|"done"|"error"`, `searchError: string | null`.
- setters: `setSearchQuery`, `setSearchOptions`, `setSearchResults`, `setSearchStatus`.
- El tab `airegex` es un `Tab` con `type: "airegex"` (agregar al union de `Tab.type`).

**`layout/MainPanel.tsx`** — agregar la rama `active?.type === "airegex" ? <RegexAiTab id=… /> : …`.

**`transport/`** — `searchContent(ws, sessionId, query, options)` → `search.content`;
`openFile` extendido con `line?`.

## Flujo de datos

```
SearchPanel ──search.content──> rg en worktree ──> resultados agrupados ──> click línea ──files.open(line)──> vim +N
    ▲ "Crear con IA"
    │ abre tab airegex (panel principal)
RegexAiTab ──chat.send(router, sessionId="airegex:<real>")──> IA ──> ```regex``` ──"Insertar regex"(store)──> campo SearchPanel
```

## Manejo de errores (sin fallos silenciosos)

- Regex inválido → `bad_regex` (mensaje de rg bajo el campo, no resultados vacíos).
- rg ausente → `rg_missing` (explica que falta ripgrep).
- Cap alcanzado → `truncated: true` + banner.
- Respuesta de IA sin bloque `regex` → no se muestra el botón (el usuario sigue conversando).
- mlx forzado sin encender → degrada a Claude con aviso (comportamiento de chat existente).

## Testing (TDD)

**Backend (`server/tests/test_search_capability.py`)** con `tmp_path` sembrado de archivos y rg real:
- query literal encuentra / no encuentra (sin matches ≠ error).
- regex válido agrupa por archivo con `ranges` correctos.
- regex inválido → envelope `bad_regex`.
- globs include/exclude filtran los archivos esperados.
- `_safe_join` bloquea path fuera del worktree.
- cap → `truncated: true`.

**Backend (`test_files_capability.py`)**: `files.open` con `line` arma `vim +N archivo`.

**Backend (`test_chat_capability.py`)**: `_load_session_context("airegex:s1")` → system prompt de
regex + cwd del worktree, sin tocar `sessions.json`.

**Frontend (vitest)**:
- SearchPanel rutea query+options al transport y renderiza resultados agrupados con resaltado.
- Estados vacío / cargando / sin-resultados / error / truncado.
- RegexAiTab: extrae el bloque ` ```regex``` ` y "Insertar regex" escribe en el store + enfoca Search.

## Rebanadas relacionadas (no en este spec)

- **Buscar archivos (Cmd+P) en el módulo Archivos** — su propia rebanada corta.
- **Pase de pulido UI/UX** — su propio ciclo de revisión.
