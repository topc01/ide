# R4 — Changed files + File diff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar end-to-end el ítem "Changed files" del rail: un panel que lista los archivos modificados del worktree de la sesión activa (con contadores `+/-`) y una tab que muestra el diff del archivo completo con las líneas resaltadas.

**Architecture:** Mismo molde de plugin que R6/R2 — módulo puro backend (`git.py`) + capability registrada en `app.py` + transport + store Zustand + módulo del rail + tab. El cwd de git se resuelve con un helper compartido (`workspace.resolve_cwd`) extraído de `terminals.py`. Todo error de git viaja como envelope; el front muestra "desconectado", nunca datos viejos.

**Tech Stack:** Backend Python/FastAPI (`uv`, `pytest`), frontend React + Vite + TS (Zustand, Tailwind/shadcn, Vitest + Testing Library). Git vía `subprocess`.

## Global Constraints

- **Sin `ANTHROPIC_API_KEY`, Claude Code local.** (No aplica a R4 directamente, pero no introducir dependencias de API.)
- **Sin fallos silenciosos:** todo error del backend viaja como envelope `{type:"error",payload:{code,message}}` (el `bus.py` ya envuelve cualquier `Exception` en `handler_error`). El front limpia el estado y muestra "desconectado", nunca la lista/diff viejos como vivos.
- **TDD estricto:** test que falla → implementación mínima → test que pasa → commit. Un commit por tarea.
- **Conventional commits en español**, atómicos.
- **Fidelidad UI 1a ámbar/terminal:** tokens en `docs/design/REFERENCES.md`; mockup `docs/design/handoff/mockup.dc.html` (panel: líneas 143-154; tab diff: líneas 376-383). Verde add `#7fb069`, rojo del `#c96a4e`, ámbar `#e0863f`.
- **Tests:** backend `cd server && uv run pytest -q`; frontend `cd ui && npm test`.

---

### Task 1: `git.py` — parsers puros

**Files:**
- Create: `server/ide_server/git.py`
- Test: `server/tests/test_git_parse.py`

**Interfaces:**
- Produces:
  - `parse_numstat(raw: str) -> list[dict]` → `[{"path": str, "added": int|None, "removed": int|None}]`
  - `parse_porcelain(raw: str) -> list[dict]` → `[{"path": str, "status": str}]`
  - `merge_changes(porcelain: list[dict], numstat: list[dict]) -> list[dict]` → `[{"path","status","added","removed"}]`
  - `parse_diff(raw: str) -> list[dict]` → `[{"type": "hunk"|"add"|"del"|"ctx", "text": str}]`
  - `untracked_lines(path: Path) -> int`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_git_parse.py
from pathlib import Path
from ide_server.git import (
    parse_numstat, parse_porcelain, merge_changes, parse_diff, untracked_lines,
)


def test_parse_numstat_counts_and_binary():
    raw = "3\t1\tsrc/a.py\n-\t-\timg.png\n"
    assert parse_numstat(raw) == [
        {"path": "src/a.py", "added": 3, "removed": 1},
        {"path": "img.png", "added": None, "removed": None},
    ]


def test_parse_porcelain_status_and_rename():
    raw = " M src/a.py\n?? new.txt\nR  old.py -> newp.py\n"
    assert parse_porcelain(raw) == [
        {"path": "src/a.py", "status": "M"},
        {"path": "new.txt", "status": "?"},
        {"path": "newp.py", "status": "R"},
    ]


def test_merge_changes_joins_by_path():
    porcelain = [{"path": "a.py", "status": "M"}, {"path": "new.txt", "status": "?"}]
    numstat = [{"path": "a.py", "added": 3, "removed": 1}]
    merged = {m["path"]: m for m in merge_changes(porcelain, numstat)}
    assert merged["a.py"] == {"path": "a.py", "status": "M", "added": 3, "removed": 1}
    assert merged["new.txt"] == {"path": "new.txt", "status": "?", "added": 0, "removed": 0}


def test_parse_diff_types_and_trailing_ctx():
    raw = (
        "diff --git a/x b/x\nindex 111..222 100644\n--- a/x\n+++ b/x\n"
        "@@ -1,2 +1,2 @@\n ctx\n-old\n+new\n"
    )
    assert parse_diff(raw) == [
        {"type": "hunk", "text": "@@ -1,2 +1,2 @@"},
        {"type": "ctx", "text": "ctx"},
        {"type": "del", "text": "old"},
        {"type": "add", "text": "new"},
    ]


