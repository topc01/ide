# Buscar contenido (módulo Search) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El módulo `search` del rail pasa de stub a un buscador de contenido con regex sobre el worktree de la sesión activa, con un agente de IA que ayuda a construir el regex.

**Architecture:** Backend Python: capability `search.content` que corre `ripgrep --json` sobre el worktree resuelto por sesión y agrupa por archivo; `files.open` extendido con `line`; `_load_session_context` extendido para sesiones efímeras `airegex:`. Frontend React: `SearchPanel` (rail), `RegexAiTab` (tab del panel principal que reusa el chat con `sessionId` sintético), estado en el store, puente "Insertar regex".

**Tech Stack:** Python 3 / FastAPI / `asyncio.create_subprocess_exec` / ripgrep · React + Vite + TS + Zustand + vitest.

## Global Constraints

- Sin fallos silenciosos: todo error viaja como envelope `{type:"error", payload:{code,message}}`; el frontend nunca muestra vacío como si fuera éxito. `bad_regex` y `rg_missing` son códigos propios.
- Fidelidad de UI: identidad 1a Terminal/amber vía shadcn/Tailwind (tokens existentes, resaltado en ámbar).
- TDD: test que falla → implementación mínima → test que pasa → commit (uno por tarea).
- Commits: conventional, atómicos, en español.
- La búsqueda corre en el worktree de la sesión activa; nunca escapa del root (patrón `_safe_join`).
- El regex es flavor ripgrep (Rust `regex`), no PCRE.
- Reusar la infra de chat + `mlx_router` para el agente de IA (no crear infra de IA nueva); default Claude.

---

### Task 1: Backend — capability `search.content` (motor ripgrep)

**Files:**
- Create: `server/ide_server/capabilities/search.py`
- Modify: `server/ide_server/bus.py:4-5` (import) y el bloque de `except` (agregar `SearchError`)
- Modify: `server/ide_server/app.py:14,36` (import + register)
- Test: `server/tests/test_search_capability.py`

**Interfaces:**
- Consumes: `resolve_cwd(root, payload)` de `ide_server.workspace`; `_safe_join(root, rel)` de `ide_server.capabilities.files`.
- Produces:
  - `register(registry: Registry, root: Path) -> None` que registra `search.content`.
  - `SearchError(Exception)` con atributo `.code: str` (valores `"bad_regex"` | `"rg_missing"`).
  - `search.content` payload: `{sessionId, query: str, options: {regex, caseSensitive, wholeWord, include: list[str], exclude: list[str], context: int}}`.
  - respuesta: `{matches: [{path: str, lines: [{line: int, text: str, ranges: [[int,int]]}]}], total: int, files: int, truncated: bool}`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_search_capability.py
import pytest
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.capabilities import search as search_cap


def _seed(tmp_path: Path):
    (tmp_path / ".ide").mkdir(exist_ok=True)
    (tmp_path / "a.py").write_text("import os\nprint('hola')\nprint('chau')\n")
    (tmp_path / "b.txt").write_text("solo texto sin match\n")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "c.py").write_text("PRINT MAYUS\nprint('x')\n")


async def _run(tmp_path, query, options=None):
    reg = Registry()
    search_cap.register(reg, tmp_path)
    return await reg.dispatch("search.content",
        {"sessionId": "s1", "query": query, "options": options or {}})


@pytest.mark.asyncio
async def test_literal_encuentra_agrupado_por_archivo(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "print", {"regex": False, "caseSensitive": True})
    paths = {m["path"] for m in out["matches"]}
    assert paths == {"a.py", "sub/c.py"}         # b.txt no matchea; agrupado por archivo
    a = next(m for m in out["matches"] if m["path"] == "a.py")
    assert [l["line"] for l in a["lines"]] == [2, 3]
    assert a["lines"][0]["ranges"] == [[0, 5]]   # 'print' en offset 0..5
    assert out["total"] == 3 and out["files"] == 2 and out["truncated"] is False


@pytest.mark.asyncio
async def test_sin_match_no_es_error(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "xyz-inexistente")
    assert out == {"matches": [], "total": 0, "files": 0, "truncated": False}