def test_untracked_lines_text_binary_missing(tmp_path):
    f = tmp_path / "t.txt"; f.write_text("a\nb\nc")           # sin newline final
    assert untracked_lines(f) == 3
    b = tmp_path / "b.bin"; b.write_bytes(b"\x00\x01\x02")
    assert untracked_lines(b) == 0
    assert untracked_lines(tmp_path / "nope") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_git_parse.py -q`
Expected: FAIL (`ModuleNotFoundError: ide_server.git`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/git.py
from __future__ import annotations
from pathlib import Path


def parse_numstat(raw: str) -> list[dict]:
    out: list[dict] = []
    for line in raw.split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        added, removed = parts[0], parts[1]
        out.append({
            "path": "\t".join(parts[2:]),
            "added": None if added == "-" else int(added),
            "removed": None if removed == "-" else int(removed),
        })
    return out


def parse_porcelain(raw: str) -> list[dict]:
    out: list[dict] = []
    for line in raw.split("\n"):
        if not line:
            continue
        code = line[:2]
        p = line[3:]
        if " -> " in p:
            p = p.split(" -> ")[1]
        trimmed = code.strip()
        status = "?" if code == "??" else (trimmed[0] if trimmed else "?")
        out.append({"path": p, "status": status})
    return out


def merge_changes(porcelain: list[dict], numstat: list[dict]) -> list[dict]:
    by_path: dict[str, dict] = {}
    for p in porcelain:
        by_path[p["path"]] = {"path": p["path"], "status": p["status"], "added": 0, "removed": 0}
    for n in numstat:
        existing = by_path.get(n["path"]) or {
            "path": n["path"], "status": "M", "added": 0, "removed": 0}
        existing["added"] = n["added"] or 0
        existing["removed"] = n["removed"] or 0
        by_path[n["path"]] = existing
    return list(by_path.values())


def parse_diff(raw: str) -> list[dict]:
    out: list[dict] = []
    for line in raw.split("\n"):
        if (line.startswith("diff ") or line.startswith("index ")
                or line.startswith("+++") or line.startswith("---")):
            continue
        if line.startswith("@@"):
            out.append({"type": "hunk", "text": line})
        elif line.startswith("+"):
            out.append({"type": "add", "text": line[1:]})
        elif line.startswith("-"):
            out.append({"type": "del", "text": line[1:]})
        else:
            out.append({"type": "ctx", "text": line[1:] if line.startswith(" ") else line})
    while out and out[-1]["type"] == "ctx" and out[-1]["text"] == "":
        out.pop()
    return out


def untracked_lines(path: Path) -> int:
    try:
        stt = path.stat()
        if not path.is_file() or stt.st_size > 5 * 1024 * 1024:
            return 0
        data = path.read_bytes()
        if b"\x00" in data or not data:
            return 0
        n = data.count(b"\n")
        return n if data.endswith(b"\n") else n + 1
    except OSError:
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_git_parse.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/git.py server/tests/test_git_parse.py
git commit -m "feat(git): parsers puros de status/numstat/diff (port de git.js)"
```

---

### Task 2: `git.py` — `repo_status` y `file_diff_full` (integración)

**Files:**
- Modify: `server/ide_server/git.py`
- Test: `server/tests/test_git_status.py`

**Interfaces:**
- Consumes: `parse_numstat`, `parse_porcelain`, `merge_changes`, `parse_diff`, `untracked_lines` (Task 1).
- Produces:
  - `class GitError(Exception)`
  - `repo_status(cwd: Path) -> dict` → `{"name","path","branch","head","files":[...],"totalAdded","totalRemoved"}`
  - `file_diff_full(cwd: Path, path: str, status: str) -> list[dict]` → `[{"type","text"}]`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_git_status.py
import subprocess
from pathlib import Path
import pytest
from ide_server.git import repo_status, file_diff_full, GitError