@pytest.mark.asyncio
async def test_query_vacia_devuelve_vacio(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "")
    assert out["total"] == 0 and out["matches"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_search_capability.py -v`
Expected: FAIL con `ModuleNotFoundError` / `AttributeError: module ... has no attribute 'register'`.

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/capabilities/search.py
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.workspace import resolve_cwd
from ide_server.capabilities.files import _safe_join

MAX_MATCHES = 2000
MAX_FILES = 500


class SearchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _build_args(query: str, opts: dict) -> list[str]:
    args = ["rg", "--json"]
    if opts.get("regex", True) is False:
        args.append("-F")                       # texto literal
    args.append("-s" if opts.get("caseSensitive") else "-i")
    if opts.get("wholeWord"):
        args.append("-w")
    for g in opts.get("include") or []:
        args += ["-g", g]
    for g in opts.get("exclude") or []:
        args += ["-g", f"!{g}"]
    ctx = int(opts.get("context") or 0)
    if ctx > 0:
        args += ["-C", str(ctx)]
    args += ["--", query]
    return args


def _byte_to_char(text: str, byte_off: int) -> int:
    # rg da offsets en bytes; el frontend resalta sobre chars.
    return len(text.encode("utf-8")[:byte_off].decode("utf-8", "ignore"))


def _parse(stdout: bytes) -> dict:
    by_path: dict[str, list] = {}
    order: list[str] = []
    total = 0
    truncated = False
    for raw in stdout.splitlines():
        if not raw:
            continue
        evt = json.loads(raw)
        if evt.get("type") != "match":
            continue
        data = evt["data"]
        path = data["path"]["text"]
        text = data["lines"]["text"].rstrip("\n")
        line = data["line_number"]
        ranges = [[_byte_to_char(text, sm["start"]), _byte_to_char(text, sm["end"])]
                  for sm in data.get("submatches", [])]
        if path not in by_path:
            if len(order) >= MAX_FILES:
                truncated = True
                continue
            by_path[path] = []
            order.append(path)
        if total >= MAX_MATCHES:
            truncated = True
            continue
        by_path[path].append({"line": line, "text": text, "ranges": ranges})
        total += 1
    matches = [{"path": p, "lines": by_path[p]} for p in order if by_path[p]]
    return {"matches": matches, "total": total,
            "files": len(matches), "truncated": truncated}


def register(registry: Registry, root: Path) -> None:
    async def content(payload: dict) -> dict:
        base = resolve_cwd(root, payload)
        _safe_join(base, "")                     # asegura base dentro del root
        query = payload.get("query") or ""
        if not query:
            return {"matches": [], "total": 0, "files": 0, "truncated": False}
        args = _build_args(query, payload.get("options") or {})
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, cwd=str(base),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError:
            raise SearchError("rg_missing", "ripgrep (rg) no está instalado")
        stdout, stderr = await proc.communicate()
        # rg: exit 0 = con matches, 1 = sin matches, 2 = error (regex inválido, etc.)
        if proc.returncode == 2:
            raise SearchError("bad_regex", stderr.decode("utf-8", "ignore").strip())
        return _parse(stdout)

    registry.register("search.content", content)
```

Modificar `server/ide_server/bus.py`:

```python
# en los imports (línea ~5)
from ide_server.capabilities.search import SearchError

# agregar este except ANTES del `except Exception` genérico (línea ~33)
    except SearchError as exc:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": exc.code, "message": str(exc)}})
```

Modificar `server/ide_server/app.py`:

```python
# junto a los otros imports de capabilities (línea ~14)
from ide_server.capabilities import search as search_cap

# junto a los otros register (línea ~36, después de files_cap)
    search_cap.register(registry, root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_search_capability.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing test para errores y filtros**

```python
# añadir a server/tests/test_search_capability.py
@pytest.mark.asyncio
async def test_regex_invalido_da_bad_regex(tmp_path):
    _seed(tmp_path)
    with pytest.raises(search_cap.SearchError) as ei:
        await _run(tmp_path, "(", {"regex": True})
    assert ei.value.code == "bad_regex"


@pytest.mark.asyncio
async def test_include_exclude_globs(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "print", {"regex": False, "caseSensitive": True,
                                         "include": ["*.py"], "exclude": ["sub/**"]})
    assert {m["path"] for m in out["matches"]} == {"a.py"}   # sub/c.py excluido, b.txt no es *.py


@pytest.mark.asyncio
async def test_case_insensitive_por_default(tmp_path):
    _seed(tmp_path)
    out = await _run(tmp_path, "print", {"regex": False})     # sin caseSensitive → -i
    assert any(m["path"] == "sub/c.py" and any(l["line"] == 1 for l in m["lines"])
               for m in out["matches"])                        # matchea 'PRINT MAYUS'
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_search_capability.py -v`
Expected: PASS (6 tests). Si `bad_regex`/globs fallan, ajustar `_build_args`/`_parse` (implementación ya los cubre).

- [ ] **Step 7: Commit**

```bash
git add server/ide_server/capabilities/search.py server/ide_server/bus.py server/ide_server/app.py server/tests/test_search_capability.py
git commit -m "feat(search): capability search.content (ripgrep --json, agrupa por archivo, códigos bad_regex/rg_missing)"
```

---

### Task 2: Backend — `files.open` con salto a línea

**Files:**
- Modify: `server/ide_server/capabilities/files.py:29-38` (handler `open_`)
- Test: `server/tests/test_files_capability.py` (agregar test; crear archivo si no existe)

**Interfaces:**
- Consumes: `terminal.open` con `{sessionId, cmd: list[str]}` (ya existe).
- Produces: `files.open` acepta `line?: int` opcional → antepone `+<line>` al path en el comando del editor.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_files_capability.py
import pytest
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.capabilities import files as files_cap


@pytest.mark.asyncio
async def test_open_con_line_antepone_mas_n(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR", "vim")
    (tmp_path / ".ide").mkdir()
    (tmp_path / "x.py").write_text("a\nb\nc\n")
    reg = Registry()
    captured = {}
    async def fake_terminal_open(payload):
        captured.update(payload); return {"id": "t1", "cwd": "/x"}
    reg.register("terminal.open", fake_terminal_open)
    files_cap.register(reg, tmp_path)
    await reg.dispatch("files.open", {"sessionId": "s1", "path": "x.py", "line": 2})
    assert captured["cmd"] == ["vim", "+2", str((tmp_path / "x.py").resolve())]


@pytest.mark.asyncio
async def test_open_sin_line_no_cambia(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR", "vim")
    (tmp_path / ".ide").mkdir()
    (tmp_path / "x.py").write_text("a\n")
    reg = Registry()
    captured = {}
    async def fake_terminal_open(payload):
        captured.update(payload); return {"id": "t1", "cwd": "/x"}
    reg.register("terminal.open", fake_terminal_open)
    files_cap.register(reg, tmp_path)
    await reg.dispatch("files.open", {"sessionId": "s1", "path": "x.py"})
    assert captured["cmd"] == ["vim", str((tmp_path / "x.py").resolve())]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_files_capability.py -k open -v`
Expected: FAIL (el `cmd` con `line` no contiene `+2`).

- [ ] **Step 3: Write minimal implementation**

Reemplazar el handler `open_` en `server/ide_server/capabilities/files.py`:

```python
    async def open_(payload: dict) -> dict:
        base = resolve_cwd(root, payload)
        target = _safe_join(base, payload.get("path") or "")
        editor = shlex.split(os.environ.get("EDITOR") or "vim")
        line = payload.get("line")
        cmd = editor + ([f"+{int(line)}"] if line else []) + [str(target)]
        return await registry.dispatch(
            "terminal.open", {"sessionId": payload.get("sessionId"), "cmd": cmd})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_files_capability.py -k open -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/files.py server/tests/test_files_capability.py
git commit -m "feat(files): files.open acepta line -> abre el editor en esa línea (vim +N)"
```

---

### Task 3: Backend — `_load_session_context` para sesiones efímeras `airegex:`

**Files:**
- Modify: `server/ide_server/capabilities/chat.py` (función `_load_session_context` + una constante nueva)
- Test: `server/tests/test_chat_capability.py` (agregar tests)

**Interfaces:**
- Consumes: `load_sessions`, `find_node`, `resolve_role` (ya se usan).
- Produces: si `session_id` empieza con `"airegex:"`, `_load_session_context` devuelve `{cwd, system_prompt, role: None, model: None, is_coordinator: False}` con `cwd` = worktree de la sesión real y `system_prompt` = `_LANG + "\n\n" + REGEX_AGENT_PROMPT`, **sin** llamar a `find_node` para el id sintético.
- Constante `REGEX_AGENT_PROMPT: str` exportada del módulo.

- [ ] **Step 1: Write the failing test**

```python
# añadir a server/tests/test_chat_capability.py
def test_airegex_session_usa_prompt_de_regex_y_cwd_del_worktree(tmp_path):
    from ide_server.capabilities.chat import _load_session_context, _LANG, REGEX_AGENT_PROMPT
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir()
    save_sessions(tmp_path, [{"id": "s1", "worktreePath": str(tmp_path)}])
    ctx = _load_session_context(tmp_path, "airegex:s1")
    assert ctx["cwd"] == str(tmp_path)
    assert ctx["system_prompt"].startswith(_LANG)
    assert REGEX_AGENT_PROMPT in ctx["system_prompt"]
    assert ctx["role"] is None and ctx["model"] is None
    assert ctx["is_coordinator"] is False


def test_airegex_de_sesion_inexistente_cae_al_root(tmp_path):
    from ide_server.capabilities.chat import _load_session_context, REGEX_AGENT_PROMPT
    from ide_server.sessions_store import save_sessions
    (tmp_path / ".ide").mkdir()
    save_sessions(tmp_path, [])
    ctx = _load_session_context(tmp_path, "airegex:nope")
    assert ctx["cwd"] == str(tmp_path)                 # fallback al root, no explota
    assert REGEX_AGENT_PROMPT in ctx["system_prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_chat_capability.py -k airegex -v`
Expected: FAIL (`ImportError: cannot import name 'REGEX_AGENT_PROMPT'`).

- [ ] **Step 3: Write minimal implementation**

En `server/ide_server/capabilities/chat.py`, agregar la constante bajo `_LANG`:

```python
REGEX_AGENT_PROMPT = (
    "Eres un asistente experto en expresiones regulares. Tu tarea es ayudar al usuario a "
    "construir el regex que necesita para buscar en su código.\n"
    "- Usa SIEMPRE la sintaxis de regex de ripgrep (motor Rust `regex`), NO PCRE (sin "
    "lookbehind, sin backreferences).\n"
    "- Cuando propongas el regex final, escríbelo en un bloque de código marcado como "
    "```regex``` (una sola línea con el patrón), para que la app lo pueda extraer.\n"
    "- Explica brevemente qué hace el patrón. Puedes pedir aclaraciones y ofrecer variantes."
)
```

Al principio de `_load_session_context`, antes de cargar el árbol, manejar el prefijo:

```python
def _load_session_context(root: Path, session_id: str) -> dict:
    from ide_server.sessions_store import load_sessions, find_node
    from ide_server.roles import resolve_role
    if session_id.startswith("airegex:"):
        real = session_id[len("airegex:"):]
        tree = load_sessions(root)
        node = find_node(tree, real)
        cwd = (node or {}).get("worktreePath") or str(root)
        system_prompt = _LANG + "\n\n" + REGEX_AGENT_PROMPT
        return {"cwd": cwd, "system_prompt": system_prompt, "role": None,
                "model": None, "is_coordinator": False}
    tree = load_sessions(root)
    node = find_node(tree, session_id)
    # ... (resto igual que hoy)
```

(El resto del cuerpo existente queda igual; solo se mueve el `import` arriba y se antepone el bloque `airegex:`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_chat_capability.py -v`
Expected: PASS (los nuevos + los existentes siguen verdes).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/chat.py server/tests/test_chat_capability.py
git commit -m "feat(chat): sesión efímera airegex: (prompt de regex + cwd del worktree, sin tocar sessions.json)"
```

---

### Task 4: Frontend — estado del search en el store + tab type `airegex`

**Files:**
- Modify: `ui/src/state/store.ts`
- Test: `ui/src/state/store.search.test.ts` (crear)

**Interfaces:**
- Produces (en `useStore`):
  - `Tab.type` incluye `"airegex"`.
  - `searchQuery: string`, `searchRegex: boolean`, `searchOptions: SearchOptions`, `searchResults: SearchResult | null`, `searchStatus: "idle"|"loading"|"done"|"error"`, `searchError: string | null`.
  - `SearchOptions = { caseSensitive: boolean; wholeWord: boolean; include: string; exclude: string; context: number }`.
  - `SearchResult = { matches: {path:string; lines:{line:number;text:string;ranges:[number,number][]}[]}[]; total:number; files:number; truncated:boolean }`.
  - setters: `setSearchQuery(q)`, `setSearchRegex(b)`, `setSearchOptions(partial)`, `setSearchStatus(s)`, `setSearchResults(r)`, `setSearchError(e)`.

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/state/store.search.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./store";

describe("search state", () => {
  beforeEach(() => useStore.setState({
    searchQuery: "", searchRegex: true, searchResults: null, searchStatus: "idle", searchError: null,
    searchOptions: { caseSensitive: false, wholeWord: false, include: "", exclude: "", context: 0 },
  }));

  it("setSearchQuery y setSearchRegex actualizan", () => {
    useStore.getState().setSearchQuery("foo");
    useStore.getState().setSearchRegex(false);
    expect(useStore.getState().searchQuery).toBe("foo");
    expect(useStore.getState().searchRegex).toBe(false);
  });

  it("setSearchOptions hace merge parcial", () => {
    useStore.getState().setSearchOptions({ wholeWord: true });
    expect(useStore.getState().searchOptions.wholeWord).toBe(true);
    expect(useStore.getState().searchOptions.caseSensitive).toBe(false);
  });

  it("setSearchResults + status", () => {
    useStore.getState().setSearchResults({ matches: [], total: 0, files: 0, truncated: false });
    useStore.getState().setSearchStatus("done");
    expect(useStore.getState().searchStatus).toBe("done");
    expect(useStore.getState().searchResults?.total).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/state/store.search.test.ts`
Expected: FAIL (`setSearchQuery is not a function`).

- [ ] **Step 3: Write minimal implementation**

En `ui/src/state/store.ts`:

```ts
export interface Tab { id: string; type: "file" | "task" | "branch" | "terminal" | "page" | "airegex"; label: string; }

export interface SearchOptions { caseSensitive: boolean; wholeWord: boolean; include: string; exclude: string; context: number; }
export interface SearchLine { line: number; text: string; ranges: [number, number][]; }
export interface SearchFile { path: string; lines: SearchLine[]; }
export interface SearchResult { matches: SearchFile[]; total: number; files: number; truncated: boolean; }
```

Agregar al `interface State` y al `create`:

```ts
  // dentro de interface State:
  searchQuery: string; searchRegex: boolean; searchOptions: SearchOptions;
  searchResults: SearchResult | null; searchStatus: "idle" | "loading" | "done" | "error"; searchError: string | null;
  setSearchQuery: (q: string) => void; setSearchRegex: (b: boolean) => void;
  setSearchOptions: (p: Partial<SearchOptions>) => void;
  setSearchStatus: (s: State["searchStatus"]) => void;
  setSearchResults: (r: SearchResult | null) => void; setSearchError: (e: string | null) => void;
```

```ts
  // dentro del create(...):
  searchQuery: "", searchRegex: true, searchResults: null, searchStatus: "idle", searchError: null,
  searchOptions: { caseSensitive: false, wholeWord: false, include: "", exclude: "", context: 0 },
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setSearchRegex: (searchRegex) => set({ searchRegex }),
  setSearchOptions: (p) => set((s) => ({ searchOptions: { ...s.searchOptions, ...p } })),
  setSearchStatus: (searchStatus) => set({ searchStatus }),
  setSearchResults: (searchResults) => set({ searchResults }),
  setSearchError: (searchError) => set({ searchError }),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/state/store.search.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/state/store.ts ui/src/state/store.search.test.ts
git commit -m "feat(search): estado del buscador en el store + tab type airegex"
```

---

### Task 5: Frontend — transport `searchContent` + `openFile` con línea

**Files:**
- Create: `ui/src/transport/searchChannel.ts`
- Modify: `ui/src/transport/filesChannel.ts` (openFile con `line`)
- Test: `ui/src/transport/searchChannel.test.ts` (crear)

**Interfaces:**
- Consumes: `WsClient.request` (ya existe).
- Produces:
  - `searchContent(ws, sessionId, query, opts): Promise<SearchResult>` → `ws.request("search.content", {sessionId, query, options})`.
  - `openFile(ws, sessionId, path, line?)` → agrega `line` al payload si viene.
  - `opts` que arma `searchContent`: `{regex, caseSensitive, wholeWord, include: string[], exclude: string[], context}` (parte los globs por coma/espacio, ignora vacíos).

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/transport/searchChannel.test.ts
import { describe, it, expect, vi } from "vitest";
import { searchContent } from "./searchChannel";

function fakeWs() {
  const calls: any[] = [];
  return { calls, request: vi.fn((channel, payload) => { calls.push({ channel, payload }); return Promise.resolve({ matches: [], total: 0, files: 0, truncated: false }); }) } as any;
}

describe("searchContent", () => {
  it("manda channel search.content con options normalizadas", async () => {
    const ws = fakeWs();
    await searchContent(ws, "s1", "foo", {
      regex: true, caseSensitive: true, wholeWord: false,
      include: "*.py, *.ts", exclude: "", context: 2,
    });
    expect(ws.calls[0].channel).toBe("search.content");
    expect(ws.calls[0].payload).toEqual({
      sessionId: "s1", query: "foo",
      options: { regex: true, caseSensitive: true, wholeWord: false,
                 include: ["*.py", "*.ts"], exclude: [], context: 2 },
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/transport/searchChannel.test.ts`
Expected: FAIL (módulo no existe).

- [ ] **Step 3: Write minimal implementation**

```ts
// ui/src/transport/searchChannel.ts
import type { WsClient } from "./ws";
import type { SearchResult } from "../state/store";

function splitGlobs(s: string): string[] {
  return s.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean);
}

export interface SearchArgs {
  regex: boolean; caseSensitive: boolean; wholeWord: boolean;
  include: string; exclude: string; context: number;
}

export function searchContent(ws: WsClient, sessionId: string, query: string, a: SearchArgs): Promise<SearchResult> {
  return ws.request("search.content", {
    sessionId, query,
    options: {
      regex: a.regex, caseSensitive: a.caseSensitive, wholeWord: a.wholeWord,
      include: splitGlobs(a.include), exclude: splitGlobs(a.exclude), context: a.context,
    },
  });
}
```

Modificar `ui/src/transport/filesChannel.ts`:

```ts
export function openFile(ws: WsClient, sessionId: string, path: string, line?: number): Promise<{ id: string; cwd: string }> {
  return ws.request("files.open", line ? { sessionId, path, line } : { sessionId, path });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/transport/searchChannel.test.ts src/transport/filesChannel.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/searchChannel.ts ui/src/transport/searchChannel.test.ts ui/src/transport/filesChannel.ts
git commit -m "feat(search): transport searchContent (globs normalizados) + openFile con línea"
```

---

### Task 6: Frontend — `SearchPanel` (reemplaza el stub) + registro del módulo

**Files:**
- Create: `ui/src/modules/search/SearchPanel.tsx`
- Create: `ui/src/modules/search/register.tsx`
- Modify: `ui/src/modules/stubs.tsx` (quitar el registro de `search`)
- Modify: `ui/src/App.tsx:1-7` (importar `./modules/search/register`)
- Test: `ui/src/modules/search/SearchPanel.test.tsx` (crear)

**Interfaces:**
- Consumes: `useStore` (Task 4), `searchContent` (Task 5), `openFile` (Task 5), `getWs`, `useSessions` (`activeSessionId`), `registerModule`.
- Produces: `SearchPanel` React component; registro del módulo `search` con icono `Search` de lucide.
- El botón "Crear con IA" abre un tab `airegex` — lo implementa la Task 7; en esta tarea es un botón que llama a un prop/callback `onCreateWithAI` expuesto vía el store o un handler local que la Task 7 conecta. Para desacoplar: el botón dispara `useStore.getState().openTab({ id: airegexTabId, type: "airegex", label: "Regex IA" })` con `airegexTabId = ` `airegex:${sid}`.

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/modules/search/SearchPanel.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SearchPanel } from "./SearchPanel";
import { useStore } from "../../state/store";

vi.mock("../../state/sessions", () => ({ useSessions: (sel: any) => sel({ activeSessionId: "s1" }) }));
const searchContent = vi.fn();
vi.mock("../../transport/searchChannel", () => ({ searchContent: (...a: any[]) => searchContent(...a) }));
vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/filesChannel", () => ({ openFile: vi.fn() }));

beforeEach(() => {
  searchContent.mockReset();
  useStore.setState({ searchQuery: "", searchRegex: true, searchResults: null, searchStatus: "idle", searchError: null,
    searchOptions: { caseSensitive: false, wholeWord: false, include: "", exclude: "", context: 0 } });
});

describe("SearchPanel", () => {
  it("busca con Enter y renderiza resultados agrupados", async () => {
    searchContent.mockResolvedValue({ matches: [{ path: "a.py", lines: [{ line: 2, text: "print(x)", ranges: [[0,5]] }] }], total: 1, files: 1, truncated: false });
    render(<SearchPanel />);
    fireEvent.change(screen.getByPlaceholderText(/buscar/i), { target: { value: "print" } });
    fireEvent.keyDown(screen.getByPlaceholderText(/buscar/i), { key: "Enter" });
    await waitFor(() => expect(screen.getByText("a.py")).toBeInTheDocument());
    expect(screen.getByText(/1 resultado/i)).toBeInTheDocument();
  });

  it("muestra el error bajo el campo (bad_regex)", async () => {
    searchContent.mockRejectedValue(new Error("regex parse error"));
    render(<SearchPanel />);
    fireEvent.change(screen.getByPlaceholderText(/buscar/i), { target: { value: "(" } });
    fireEvent.keyDown(screen.getByPlaceholderText(/buscar/i), { key: "Enter" });
    await waitFor(() => expect(screen.getByText(/regex parse error/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/modules/search/SearchPanel.test.tsx`
Expected: FAIL (componente no existe).

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/modules/search/SearchPanel.tsx
import { useStore } from "../../state/store";
import { useSessions } from "../../state/sessions";
import { getWs } from "../../transport/wsClient";
import { searchContent } from "../../transport/searchChannel";
import { openFile } from "../../transport/filesChannel";

function Highlighted({ text, ranges }: { text: string; ranges: [number, number][] }) {
  if (!ranges.length) return <>{text}</>;
  const out: React.ReactNode[] = []; let i = 0;
  ranges.forEach(([s, e], k) => {
    if (s > i) out.push(text.slice(i, s));
    out.push(<mark key={k} className="bg-primary/30 text-foreground">{text.slice(s, e)}</mark>);
    i = e;
  });
  if (i < text.length) out.push(text.slice(i));
  return <>{out}</>;
}

export function SearchPanel() {
  const sid = useSessions((s) => s.activeSessionId);
  const { searchQuery, searchRegex, searchOptions, searchResults, searchStatus, searchError,
    setSearchQuery, setSearchRegex, setSearchOptions, setSearchStatus, setSearchResults, setSearchError,
    openTab } = useStore();

  async function run() {
    if (!sid || !searchQuery) return;
    setSearchStatus("loading"); setSearchError(null);
    try {
      const r = await searchContent(getWs(), sid, searchQuery, { regex: searchRegex, ...searchOptions });
      setSearchResults(r); setSearchStatus("done");
    } catch (err: any) {
      setSearchError(String(err?.message ?? err)); setSearchStatus("error"); setSearchResults(null);
    }
  }

  return (
    <div className="flex h-full flex-col gap-2 p-2 text-sm">
      <div className="flex items-center gap-1">
        <input className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1"
          placeholder="Buscar contenido…" value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }} />
        <button title="Regex" aria-pressed={searchRegex}
          className={`rounded px-1 ${searchRegex ? "bg-primary/30" : ""}`}
          onClick={() => setSearchRegex(!searchRegex)}>.*</button>
        <button title="Crear con IA" className="rounded px-1"
          onClick={() => sid && openTab({ id: `airegex:${sid}`, type: "airegex", label: "Regex IA" })}>✨</button>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-xs">
        <button aria-pressed={searchOptions.caseSensitive} className={`rounded px-1 ${searchOptions.caseSensitive ? "bg-primary/30" : ""}`}
          onClick={() => setSearchOptions({ caseSensitive: !searchOptions.caseSensitive })}>Aa</button>
        <button aria-pressed={searchOptions.wholeWord} className={`rounded px-1 ${searchOptions.wholeWord ? "bg-primary/30" : ""}`}
          onClick={() => setSearchOptions({ wholeWord: !searchOptions.wholeWord })}>ab|</button>
        <input className="w-24 rounded border border-border bg-background px-1" placeholder="incluir"
          value={searchOptions.include} onChange={(e) => setSearchOptions({ include: e.target.value })} />
        <input className="w-24 rounded border border-border bg-background px-1" placeholder="excluir"
          value={searchOptions.exclude} onChange={(e) => setSearchOptions({ exclude: e.target.value })} />
      </div>
      {searchStatus === "loading" && <div className="text-muted-foreground">buscando…</div>}
      {searchError && <div className="rounded border border-border bg-card p-1 text-xs text-muted-foreground">{searchError}</div>}
      {searchStatus === "done" && searchResults && (
        <div className="min-h-0 flex-1 overflow-auto">
          <div className="mb-1 text-xs text-muted-foreground">
            {searchResults.total} resultado{searchResults.total === 1 ? "" : "s"} en {searchResults.files} archivo{searchResults.files === 1 ? "" : "s"}
            {searchResults.truncated && " (mostrando los primeros — refina la búsqueda)"}
          </div>
          {searchResults.total === 0 && <div className="text-muted-foreground">Sin coincidencias</div>}
          {searchResults.matches.map((f) => (
            <div key={f.path} className="mb-1">
              <div className="text-xs font-medium text-foreground">{f.path}</div>
              {f.lines.map((l, k) => (
                <button key={k} className="block w-full truncate text-left font-mono text-xs hover:bg-card"
                  onClick={() => sid && openFile(getWs(), sid, f.path, l.line)}>
                  <span className="mr-2 text-muted-foreground">{l.line}</span>
                  <Highlighted text={l.text} ranges={l.ranges} />
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

```tsx
// ui/src/modules/search/register.tsx
import { Search } from "lucide-react";
import { registerModule } from "../registry";
import { SearchPanel } from "./SearchPanel";
registerModule({ id: "search", title: "Search", icon: Search, Panel: SearchPanel });
```

En `ui/src/modules/stubs.tsx`, quitar la línea que registra `search` (dejar el archivo exportando `getModules`; si queda vacío de registros, mantener el import de `getModules`).

En `ui/src/App.tsx`, agregar el import junto a los otros módulos:

```ts
import "./modules/search/register";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/modules/search/SearchPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/search/ ui/src/modules/stubs.tsx ui/src/App.tsx
git commit -m "feat(search): SearchPanel (regex + filtros + resultados agrupados con resaltado) reemplaza el stub"
```

---

### Task 7: Frontend — `RegexAiTab` (chat de IA) + wiring en `MainPanel` + puente "Insertar regex"

**Files:**
- Create: `ui/src/main/RegexAiTab.tsx`
- Modify: `ui/src/layout/MainPanel.tsx` (rama `airegex`)
- Test: `ui/src/main/RegexAiTab.test.tsx` (crear)

**Interfaces:**
- Consumes: `useChat` (`state/chat.ts`: `convos`, `applyEvent`, `pushUser`, `setStarting`), `startChat`/`sendChat`/`subscribeChat` (chatChannel), `getWs`, `useStore` (`setSearchQuery`, `setSearchRegex`, `setActivePanel`), `Composer`, `MessageBubble`.
- Produces: `RegexAiTab({ id }: { id: string })` donde `id` = `airegex:<sid>`; usa ese `id` como `sessionId` de chat (el backend lo interpreta, Task 3). Un botón "Insertar regex" aparece cuando la última respuesta del asistente contiene un bloque ```` ```regex ````; al click extrae el patrón, hace `setSearchRegex(true)`, `setSearchQuery(patrón)`, `setActivePanel("search")`.
- `extractRegex(text: string): string | null` — helper exportado y testeado (parsea el último bloque ```` ```regex ````).

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/main/RegexAiTab.test.tsx
import { describe, it, expect } from "vitest";
import { extractRegex } from "./RegexAiTab";

describe("extractRegex", () => {
  it("saca el patrón del bloque ```regex```", () => {
    const md = "Prueba esto:\n```regex\n\\bprint\\s*\\(\n```\nEso matchea…";
    expect(extractRegex(md)).toBe("\\bprint\\s*\\(");
  });
  it("devuelve null si no hay bloque regex", () => {
    expect(extractRegex("no hay patrón aquí")).toBeNull();
  });
  it("toma el último bloque si hay varios", () => {
    const md = "```regex\nfoo\n```\ny mejor:\n```regex\nbar\n```";
    expect(extractRegex(md)).toBe("bar");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/main/RegexAiTab.test.tsx`
Expected: FAIL (módulo no existe).

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/main/RegexAiTab.tsx
import { useEffect, useRef } from "react";
import { useChat } from "../state/chat";
import { useStore } from "../state/store";
import { getWs } from "../transport/wsClient";
import { startChat, sendChat, subscribeChat } from "../transport/chatChannel";
import { MessageBubble } from "../chat/MessageBubble";
import { Composer } from "../chat/Composer";

export function extractRegex(text: string): string | null {
  const re = /```regex\s*\n([\s\S]*?)```/g;
  let m: RegExpExecArray | null, last: string | null = null;
  while ((m = re.exec(text)) !== null) last = m[1].trim();
  return last;
}

export function RegexAiTab({ id }: { id: string }) {
  const { convos, applyEvent, setStarting, pushUser } = useChat();
  const { setSearchQuery, setSearchRegex, setActivePanel } = useStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setStarting(id, true);
    const unsub = subscribeChat(getWs(), id, (e) => applyEvent(id, e));
    startChat(getWs(), id)
      .catch((err) => applyEvent(id, { kind: "error", code: "chat_error", message: String(err?.message ?? err) }))
      .finally(() => setStarting(id, false));
    return unsub;
  }, [id, applyEvent, setStarting]);

  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); });

  const c = convos[id];
  const lastAssistant = [...(c?.messages ?? [])].reverse().find((m: any) => m.role === "assistant");
  const regex = lastAssistant ? extractRegex(lastAssistant.text ?? "") : null;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border p-2 text-xs text-muted-foreground">
        Asistente de regex — describe qué quieres buscar.
      </div>
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-auto p-4">
        {c?.messages.map((m: any, i: number) => <MessageBubble key={i} msg={m} />)}
      </div>
      {regex && (
        <div className="flex items-center gap-2 border-t border-border p-2">
          <code className="min-w-0 flex-1 truncate rounded bg-card px-2 py-1 text-xs">{regex}</code>
          <button className="rounded bg-primary/30 px-2 py-1 text-xs"
            onClick={() => { setSearchRegex(true); setSearchQuery(regex); setActivePanel("search"); }}>
            Insertar regex
          </button>
        </div>
      )}
      <Composer streaming={!!c?.streaming}
        onSend={(t) => { pushUser(id, t); sendChat(getWs(), id, t).catch((err) =>
          applyEvent(id, { kind: "error", code: "chat_error", message: String(err?.message ?? err) })); }} />
    </div>
  );
}
```

En `ui/src/layout/MainPanel.tsx`, importar y agregar la rama antes del fallback:

```tsx
import { RegexAiTab } from "../main/RegexAiTab";
// ...
        {active?.type === "terminal"
          ? <TerminalTab id={active.id} />
          : active?.type === "airegex"
            ? <RegexAiTab id={active.id} />
          : active?.type === "file"
            ? <DiffTab id={active.id} />
            // ... (resto igual)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/main/RegexAiTab.test.tsx`
Expected: PASS.

- [ ] **Step 5: Verificar el build y el suite completo**

Run: `cd ui && npx vitest run && npm run build`
Expected: todos los tests verdes; build OK.
Run: `cd server && uv run pytest -q`
Expected: todos verdes.

- [ ] **Step 6: Commit**

```bash
git add ui/src/main/RegexAiTab.tsx ui/src/main/RegexAiTab.test.tsx ui/src/layout/MainPanel.tsx
git commit -m "feat(search): RegexAiTab (chat de IA para regex) + puente Insertar regex al panel Search"
```

---

## Notas de integración (no son tareas)

- **Composer**: su prop `onSend` es `(t, route?) => void`. En `RegexAiTab` lo llamamos sin `route` (ruteo Auto; default Claude). Verificar que `Composer` no exija `onStop` (en `ChatView` se pasa; aquí se puede omitir o pasar un no-op si TS lo exige).
- **`state/chat.ts`**: reusar tal cual (las convos se indexan por el `id` de sesión, así `airegex:<sid>` es una conversación aparte). Confirmar la forma de `MessageBubble`/`msg` (campo `role`/`text`) al implementar la Task 7; ajustar `lastAssistant` si el shape difiere.
- **rg y `.gitignore`**: rg ignora `.gitignore` por default — es el comportamiento deseado. No pasar `-uu`.
```