def _repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    (r / "a.py").write_text("uno\ndos\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], cwd=r, check=True)
    (r / "a.py").write_text("uno\nDOS\ntres\n")     # modificado
    (r / "b.txt").write_text("nuevo\n")             # untracked
    return r


def test_repo_status_lists_modified_and_untracked(tmp_path):
    r = _repo(tmp_path)
    st = repo_status(r)
    assert st["branch"] == "main"
    by = {f["path"]: f for f in st["files"]}
    assert by["a.py"]["status"] == "M" and by["a.py"]["added"] >= 1
    assert by["b.txt"]["status"] == "?" and by["b.txt"]["added"] == 1
    assert st["totalAdded"] >= 2


def test_file_diff_full_modified_has_add_and_del(tmp_path):
    r = _repo(tmp_path)
    lines = file_diff_full(r, "a.py", "M")
    types = {l["type"] for l in lines}
    assert "add" in types and "del" in types
    assert any(l["type"] == "add" and l["text"] == "DOS" for l in lines)


def test_file_diff_full_untracked_is_all_add(tmp_path):
    r = _repo(tmp_path)
    lines = file_diff_full(r, "b.txt", "?")
    assert lines[0] == {"type": "add", "text": "nuevo"}


def test_repo_status_non_git_raises(tmp_path):
    with pytest.raises(GitError):
        repo_status(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_git_status.py -q`
Expected: FAIL (`ImportError: cannot import name 'repo_status'`)

- [ ] **Step 3: Write minimal implementation** (append to `server/ide_server/git.py`)

```python
import subprocess


class GitError(Exception):
    pass


def _git(cwd: Path, args: list[str]) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise GitError(out.stderr.strip() or f"git {' '.join(args)} falló")
    return out.stdout


def repo_status(cwd: Path) -> dict:
    branch = _git(cwd, ["branch", "--show-current"]).strip() or "(detached)"
    head = _git(cwd, ["rev-parse", "HEAD"]).strip()
    numstat = parse_numstat(_git(cwd, ["diff", "--numstat", "HEAD"]))
    porcelain = parse_porcelain(_git(cwd, ["status", "--porcelain", "-uall"]))
    files = merge_changes(porcelain, numstat)
    for f in files:
        if f["status"] == "?" and not f["added"]:
            f["added"] = untracked_lines(cwd / f["path"])
    return {
        "name": cwd.name, "path": str(cwd), "branch": branch, "head": head,
        "files": files,
        "totalAdded": sum(f["added"] or 0 for f in files),
        "totalRemoved": sum(f["removed"] or 0 for f in files),
    }


def file_diff_full(cwd: Path, path: str, status: str) -> list[dict]:
    if status == "?":
        try:
            data = (cwd / path).read_bytes()
        except OSError as exc:
            return [{"type": "ctx", "text": f"no se pudo leer el archivo: {exc}"}]
        if b"\x00" in data:
            return [{"type": "ctx", "text": "(binario)"}]
        return [{"type": "add", "text": t} for t in data.decode("utf-8", "replace").split("\n")]
    return parse_diff(_git(cwd, ["diff", "HEAD", "-U1000000", "--", path]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_git_status.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/git.py server/tests/test_git_status.py
git commit -m "feat(git): repo_status y file_diff_full contra repo real"
```

---

### Task 3: `workspace.resolve_cwd` — helper compartido (refactor de `terminals`)

**Files:**
- Modify: `server/ide_server/workspace.py`
- Modify: `server/ide_server/capabilities/terminals.py:16-30` (reemplazar `_repo_path` + `_cwd` por el helper)
- Test: `server/tests/test_workspace.py` (agregar casos)

**Interfaces:**
- Consumes: `discover_repos` (existente), `load_sessions`/`find_node` de `sessions_store`.
- Produces: `resolve_cwd(root: Path, payload: dict) -> Path` — `sessionId` → `worktreePath` (o root); `repoId` → `root/repoId`; si no, `root`. `KeyError` si el id no existe.

- [ ] **Step 1: Write the failing test** (agregar a `server/tests/test_workspace.py`)

```python
import json
import pytest
from pathlib import Path
from ide_server.workspace import resolve_cwd


def _seed(tmp_path: Path) -> Path:
    (tmp_path / ".ide").mkdir()
    wt = tmp_path / ".ide" / "worktrees" / "s1"; wt.mkdir(parents=True)
    (tmp_path / "repoA" / ".git").mkdir(parents=True)
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps(
        {"sessions": [{"id": "s1", "name": "S1", "repoId": "repoA",
                       "worktreePath": str(wt), "children": []}]}))
    return tmp_path


def test_resolve_cwd_session_returns_worktree(tmp_path):
    root = _seed(tmp_path)
    assert resolve_cwd(root, {"sessionId": "s1"}).name == "s1"


def test_resolve_cwd_repo_and_root(tmp_path):
    root = _seed(tmp_path)
    assert resolve_cwd(root, {"repoId": "repoA"}) == root / "repoA"
    assert resolve_cwd(root, {}) == root


def test_resolve_cwd_unknown_session_raises(tmp_path):
    root = _seed(tmp_path)
    with pytest.raises(KeyError):
        resolve_cwd(root, {"sessionId": "nope"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_workspace.py -q`
Expected: FAIL (`ImportError: cannot import name 'resolve_cwd'`)

- [ ] **Step 3: Write minimal implementation** (append to `server/ide_server/workspace.py`)

```python
def resolve_cwd(root: Path, payload: dict) -> Path:
    from ide_server.sessions_store import load_sessions, find_node
    if payload.get("sessionId"):
        node = find_node(load_sessions(root), payload["sessionId"])
        if node is None:
            raise KeyError(payload["sessionId"])
        return Path(node.get("worktreePath") or root)
    if payload.get("repoId"):
        for repo in discover_repos(root):
            if repo["id"] == payload["repoId"]:
                return root / repo["id"]
        raise KeyError(payload["repoId"])
    return root
```

Then refactor `server/ide_server/capabilities/terminals.py` — remove the local `_repo_path` and `_cwd` (lines 16-30) and replace with the shared helper:

```python
from ide_server.workspace import resolve_cwd
# ...dentro de register(), reemplazar el uso de _cwd(payload) por:
#   cwd = resolve_cwd(root, payload)
# y borrar las funciones _repo_path y _cwd.
```

Concretamente en `open_`: cambiar `cwd = _cwd(payload)` por `cwd = resolve_cwd(root, payload)`. Quitar los imports ahora sin uso (`discover_repos`, `find_node`, `load_sessions`) si ya no se usan en el archivo.

- [ ] **Step 4: Run test to verify it passes** (workspace + terminales verdes)

Run: `cd server && uv run pytest tests/test_workspace.py tests/test_terminals_open.py tests/test_terminals_io.py -q`
Expected: PASS (todos verdes — el refactor no rompe terminales)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/workspace.py server/ide_server/capabilities/terminals.py server/tests/test_workspace.py
git commit -m "refactor(workspace): resolve_cwd compartido entre terminals y changes"
```

---

### Task 4: Capability `changes` + wiring en `app.py`

**Files:**
- Create: `server/ide_server/capabilities/changes.py`
- Modify: `server/ide_server/app.py:12` (import) y `:23` (register)
- Test: `server/tests/test_changes_capability.py`

**Interfaces:**
- Consumes: `git.repo_status`, `git.file_diff_full` (Task 2); `workspace.resolve_cwd` (Task 3).
- Produces: capability `register(registry: Registry, root: Path) -> None` con canales `changes.list` `{sessionId?,repoId?}` → `{status}` y `changes.diff` `{sessionId?,repoId?,path,status}` → `{lines}`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_changes_capability.py
import json, subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import changes as changes_cap


def _seed(tmp_path: Path) -> Path:
    (tmp_path / ".ide").mkdir()
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "a.py").write_text("uno\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (repo / "a.py").write_text("uno\ndos\n")
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps(
        {"sessions": [{"id": "s1", "name": "S1", "repoId": "repoA",
                       "worktreePath": str(repo), "children": []}]}))
    return tmp_path


@pytest.mark.asyncio
async def test_changes_list_for_session(tmp_path):
    root = _seed(tmp_path)
    reg = Registry(); changes_cap.register(reg, root)
    out = await reg.dispatch("changes.list", {"sessionId": "s1"})
    assert out["status"]["branch"] == "main"
    assert any(f["path"] == "a.py" for f in out["status"]["files"])


@pytest.mark.asyncio
async def test_changes_diff_for_session(tmp_path):
    root = _seed(tmp_path)
    reg = Registry(); changes_cap.register(reg, root)
    out = await reg.dispatch("changes.diff", {"sessionId": "s1", "path": "a.py", "status": "M"})
    assert any(l["type"] == "add" and l["text"] == "dos" for l in out["lines"])


@pytest.mark.asyncio
async def test_changes_list_non_git_root_raises(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps({"sessions": []}))
    reg = Registry(); changes_cap.register(reg, tmp_path)
    from ide_server.git import GitError
    with pytest.raises(GitError):
        await reg.dispatch("changes.list", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_changes_capability.py -q`
Expected: FAIL (`ModuleNotFoundError: ...capabilities.changes`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/capabilities/changes.py
from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server import git
from ide_server.workspace import resolve_cwd


def register(registry: Registry, root: Path) -> None:
    async def list_(payload: dict) -> dict:
        return {"status": git.repo_status(resolve_cwd(root, payload))}

    async def diff_(payload: dict) -> dict:
        cwd = resolve_cwd(root, payload)
        return {"lines": git.file_diff_full(cwd, payload["path"], payload.get("status") or "M")}

    registry.register("changes.list", list_)
    registry.register("changes.diff", diff_)
```

Wire into `server/ide_server/app.py` — add import next to the other capability imports:

```python
from ide_server.capabilities import changes as changes_cap
```

and register it after `customizations_cap.register(registry, root)`:

```python
    changes_cap.register(registry, root)
```

- [ ] **Step 4: Run test to verify it passes** (capability + app arranca)

Run: `cd server && uv run pytest tests/test_changes_capability.py tests/test_app.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/changes.py server/ide_server/app.py server/tests/test_changes_capability.py
git commit -m "feat(changes): capability changes.list/diff + wiring en app"
```

---

### Task 5: Transport `changesChannel.ts`

**Files:**
- Create: `ui/src/transport/changesChannel.ts`
- Test: `ui/src/transport/changesChannel.test.ts`

**Interfaces:**
- Consumes: `WsClient.request` (existente).
- Produces:
  - `interface FileChange { path: string; status: string; added: number | null; removed: number | null }`
  - `interface RepoStatus { name: string; path: string; branch: string; head: string; files: FileChange[]; totalAdded: number; totalRemoved: number }`
  - `type DiffLineType = "hunk" | "add" | "del" | "ctx"`
  - `interface DiffLine { type: DiffLineType; text: string }`
  - `fetchChanges(ws, { sessionId?: string | null }): Promise<RepoStatus>`
  - `fetchDiff(ws, { sessionId?: string | null; path: string; status: string }): Promise<DiffLine[]>`

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/transport/changesChannel.test.ts
import { describe, it, expect, vi } from "vitest";
import { fetchChanges, fetchDiff } from "./changesChannel";

describe("changesChannel", () => {
  it("fetchChanges pide changes.list con sessionId y devuelve status", async () => {
    const status = { name: "repoA", branch: "main", files: [] };
    const ws = { request: vi.fn().mockResolvedValue({ status }) } as any;
    expect(await fetchChanges(ws, { sessionId: "s1" })).toBe(status);
    expect(ws.request).toHaveBeenCalledWith("changes.list", { sessionId: "s1" });
  });

  it("fetchDiff pide changes.diff con path/status y devuelve lines", async () => {
    const lines = [{ type: "add", text: "x" }];
    const ws = { request: vi.fn().mockResolvedValue({ lines }) } as any;
    expect(await fetchDiff(ws, { sessionId: "s1", path: "a.py", status: "M" })).toBe(lines);
    expect(ws.request).toHaveBeenCalledWith("changes.diff", { sessionId: "s1", path: "a.py", status: "M" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- changesChannel`
Expected: FAIL (no existe `./changesChannel`)

- [ ] **Step 3: Write minimal implementation**

```typescript
// ui/src/transport/changesChannel.ts
import type { WsClient } from "./ws";

export interface FileChange { path: string; status: string; added: number | null; removed: number | null }
export interface RepoStatus {
  name: string; path: string; branch: string; head: string;
  files: FileChange[]; totalAdded: number; totalRemoved: number;
}
export type DiffLineType = "hunk" | "add" | "del" | "ctx";
export interface DiffLine { type: DiffLineType; text: string }

export async function fetchChanges(
  ws: WsClient, opts: { sessionId?: string | null },
): Promise<RepoStatus> {
  return (await ws.request("changes.list", { sessionId: opts.sessionId ?? undefined })).status;
}

export async function fetchDiff(
  ws: WsClient, opts: { sessionId?: string | null; path: string; status: string },
): Promise<DiffLine[]> {
  return (await ws.request("changes.diff", {
    sessionId: opts.sessionId ?? undefined, path: opts.path, status: opts.status,
  })).lines;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- changesChannel`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/changesChannel.ts ui/src/transport/changesChannel.test.ts
git commit -m "feat(changes): transport changesChannel (list + diff)"
```

---

### Task 6: State `changes.ts` (store Zustand)

**Files:**
- Create: `ui/src/state/changes.ts`
- Test: `ui/src/state/changes.test.ts`

**Interfaces:**
- Consumes: `fetchChanges` (Task 5), `getWs` (existente).
- Produces: `useChanges` con `{ status: RepoStatus | null; loading: boolean; error: string | null; load(sessionId: string | null): Promise<void> }`. En error limpia `status` y setea `error`.

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/state/changes.test.ts
import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchChanges = vi.fn();
vi.mock("../transport/changesChannel", () => ({ fetchChanges: (...a: any[]) => fetchChanges(...a) }));

import { useChanges } from "./changes";

beforeEach(() => {
  fetchChanges.mockReset();
  useChanges.setState({ status: null, loading: false, error: null });
});

describe("state/changes", () => {
  it("load exitoso guarda status y limpia error", async () => {
    const status = { branch: "main", files: [] };
    fetchChanges.mockResolvedValue(status);
    await useChanges.getState().load("s1");
    expect(useChanges.getState()).toMatchObject({ status, error: null, loading: false });
  });

  it("load con error limpia status y setea error", async () => {
    useChanges.setState({ status: { branch: "old", files: [] } as any });
    fetchChanges.mockRejectedValue({ message: "no es repo git" });
    await useChanges.getState().load("s1");
    expect(useChanges.getState().status).toBeNull();
    expect(useChanges.getState().error).toBe("no es repo git");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- state/changes`
Expected: FAIL (no existe `./changes`)

- [ ] **Step 3: Write minimal implementation**

```typescript
// ui/src/state/changes.ts
import { create } from "zustand";
import type { RepoStatus } from "../transport/changesChannel";
import { fetchChanges } from "../transport/changesChannel";
import { getWs } from "../transport/wsClient";

interface ChangesState {
  status: RepoStatus | null;
  loading: boolean;
  error: string | null;
  load: (sessionId: string | null) => Promise<void>;
}

export const useChanges = create<ChangesState>((set) => ({
  status: null, loading: false, error: null,
  load: async (sessionId) => {
    set({ loading: true });
    try {
      const status = await fetchChanges(getWs(), { sessionId });
      set({ status, loading: false, error: null });
    } catch (e: unknown) {
      const message = (e as { message?: string })?.message ?? "desconectado";
      set({ status: null, loading: false, error: message });
    }
  },
}));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- state/changes`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ui/src/state/changes.ts ui/src/state/changes.test.ts
git commit -m "feat(changes): store zustand con load y estado de error"
```

---

### Task 7: `ChangesPanel` + registro del módulo (rail)

**Files:**
- Create: `ui/src/modules/changes/ChangesPanel.tsx`
- Create: `ui/src/modules/changes/register.tsx`
- Create: `ui/src/modules/changes/ChangesPanel.test.tsx`
- Create: `ui/src/modules/changes/register.test.ts`
- Modify: `ui/src/modules/stubs.tsx` (quitar la línea de `changes` y el import `FileDiff` si queda sin uso)
- Modify: `ui/src/App.tsx:2` (agregar `import "./modules/changes/register";`)

**Interfaces:**
- Consumes: `useChanges` (Task 6), `useSessions` (`activeSessionId`), `useStore` (`openTab`).
- Produces: `ChangesPanel` (default export nombrado); módulo registrado con `id: "changes"`. Click en archivo abre tab `id: "diff:<sessionId>:<status>:<path>"`, `type: "file"`, `label: basename(path)`.

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/modules/changes/ChangesPanel.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useChanges } from "../../state/changes";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const load = vi.fn();
vi.mock("../../state/changes", async (orig) => {
  const mod = await (orig() as any);
  return mod;
});
import { ChangesPanel } from "./ChangesPanel";

beforeEach(() => {
  vi.useFakeTimers();
  useSessions.setState({ activeSessionId: "s1" } as any);
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
  useChanges.setState({
    status: { name: "r", path: "/r", branch: "main", head: "h",
      files: [{ path: "src/a.py", status: "M", added: 3, removed: 1 }],
      totalAdded: 3, totalRemoved: 1 },
    loading: false, error: null, load,
  });
});

describe("ChangesPanel", () => {
  it("lista los archivos y abre una tab al clickear", () => {
    render(<ChangesPanel />);
    expect(screen.getByText("src/a.py")).toBeInTheDocument();
    fireEvent.click(screen.getByText("src/a.py"));
    const tab = useStore.getState().openTabs[0];
    expect(tab).toMatchObject({ id: "diff:s1:M:src/a.py", type: "file", label: "a.py" });
    vi.useRealTimers();
  });

  it("muestra 'desconectado' cuando hay error", () => {
    useChanges.setState({ status: null, loading: false, error: "no es repo git", load });
    render(<ChangesPanel />);
    expect(screen.getByText(/desconectado/i)).toBeInTheDocument();
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- ChangesPanel`
Expected: FAIL (no existe `./ChangesPanel`)

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/modules/changes/ChangesPanel.tsx
import { useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";
import { useChanges } from "../../state/changes";

const basename = (p: string) => p.split("/").pop() || p;

export function ChangesPanel() {
  const activeSessionId = useSessions((s) => s.activeSessionId);
  const openTab = useStore((s) => s.openTab);
  const { status, error, load } = useChanges();

  useEffect(() => {
    load(activeSessionId);
    const t = setInterval(() => load(activeSessionId), 4000);
    return () => clearInterval(t);
  }, [activeSessionId, load]);

  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Archivos modificados
        </div>
        <button aria-label="refrescar" onClick={() => load(activeSessionId)}
          className="text-muted-foreground hover:text-foreground">
          <RefreshCw size={13} />
        </button>
      </div>
      {status && !error && (
        <div className="mb-2 flex items-center gap-2 px-1 font-mono text-[10.5px] text-muted-foreground">
          <span className="text-[#e0863f]">{status.branch}</span>
          <span className="text-[#7fb069]">+{status.totalAdded}</span>
          <span className="text-[#c96a4e]">-{status.totalRemoved}</span>
        </div>
      )}
      {error && <div className="px-1 py-2 text-xs text-destructive">desconectado — {error}</div>}
      {!error && status && status.files.length === 0 && (
        <div className="px-1 py-2 text-xs text-muted-foreground">sin cambios</div>
      )}
      {!error && status?.files.map((f) => (
        <button key={f.path}
          onClick={() => openTab({
            id: `diff:${activeSessionId ?? ""}:${f.status}:${f.path}`,
            type: "file", label: basename(f.path),
          })}
          className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 hover:bg-accent">
          <span className="min-w-0 flex-1 truncate text-left font-mono text-[11.5px] text-foreground">
            {f.path}
          </span>
          <span className="font-mono text-[10.5px] text-[#7fb069]">+{f.added ?? 0}</span>
          <span className="font-mono text-[10.5px] text-[#c96a4e]">-{f.removed ?? 0}</span>
        </button>
      ))}
    </div>
  );
}
```

```tsx
// ui/src/modules/changes/register.tsx
import { FileDiff } from "lucide-react";
import { registerModule } from "../registry";
import { ChangesPanel } from "./ChangesPanel";

registerModule({ id: "changes", title: "Changed files", icon: FileDiff, Panel: ChangesPanel });
```

```typescript
// ui/src/modules/changes/register.test.ts
import { describe, it, expect } from "vitest";
import "../stubs";
import "./register";
import { getModules } from "../registry";
import { ChangesPanel } from "./ChangesPanel";

describe("registro changes", () => {
  it("usa el ChangesPanel real (no el stub)", () => {
    expect(getModules().find((m) => m.id === "changes")?.Panel).toBe(ChangesPanel);
  });
});
```

Edit `ui/src/modules/stubs.tsx` — remove the `changes` registration line so the real module wins (the registry ignores duplicate ids; removing the stub avoids order-dependence):

```tsx
// Borrar esta línea:
// registerModule({ id: "changes", title: "Changed files", icon: FileDiff, Panel: Stub("Changed files") });
```

Also drop `FileDiff` from the stubs import if it is no longer referenced there.

Edit `ui/src/App.tsx` — add the register import next to the terminal one:

```tsx
import "./modules/changes/register";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- changes && cd ui && npx tsc --noEmit`
Expected: PASS (ChangesPanel + register verdes; tsc limpio)

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/changes ui/src/modules/stubs.tsx ui/src/App.tsx
git commit -m "feat(changes): ChangesPanel en el rail con polling + apertura de tab"
```

---

### Task 8: `DiffTab` + ruteo en `MainPanel`

**Files:**
- Create: `ui/src/main/DiffTab.tsx`
- Create: `ui/src/main/DiffTab.test.tsx`
- Modify: `ui/src/layout/MainPanel.tsx:13-17` (rutear `type === "file"` a `DiffTab`)

**Interfaces:**
- Consumes: `fetchDiff` (Task 5), `getWs`. Recibe `id: "diff:<sessionId>:<status>:<path>"`.
- Produces: `DiffTab({ id }: { id: string })` — parsea el id, hace `fetchDiff`, renderiza líneas por tipo con bg/color; muestra error si falla.

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/main/DiffTab.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchDiff = vi.fn();
vi.mock("../transport/changesChannel", () => ({ fetchDiff: (...a: any[]) => fetchDiff(...a) }));
import { DiffTab } from "./DiffTab";

beforeEach(() => fetchDiff.mockReset());

describe("DiffTab", () => {
  it("parsea el id y renderiza líneas add/del/ctx", async () => {
    fetchDiff.mockResolvedValue([
      { type: "ctx", text: "uno" },
      { type: "del", text: "viejo" },
      { type: "add", text: "nuevo" },
    ]);
    render(<DiffTab id="diff:s1:M:src/a.py" />);
    await waitFor(() => screen.getByText("nuevo"));
    expect(screen.getByText("viejo")).toBeInTheDocument();
    expect(fetchDiff).toHaveBeenCalledWith({ sessionId: "s1", path: "src/a.py", status: "M" });
    expect(screen.getByText("src/a.py")).toBeInTheDocument();
  });

  it("muestra error si el diff falla", async () => {
    fetchDiff.mockRejectedValue({ message: "no es repo git" });
    render(<DiffTab id="diff:s1:M:src/a.py" />);
    await waitFor(() => screen.getByText(/no se pudo leer el diff/i));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- DiffTab`
Expected: FAIL (no existe `./DiffTab`)

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/main/DiffTab.tsx
import { useEffect, useState } from "react";
import { fetchDiff, type DiffLine, type DiffLineType } from "../transport/changesChannel";
import { getWs } from "../transport/wsClient";

const STYLE: Record<DiffLineType, { bg: string; color: string }> = {
  add: { bg: "rgba(127,176,105,0.14)", color: "#cfe8bf" },
  del: { bg: "rgba(201,106,78,0.14)", color: "#e8c3b8" },
  hunk: { bg: "transparent", color: "#e0863f" },
  ctx: { bg: "transparent", color: "#cfc9bd" },
};

// id = "diff:<sessionId>:<status>:<path>"; path puede contener ":".
function parseId(id: string): { sessionId: string | null; status: string; path: string } {
  const rest = id.slice("diff:".length);
  const i1 = rest.indexOf(":");
  const i2 = rest.indexOf(":", i1 + 1);
  return {
    sessionId: rest.slice(0, i1) || null,
    status: rest.slice(i1 + 1, i2),
    path: rest.slice(i2 + 1),
  };
}

export function DiffTab({ id }: { id: string }) {
  const { sessionId, status, path } = parseId(id);
  const [lines, setLines] = useState<DiffLine[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDiff(getWs(), { sessionId, path, status })
      .then((ls) => { if (!cancelled) { setLines(ls); setError(null); } })
      .catch((e: unknown) => {
        if (!cancelled) setError((e as { message?: string })?.message ?? "desconectado");
      });
    return () => { cancelled = true; };
  }, [id]);

  if (error) {
    return <div className="p-4 text-sm text-destructive">no se pudo leer el diff — {error}</div>;
  }
  return (
    <div className="h-full overflow-auto py-4">
      <div className="px-5 pb-3 font-mono text-xs text-muted-foreground">{path}</div>
      {lines.map((l, i) => (
        <div key={i} className="whitespace-pre px-5 font-mono text-[12.5px] leading-relaxed"
          style={{ background: STYLE[l.type].bg, color: STYLE[l.type].color }}>
          {l.text || " "}
        </div>
      ))}
    </div>
  );
}
```

Edit `ui/src/layout/MainPanel.tsx` — import and route `type === "file"`:

```tsx
import { DiffTab } from "../main/DiffTab";
// ...
{active?.type === "terminal" ? (
  <TerminalTab id={active.id} />
) : active?.type === "file" ? (
  <DiffTab id={active.id} />
) : active ? (
  <div className="p-4 text-sm text-muted-foreground">{`Tab: ${active.id}`}</div>
) : (
  <ChatView />
)}
```

- [ ] **Step 4: Run test to verify it passes** (DiffTab + suite completa + build)

Run: `cd ui && npm test -- DiffTab && cd ui && npx tsc --noEmit && npm run build`
Expected: PASS; tsc limpio; build ok

- [ ] **Step 5: Commit**

```bash
git add ui/src/main/DiffTab.tsx ui/src/main/DiffTab.test.tsx ui/src/layout/MainPanel.tsx
git commit -m "feat(changes): DiffTab con diff de archivo completo resaltado"
```

---

## Verificación final (post Task 8)

- [ ] Backend completo: `cd server && uv run pytest -q` → todo verde (95 previos + nuevos).
- [ ] Frontend completo: `cd ui && npm test` → todo verde; `npx tsc --noEmit` limpio; `npm run build` ok.
- [ ] E2E manual (opcional, ver HANDOFF "Cómo correr"): levantar backend con `~/ide-demo` + `npm run dev`, seleccionar una sesión, abrir el rail "Changed files", editar un archivo en el worktree, verificar que el polling lo muestra, clickear y ver el diff resaltado en una tab.
- [ ] Actualizar `docs/superpowers/HANDOFF.md`: mover R4 a "cerrado", quitarlo de "próximos pasos".

## Self-Review (notas del plan)

- **Cobertura del spec:** parsers (T1), repo_status/file_diff_full incl. untracked/binario/borrado (T2), resolve_cwd compartido (T3), capability + envelope de error (T4), transport (T5), store con error (T6), panel con polling + apertura de tab + estado error/vacío (T7), tab de diff resaltada + ruteo (T8). Fuera de alcance (watchers, hunks-only, staged/unstaged, acciones sobre archivos) no se implementa.
- **Status en la tab:** se codifica en el id (`diff:<sessionId>:<status>:<path>`) para que `DiffTab` sepa si el archivo es untracked (`?` → todo-add) sin depender del store; el path va último para tolerar `:` en rutas.
- **Sin fallos silenciosos:** `git.GitError` sube por el `bus.py` como `handler_error`; el store limpia `status` y setea `error`; panel y tab muestran "desconectado".
