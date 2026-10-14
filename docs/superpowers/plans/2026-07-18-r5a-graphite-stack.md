# R5a — Graphite stack (lectura) + restack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar el ítem "Graphite" del rail: un stack de branches (del repo de la sesión activa) inline — branch → commits → archivos → diff del archivo en ese commit — con marca `needsRestack` (conector punteado) y acción de restack con confirmación.

**Architecture:** Molde de plugin de R4/R6 — módulos puros backend (`graphite.py`, extensiones a `git.py`/`workspace.py`) + capability en `app.py` + transport + store Zustand + módulo del rail. La estructura del stack sale del SQLite de gt (`<repo>/.git/.graphite_metadata.db`); commits/archivos de git (reusa `git.py`); el diff de archivo por commit reusa el `DiffTab` de R4 extendido. Restack corre `gt` no-interactivo.

**Tech Stack:** Backend Python/FastAPI (`uv`, `pytest`, `sqlite3` stdlib, `subprocess`); frontend React + Vite + TS (Zustand, Tailwind/shadcn, Vitest + Testing Library).

## Global Constraints

- **Sin fallos silenciosos:** errores gt/git viajan como envelope `{type:"error",payload:{code,message}}` (el `bus.py` envuelve cualquier `Exception` en `handler_error`). El front limpia el estado y muestra "desconectado", nunca stack/diff viejos. `graphite.restack` **nunca** deja el repo a medio-rebase: ante fallo hace `git rebase --abort` defensivo y levanta `GraphiteError`.
- **TDD estricto:** test que falla → implementación mínima → test que pasa → commit. Un commit por tarea.
- **Conventional commits en español**, atómicos.
- **Fidelidad UI 1a ámbar/terminal:** tokens en `docs/design/REFERENCES.md`; mockup `docs/design/handoff/mockup.dc.html` (stack: líneas 155-195). Verde `#7fb069`, rojo `#c96a4e`, ámbar `#e0863f`.
- **Reusa R4:** `git.parse_numstat`, `git.parse_diff`, el patrón subprocess `git._git`, y `DiffTab`/`MainPanel` (ruteo `type:"file"` — no se toca el layout).
- **Tests:** backend `cd server && uv run pytest -q`; frontend `cd ui && npm test`.
- **Esquema SQLite de gt** (`branch_metadata`): `branch_name` (PK), `parent_branch_name`, `parent_branch_revision`, `branch_revision`, `children`, `state`, `validation_result`, `parent_head_revision`, `last_submitted_version`. R5a usa `branch_name`, `parent_branch_name`, `parent_branch_revision`, `branch_revision`.

---

### Task 1: `git.file_diff_at_commit` + `changes.diff` acepta `sha`

**Files:**
- Modify: `server/ide_server/git.py` (append)
- Modify: `server/ide_server/capabilities/changes.py`
- Test: `server/tests/test_git_commit_diff.py`
- Test: `server/tests/test_changes_capability.py` (append)

**Interfaces:**
- Consumes: `git.parse_diff`, `git._git` (R4).
- Produces: `git.file_diff_at_commit(cwd: Path, sha: str, path: str) -> list[dict]` → `[{"type","text"}]`. `changes.diff` payload acepta `sha?`: si viene → `file_diff_at_commit`, si no → R4.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_git_commit_diff.py
import subprocess
from pathlib import Path
from ide_server.git import file_diff_at_commit


def _repo(tmp_path: Path) -> tuple[Path, str]:
    r = tmp_path / "repo"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    (r / "a.py").write_text("uno\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "c1"], cwd=r, check=True)
    (r / "a.py").write_text("uno\ndos\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "c2"], cwd=r, check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r,
                         capture_output=True, text=True).stdout.strip()
    return r, sha


def test_file_diff_at_commit_shows_that_commit_change(tmp_path):
    r, sha = _repo(tmp_path)
    lines = file_diff_at_commit(r, sha, "a.py")
    assert any(l["type"] == "add" and l["text"] == "dos" for l in lines)
    # el commit c2 no tocó la línea 'uno' salvo como contexto (no como add/del)
    assert not any(l["type"] == "del" for l in lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_git_commit_diff.py -q`
Expected: FAIL (`ImportError: cannot import name 'file_diff_at_commit'`)

- [ ] **Step 3: Write minimal implementation** (append to `server/ide_server/git.py`)

```python
def file_diff_at_commit(cwd: Path, sha: str, path: str) -> list[dict]:
    # `git show <sha> --format=` suprime el header de commit → solo el diff del archivo.
    return parse_diff(_git(cwd, ["show", sha, "--format=", "-U1000000", "--", path]))
```

Then modify `server/ide_server/capabilities/changes.py` `diff_` to honor `sha`:

```python
    async def diff_(payload: dict) -> dict:
        cwd = resolve_cwd(root, payload)
        if payload.get("sha"):
            return {"lines": git.file_diff_at_commit(cwd, payload["sha"], payload["path"])}
        return {"lines": git.file_diff_full(cwd, payload["path"], payload.get("status") or "M")}
```

- [ ] **Step 4: Add the capability test** (append to `server/tests/test_changes_capability.py`)

```python
@pytest.mark.asyncio
async def test_changes_diff_at_commit(tmp_path):
    root = _seed(tmp_path)   # helper ya existente en el archivo (repoA con a.py modificado)
    repo = root / "repoA"
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "c2"], cwd=repo, check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                         capture_output=True, text=True).stdout.strip()
    reg = Registry(); changes_cap.register(reg, root)
    out = await reg.dispatch("changes.diff", {"sessionId": "s1", "path": "a.py", "sha": sha})
    assert any(l["type"] == "add" and l["text"] == "dos" for l in out["lines"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && uv run pytest tests/test_git_commit_diff.py tests/test_changes_capability.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/ide_server/git.py server/ide_server/capabilities/changes.py server/tests/test_git_commit_diff.py server/tests/test_changes_capability.py
git commit -m "feat(git): diff de archivo por commit (git show) + changes.diff acepta sha"
```

---

### Task 2: `graphite.build_stack` (puro) + `GraphiteError`

**Files:**
- Create: `server/ide_server/graphite.py`
- Test: `server/tests/test_graphite_build.py`

**Interfaces:**
- Produces:
  - `class GraphiteError(Exception)`
  - `build_stack(rows: list[dict], current: str | None) -> list[dict]` — `rows` = `[{name, parent, parentRevision, revision}]`. Devuelve lista ordenada trunk→hojas; cada item `{name, parent, isTrunk, current, needsRestack, revision}`. `needsRestack = parent is not None and parentRevision != <revision del row del padre>`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_graphite_build.py
from ide_server.graphite import build_stack, GraphiteError


def test_build_stack_orders_and_flags_current():
    rows = [
        {"name": "main", "parent": None, "parentRevision": None, "revision": "r0"},
        {"name": "feat-a", "parent": "main", "parentRevision": "r0", "revision": "r1"},
        {"name": "feat-b", "parent": "feat-a", "parentRevision": "r1", "revision": "r2"},
    ]
    stack = build_stack(rows, current="feat-a")
    assert [b["name"] for b in stack] == ["main", "feat-a", "feat-b"]
    trunk = stack[0]
    assert trunk["isTrunk"] is True and trunk["needsRestack"] is False
    assert stack[1]["current"] is True and stack[2]["current"] is False
    # todas al día: parentRevision coincide con la revision del padre
    assert all(b["needsRestack"] is False for b in stack)


def test_build_stack_detects_needs_restack():
    # feat-a fue apilada sobre r0 pero main ahora está en rX → desactualizada
    rows = [
        {"name": "main", "parent": None, "parentRevision": None, "revision": "rX"},
        {"name": "feat-a", "parent": "main", "parentRevision": "r0", "revision": "r1"},
    ]
    stack = build_stack(rows, current=None)
    a = next(b for b in stack if b["name"] == "feat-a")
    assert a["needsRestack"] is True


def test_build_stack_no_trunk_raises():
    rows = [{"name": "orphan", "parent": "ghost", "parentRevision": "r", "revision": "r1"}]
    try:
        build_stack(rows, current=None)
        assert False, "esperaba GraphiteError"
    except GraphiteError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_graphite_build.py -q`
Expected: FAIL (`ModuleNotFoundError: ide_server.graphite`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/graphite.py
from __future__ import annotations
from pathlib import Path


class GraphiteError(Exception):
    pass


def build_stack(rows: list[dict], current: str | None) -> list[dict]:
    by_name = {r["name"]: r for r in rows}
    children: dict[str, list[str]] = {}
    trunk = None
    for r in rows:
        if r["parent"] is None:
            trunk = r["name"]
        else:
            children.setdefault(r["parent"], []).append(r["name"])
    if trunk is None:
        raise GraphiteError("stack sin trunk (ninguna branch sin padre)")

    out: list[dict] = []

    def visit(name: str) -> None:
        r = by_name[name]
        parent = r["parent"]
        needs = False
        if parent is not None and parent in by_name:
            needs = r["parentRevision"] != by_name[parent]["revision"]
        out.append({
            "name": name, "parent": parent, "isTrunk": parent is None,
            "current": name == current, "needsRestack": needs, "revision": r["revision"],
        })
        for child in sorted(children.get(name, [])):
            visit(child)

    visit(trunk)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_graphite_build.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/graphite.py server/tests/test_graphite_build.py
git commit -m "feat(graphite): build_stack puro con needsRestack + GraphiteError"
```

---

### Task 3: `graphite.read_stack` (sqlite) + `branch_commits` + `commit_files`

**Files:**
- Modify: `server/ide_server/graphite.py` (append)
- Test: `server/tests/test_graphite_read.py`

**Interfaces:**
- Consumes: `git.parse_numstat`, `git._git` (R4).
- Produces:
  - `read_stack(repo_path: Path) -> list[dict]` → `[{name, parent, parentRevision, revision}]`. `GraphiteError` si falta la db / la tabla / error sqlite.
  - `branch_commits(repo_path: Path, revision: str, parent_revision: str | None) -> list[dict]` → trunk (`parent_revision is None`) → `[]`; si no `[{hash, message}]`.
  - `commit_files(repo_path: Path, sha: str) -> list[dict]` → `[{path, added, removed}]`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_graphite_read.py
import sqlite3
import subprocess
from pathlib import Path
import pytest
from ide_server.graphite import read_stack, branch_commits, commit_files, GraphiteError


def _gitdir(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    return repo


def _seed_db(repo: Path, rows: list[tuple]) -> None:
    db = repo / ".git" / ".graphite_metadata.db"
    con = sqlite3.connect(db)
    con.execute(
        'CREATE TABLE "branch_metadata" ("branch_name" text not null primary key, '
        '"parent_branch_name" text, "parent_branch_revision" text, "branch_revision" text)')
    con.executemany(
        'INSERT INTO branch_metadata '
        '("branch_name","parent_branch_name","parent_branch_revision","branch_revision") '
        'VALUES (?,?,?,?)', rows)
    con.commit(); con.close()


def test_read_stack_returns_normalized_rows(tmp_path):
    repo = _gitdir(tmp_path)
    _seed_db(repo, [
        ("main", None, None, "r0"),
        ("feat-a", "main", "r0", "r1"),
    ])
    rows = {r["name"]: r for r in read_stack(repo)}
    assert rows["main"] == {"name": "main", "parent": None, "parentRevision": None, "revision": "r0"}
    assert rows["feat-a"]["parent"] == "main" and rows["feat-a"]["revision"] == "r1"


def test_read_stack_missing_db_raises(tmp_path):
    with pytest.raises(GraphiteError):
        read_stack(_gitdir(tmp_path))


def _real_repo(tmp_path: Path) -> tuple[Path, str, str]:
    r = tmp_path / "rr"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    (r / "a.py").write_text("uno\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "base"], cwd=r, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True).stdout.strip()
    (r / "a.py").write_text("uno\ndos\n")
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "agrega dos"], cwd=r, check=True)
    tip = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r, capture_output=True, text=True).stdout.strip()
    return r, base, tip


def test_branch_commits_and_files(tmp_path):
    r, base, tip = _real_repo(tmp_path)
    commits = branch_commits(r, tip, base)
    assert len(commits) == 1 and commits[0]["message"] == "agrega dos"
    assert branch_commits(r, tip, None) == []      # trunk → sin commits
    files = commit_files(r, tip)
    assert any(f["path"] == "a.py" and f["added"] == 1 for f in files)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_graphite_read.py -q`
Expected: FAIL (`ImportError: cannot import name 'read_stack'`)

- [ ] **Step 3: Write minimal implementation** (append to `server/ide_server/graphite.py`)

```python
import sqlite3
from ide_server import git


def read_stack(repo_path: Path) -> list[dict]:
    db = repo_path / ".git" / ".graphite_metadata.db"
    if not db.exists():
        raise GraphiteError(f"no es un repo Graphite (falta {db.name})")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            cur = con.execute(
                "SELECT branch_name, parent_branch_name, parent_branch_revision, branch_revision "
                "FROM branch_metadata")
            rows = cur.fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise GraphiteError(f"no se pudo leer la metadata de Graphite: {exc}") from exc
    return [{"name": n, "parent": p, "parentRevision": pr, "revision": rev}
            for (n, p, pr, rev) in rows]


def branch_commits(repo_path: Path, revision: str, parent_revision: str | None) -> list[dict]:
    if parent_revision is None:
        return []
    raw = git._git(repo_path, ["log", "--format=%h%x1f%s", f"{parent_revision}..{revision}"])
    out: list[dict] = []
    for line in raw.split("\n"):
        if not line:
            continue
        h, _, msg = line.partition("\x1f")
        out.append({"hash": h, "message": msg})
    return out


def commit_files(repo_path: Path, sha: str) -> list[dict]:
    raw = git._git(repo_path, ["show", "--numstat", "--format=", sha])
    return [{"path": f["path"], "added": f["added"], "removed": f["removed"]}
            for f in git.parse_numstat(raw)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_graphite_read.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/graphite.py server/tests/test_graphite_read.py
git commit -m "feat(graphite): read_stack (sqlite gt) + branch_commits + commit_files"
```

---

### Task 4: `workspace.resolve_repo`

**Files:**
- Modify: `server/ide_server/workspace.py` (append)
- Test: `server/tests/test_workspace.py` (append)

**Interfaces:**
- Produces: `resolve_repo(root: Path, payload: dict) -> Path` — `sessionId` → `root/<repoId de la sesión>` (`KeyError` si la sesión no existe o no tiene repoId); `repoId` → `root/<repoId>`; si no → `KeyError`.

- [ ] **Step 1: Write the failing test** (append a `server/tests/test_workspace.py`)

```python
from ide_server.workspace import resolve_repo


def test_resolve_repo_session_returns_repo(tmp_path):
    root = _seed(tmp_path)   # helper ya existente: sesión s1 con repoId repoA
    assert resolve_repo(root, {"sessionId": "s1"}) == root / "repoA"


def test_resolve_repo_repoid_and_errors(tmp_path):
    root = _seed(tmp_path)
    assert resolve_repo(root, {"repoId": "repoA"}) == root / "repoA"
    with pytest.raises(KeyError):
        resolve_repo(root, {})
    with pytest.raises(KeyError):
        resolve_repo(root, {"sessionId": "nope"})
```

Nota: si el helper `_seed` existente en `test_workspace.py` no crea una sesión con `repoId`, agrega una sesión `{"id":"s1","repoId":"repoA","worktreePath":...,"children":[]}` a su `sessions.json` (mirar cómo lo hace `test_resolve_cwd_session_returns_worktree`, que ya siembra `s1`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_workspace.py -q`
Expected: FAIL (`ImportError: cannot import name 'resolve_repo'`)

- [ ] **Step 3: Write minimal implementation** (append a `server/ide_server/workspace.py`)

```python
def resolve_repo(root: Path, payload: dict) -> Path:
    from ide_server.sessions_store import load_sessions, find_node
    if payload.get("sessionId"):
        node = find_node(load_sessions(root), payload["sessionId"])
        if node is None or not node.get("repoId"):
            raise KeyError(payload["sessionId"])
        return root / node["repoId"]
    if payload.get("repoId"):
        return root / payload["repoId"]
    raise KeyError("sin contexto de repo")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_workspace.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/workspace.py server/tests/test_workspace.py
git commit -m "feat(workspace): resolve_repo (repo de la sesión, no worktree)"
```

---

### Task 5: `graphite.restack`

**Files:**
- Modify: `server/ide_server/graphite.py` (append)
- Test: `server/tests/test_graphite_restack.py`

**Interfaces:**
- Produces: `restack(repo_path: Path, branch: str) -> None` — corre `gt restack --branch <branch> --only --no-interactive -q --cwd <repo>`. Ante fallo: `git rebase --abort` defensivo (ignora su error) y levanta `GraphiteError`. `gt` ausente → `GraphiteError`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_graphite_restack.py
import shutil
import subprocess
from pathlib import Path
import pytest
from ide_server.graphite import restack, GraphiteError

pytestmark = pytest.mark.skipif(shutil.which("gt") is None, reason="gt no instalado")


def test_restack_on_non_graphite_repo_raises_and_cleans(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=r, check=True)
    # branch inexistente / repo no trackeado por gt → gt falla → GraphiteError
    with pytest.raises(GraphiteError):
        restack(r, "no-existe")
    # el repo no quedó a medio-rebase
    assert not (r / ".git" / "rebase-merge").exists()
    assert not (r / ".git" / "rebase-apply").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_graphite_restack.py -q`
Expected: FAIL (`ImportError: cannot import name 'restack'`) — o skip si no hay `gt` (en tu máquina hay gt, así que corre).

- [ ] **Step 3: Write minimal implementation** (append a `server/ide_server/graphite.py`)

```python
import shutil
import subprocess


def restack(repo_path: Path, branch: str) -> None:
    if shutil.which("gt") is None:
        raise GraphiteError("gt (Graphite) no está instalado")
    out = subprocess.run(
        ["gt", "restack", "--branch", branch, "--only", "--no-interactive", "-q",
         "--cwd", str(repo_path)],
        capture_output=True, text=True)
    if out.returncode != 0:
        # defensivo: no dejar el repo a medio-rebase
        subprocess.run(["git", "-C", str(repo_path), "rebase", "--abort"],
                       capture_output=True, text=True)
        msg = (out.stderr or out.stdout or "").strip() or "gt restack falló"
        raise GraphiteError(f"restack falló (¿conflictos?): {msg}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_graphite_restack.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/graphite.py server/tests/test_graphite_restack.py
git commit -m "feat(graphite): restack via gt no-interactivo + abort defensivo"
```

---

### Task 6: Capability `graphite` + wiring en `app.py`

**Files:**
- Create: `server/ide_server/capabilities/graphite.py`
- Modify: `server/ide_server/app.py` (import + register)
- Test: `server/tests/test_graphite_capability.py`

**Interfaces:**
- Consumes: `graphite.read_stack/build_stack/branch_commits/commit_files/restack`, `workspace.resolve_repo`, `workspace._current_branch`, `sessions_store.load_sessions/find_node`.
- Produces: `register(registry, root)` con:
  - `graphite.stack` `{sessionId?,repoId?}` → `{stack, current}`
  - `graphite.branch` `{sessionId?,repoId?,branch}` → `{commits:[{hash,message,files:[...]}]}`
  - `graphite.restack` `{sessionId?,repoId?,branch}` → `{stack, current}`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_graphite_capability.py
import json, sqlite3, subprocess
from pathlib import Path
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import graphite as graphite_cap


def _seed(tmp_path: Path) -> tuple[Path, str, str]:
    (tmp_path / ".ide").mkdir()
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "a.py").write_text("uno\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "base"], cwd=repo, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "-b", "feat-a"], cwd=repo, check=True)
    (repo / "a.py").write_text("uno\ndos\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "agrega dos"], cwd=repo, check=True)
    tip = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    db = repo / ".git" / ".graphite_metadata.db"
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "branch_metadata" ("branch_name" text primary key, '
                '"parent_branch_name" text, "parent_branch_revision" text, "branch_revision" text)')
    con.executemany('INSERT INTO branch_metadata VALUES (?,?,?,?)',
                    [("main", None, None, base), ("feat-a", "main", base, tip)])
    con.commit(); con.close()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps(
        {"sessions": [{"id": "s1", "name": "S1", "repoId": "repoA", "branch": "feat-a",
                       "worktreePath": str(repo), "children": []}]}))
    return tmp_path, base, tip


@pytest.mark.asyncio
async def test_graphite_stack_for_session(tmp_path):
    root, base, tip = _seed(tmp_path)
    reg = Registry(); graphite_cap.register(reg, root)
    out = await reg.dispatch("graphite.stack", {"sessionId": "s1"})
    names = [b["name"] for b in out["stack"]]
    assert names == ["main", "feat-a"]
    assert out["current"] == "feat-a"
    assert next(b for b in out["stack"] if b["name"] == "feat-a")["current"] is True


@pytest.mark.asyncio
async def test_graphite_branch_commits_and_files(tmp_path):
    root, base, tip = _seed(tmp_path)
    reg = Registry(); graphite_cap.register(reg, root)
    out = await reg.dispatch("graphite.branch", {"sessionId": "s1", "branch": "feat-a"})
    assert out["commits"][0]["message"] == "agrega dos"
    assert any(f["path"] == "a.py" for f in out["commits"][0]["files"])


@pytest.mark.asyncio
async def test_graphite_stack_non_graphite_raises(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps({"sessions": []}))
    (tmp_path / "repoB").mkdir()
    reg = Registry(); graphite_cap.register(reg, root=tmp_path)
    from ide_server.graphite import GraphiteError
    with pytest.raises(GraphiteError):
        await reg.dispatch("graphite.stack", {"repoId": "repoB"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_graphite_capability.py -q`
Expected: FAIL (`ModuleNotFoundError: ...capabilities.graphite`)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/capabilities/graphite.py
from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server import graphite
from ide_server.workspace import resolve_repo, _current_branch
from ide_server.sessions_store import load_sessions, find_node


def register(registry: Registry, root: Path) -> None:
    def _current(repo: Path, payload: dict) -> str:
        if payload.get("sessionId"):
            node = find_node(load_sessions(root), payload["sessionId"])
            if node and node.get("branch"):
                return node["branch"]
        return _current_branch(repo)

    async def stack_(payload: dict) -> dict:
        repo = resolve_repo(root, payload)
        current = _current(repo, payload)
        rows = graphite.read_stack(repo)
        return {"stack": graphite.build_stack(rows, current), "current": current}

    async def branch_(payload: dict) -> dict:
        repo = resolve_repo(root, payload)
        rows = {r["name"]: r for r in graphite.read_stack(repo)}
        row = rows.get(payload["branch"])
        if row is None:
            return {"commits": []}
        commits = graphite.branch_commits(repo, row["revision"], row["parentRevision"])
        for c in commits:
            c["files"] = graphite.commit_files(repo, c["hash"])
        return {"commits": commits}

    async def restack_(payload: dict) -> dict:
        repo = resolve_repo(root, payload)
        graphite.restack(repo, payload["branch"])
        current = _current(repo, payload)
        rows = graphite.read_stack(repo)
        return {"stack": graphite.build_stack(rows, current), "current": current}

    registry.register("graphite.stack", stack_)
    registry.register("graphite.branch", branch_)
    registry.register("graphite.restack", restack_)
```

Wire into `server/ide_server/app.py` — add import with the others:

```python
from ide_server.capabilities import graphite as graphite_cap
```

and register after `changes_cap.register(registry, root)`:

```python
    graphite_cap.register(registry, root)
```

- [ ] **Step 4: Run test to verify it passes** (capability + app arranca)

Run: `cd server && uv run pytest tests/test_graphite_capability.py tests/test_app.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/graphite.py server/ide_server/app.py server/tests/test_graphite_capability.py
git commit -m "feat(graphite): capability stack/branch/restack + wiring en app"
```

---

### Task 7: Transport `graphiteChannel.ts` + `changesChannel.fetchDiff` acepta `sha`

**Files:**
- Create: `ui/src/transport/graphiteChannel.ts`
- Modify: `ui/src/transport/changesChannel.ts`
- Test: `ui/src/transport/graphiteChannel.test.ts`
- Test: `ui/src/transport/changesChannel.test.ts` (append)

**Interfaces:**
- Consumes: `WsClient.request`; reusa `FileChange` de `changesChannel`.
- Produces:
  - `interface StackBranch { name: string; parent: string | null; isTrunk: boolean; current: boolean; needsRestack: boolean; revision: string }`
  - `interface Commit { hash: string; message: string; files: FileChange[] }`
  - `fetchStack(ws, { sessionId?: string | null }): Promise<{ stack: StackBranch[]; current: string }>`
  - `fetchBranch(ws, { sessionId?: string | null; branch: string }): Promise<Commit[]>`
  - `restackBranch(ws, { sessionId?: string | null; branch: string }): Promise<{ stack: StackBranch[]; current: string }>`
  - `changesChannel.fetchDiff` gana un `sha?` opcional en `opts`, incluido en el payload.

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/transport/graphiteChannel.test.ts
import { describe, it, expect, vi } from "vitest";
import { fetchStack, fetchBranch, restackBranch } from "./graphiteChannel";

describe("graphiteChannel", () => {
  it("fetchStack pide graphite.stack y devuelve {stack,current}", async () => {
    const res = { stack: [{ name: "main" }], current: "main" };
    const ws = { request: vi.fn().mockResolvedValue(res) } as any;
    expect(await fetchStack(ws, { sessionId: "s1" })).toBe(res);
    expect(ws.request).toHaveBeenCalledWith("graphite.stack", { sessionId: "s1" });
  });

  it("fetchBranch pide graphite.branch y devuelve commits", async () => {
    const commits = [{ hash: "a", message: "m", files: [] }];
    const ws = { request: vi.fn().mockResolvedValue({ commits }) } as any;
    expect(await fetchBranch(ws, { sessionId: "s1", branch: "feat-a" })).toBe(commits);
    expect(ws.request).toHaveBeenCalledWith("graphite.branch", { sessionId: "s1", branch: "feat-a" });
  });

  it("restackBranch pide graphite.restack y devuelve {stack,current}", async () => {
    const res = { stack: [], current: "main" };
    const ws = { request: vi.fn().mockResolvedValue(res) } as any;
    expect(await restackBranch(ws, { sessionId: "s1", branch: "feat-a" })).toBe(res);
    expect(ws.request).toHaveBeenCalledWith("graphite.restack", { sessionId: "s1", branch: "feat-a" });
  });
});
```

Append to `ui/src/transport/changesChannel.test.ts`:

```typescript
it("fetchDiff incluye sha cuando se pasa", async () => {
  const ws = { request: vi.fn().mockResolvedValue({ lines: [] }) } as any;
  await fetchDiff(ws, { sessionId: "s1", path: "a.py", status: "M", sha: "abc" });
  expect(ws.request).toHaveBeenCalledWith("changes.diff",
    { sessionId: "s1", path: "a.py", status: "M", sha: "abc" });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- graphiteChannel changesChannel`
Expected: FAIL (no existe `./graphiteChannel`)

- [ ] **Step 3: Write minimal implementation**

```typescript
// ui/src/transport/graphiteChannel.ts
import type { WsClient } from "./ws";
import type { FileChange } from "./changesChannel";

export interface StackBranch {
  name: string; parent: string | null; isTrunk: boolean;
  current: boolean; needsRestack: boolean; revision: string;
}
export interface Commit { hash: string; message: string; files: FileChange[] }

export async function fetchStack(
  ws: WsClient, opts: { sessionId?: string | null },
): Promise<{ stack: StackBranch[]; current: string }> {
  return ws.request("graphite.stack", { sessionId: opts.sessionId ?? undefined });
}

export async function fetchBranch(
  ws: WsClient, opts: { sessionId?: string | null; branch: string },
): Promise<Commit[]> {
  return (await ws.request("graphite.branch",
    { sessionId: opts.sessionId ?? undefined, branch: opts.branch })).commits;
}

export async function restackBranch(
  ws: WsClient, opts: { sessionId?: string | null; branch: string },
): Promise<{ stack: StackBranch[]; current: string }> {
  return ws.request("graphite.restack", { sessionId: opts.sessionId ?? undefined, branch: opts.branch });
}
```

Modify `ui/src/transport/changesChannel.ts` `fetchDiff` signature + payload:

```typescript
export async function fetchDiff(
  ws: WsClient, opts: { sessionId?: string | null; path: string; status: string; sha?: string },
): Promise<DiffLine[]> {
  return (await ws.request("changes.diff", {
    sessionId: opts.sessionId ?? undefined, path: opts.path, status: opts.status,
    ...(opts.sha ? { sha: opts.sha } : {}),
  })).lines;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- graphiteChannel changesChannel`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/graphiteChannel.ts ui/src/transport/graphiteChannel.test.ts ui/src/transport/changesChannel.ts ui/src/transport/changesChannel.test.ts
git commit -m "feat(graphite): transport graphiteChannel + fetchDiff acepta sha"
```

---

### Task 8: State `graphite.ts` (store Zustand)

**Files:**
- Create: `ui/src/state/graphite.ts`
- Test: `ui/src/state/graphite.test.ts`

**Interfaces:**
- Consumes: `fetchStack`, `fetchBranch`, `restackBranch` (Task 7), `getWs`, `useSessions` (guard de sesión).
- Produces: `useGraphite` con `{ stack: StackBranch[], current: string | null, commitsByBranch: Record<string, Commit[]>, expandedBranches: string[], expandedCommits: string[], loading: boolean, error: string | null, restacking: string | null, load(sessionId), toggleBranch(sessionId, branch), toggleCommit(hash), restack(sessionId, branch) }`.

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/state/graphite.test.ts
import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchStack = vi.fn();
const fetchBranch = vi.fn();
const restackBranch = vi.fn();
vi.mock("../transport/graphiteChannel", () => ({
  fetchStack: (...a: any[]) => fetchStack(...a),
  fetchBranch: (...a: any[]) => fetchBranch(...a),
  restackBranch: (...a: any[]) => restackBranch(...a),
}));
import { useSessions } from "./sessions";
import { useGraphite } from "./graphite";

beforeEach(() => {
  fetchStack.mockReset(); fetchBranch.mockReset(); restackBranch.mockReset();
  useSessions.setState({ activeSessionId: "s1" } as any);
  useGraphite.setState({
    stack: [], current: null, commitsByBranch: {}, expandedBranches: [],
    expandedCommits: [], loading: false, error: null, restacking: null,
  });
});

describe("state/graphite", () => {
  it("load guarda stack/current y limpia error", async () => {
    fetchStack.mockResolvedValue({ stack: [{ name: "main" }], current: "main" });
    await useGraphite.getState().load("s1");
    expect(useGraphite.getState().stack).toEqual([{ name: "main" }]);
    expect(useGraphite.getState().current).toBe("main");
    expect(useGraphite.getState().error).toBeNull();
  });

  it("load con error limpia stack y setea error", async () => {
    useGraphite.setState({ stack: [{ name: "viejo" } as any] });
    fetchStack.mockRejectedValue({ message: "no es repo Graphite" });
    await useGraphite.getState().load("s1");
    expect(useGraphite.getState().stack).toEqual([]);
    expect(useGraphite.getState().error).toBe("no es repo Graphite");
  });

  it("toggleBranch expande y trae commits una sola vez", async () => {
    fetchBranch.mockResolvedValue([{ hash: "a", message: "m", files: [] }]);
    await useGraphite.getState().toggleBranch("s1", "feat-a");
    expect(useGraphite.getState().expandedBranches).toContain("feat-a");
    expect(useGraphite.getState().commitsByBranch["feat-a"]).toHaveLength(1);
    await useGraphite.getState().toggleBranch("s1", "feat-a");  // colapsa
    expect(useGraphite.getState().expandedBranches).not.toContain("feat-a");
    expect(fetchBranch).toHaveBeenCalledTimes(1);  // no re-fetch
  });

  it("restack actualiza el stack", async () => {
    restackBranch.mockResolvedValue({ stack: [{ name: "main" }], current: "main" });
    await useGraphite.getState().restack("s1", "feat-a");
    expect(useGraphite.getState().stack).toEqual([{ name: "main" }]);
    expect(useGraphite.getState().restacking).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- state/graphite`
Expected: FAIL (no existe `./graphite`)

- [ ] **Step 3: Write minimal implementation**

```typescript
// ui/src/state/graphite.ts
import { create } from "zustand";
import type { StackBranch, Commit } from "../transport/graphiteChannel";
import { fetchStack, fetchBranch, restackBranch } from "../transport/graphiteChannel";
import { getWs } from "../transport/wsClient";
import { useSessions } from "./sessions";

interface GraphiteState {
  stack: StackBranch[];
  current: string | null;
  commitsByBranch: Record<string, Commit[]>;
  expandedBranches: string[];
  expandedCommits: string[];
  loading: boolean;
  error: string | null;
  restacking: string | null;
  load: (sessionId: string | null) => Promise<void>;
  toggleBranch: (sessionId: string | null, branch: string) => Promise<void>;
  toggleCommit: (hash: string) => void;
  restack: (sessionId: string | null, branch: string) => Promise<void>;
}

const stale = (sessionId: string | null) =>
  useSessions.getState().activeSessionId !== sessionId;

export const useGraphite = create<GraphiteState>((set, get) => ({
  stack: [], current: null, commitsByBranch: {}, expandedBranches: [],
  expandedCommits: [], loading: false, error: null, restacking: null,

  load: async (sessionId) => {
    set({ loading: true });
    try {
      const { stack, current } = await fetchStack(getWs(), { sessionId });
      if (stale(sessionId)) return;
      set({ stack, current, commitsByBranch: {}, expandedBranches: [],
            expandedCommits: [], loading: false, error: null });
    } catch (e: unknown) {
      if (stale(sessionId)) return;
      set({ stack: [], current: null, commitsByBranch: {}, loading: false,
            error: (e as { message?: string })?.message ?? "desconectado" });
    }
  },

  toggleBranch: async (sessionId, branch) => {
    const open = get().expandedBranches.includes(branch);
    if (open) {
      set({ expandedBranches: get().expandedBranches.filter((b) => b !== branch) });
      return;
    }
    set({ expandedBranches: [...get().expandedBranches, branch] });
    if (get().commitsByBranch[branch]) return;
    try {
      const commits = await fetchBranch(getWs(), { sessionId, branch });
      if (stale(sessionId)) return;
      set({ commitsByBranch: { ...get().commitsByBranch, [branch]: commits } });
    } catch (e: unknown) {
      if (stale(sessionId)) return;
      set({ error: (e as { message?: string })?.message ?? "desconectado" });
    }
  },

  toggleCommit: (hash) => {
    const open = get().expandedCommits.includes(hash);
    set({ expandedCommits: open
      ? get().expandedCommits.filter((h) => h !== hash)
      : [...get().expandedCommits, hash] });
  },

  restack: async (sessionId, branch) => {
    set({ restacking: branch });
    try {
      const { stack, current } = await restackBranch(getWs(), { sessionId, branch });
      set({ stack, current, restacking: null, error: null });
    } catch (e: unknown) {
      set({ restacking: null, error: (e as { message?: string })?.message ?? "desconectado" });
    }
  },
}));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- state/graphite`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ui/src/state/graphite.ts ui/src/state/graphite.test.ts
git commit -m "feat(graphite): store zustand (load/toggle/restack + guard de sesión)"
```

---

### Task 9: `GraphitePanel` + registro del módulo (rail)

**Files:**
- Create: `ui/src/modules/graphite/GraphitePanel.tsx`
- Create: `ui/src/modules/graphite/register.tsx`
- Create: `ui/src/modules/graphite/GraphitePanel.test.tsx`
- Create: `ui/src/modules/graphite/register.test.ts`
- Modify: `ui/src/modules/stubs.tsx` (quitar `graphite`; quitar `Layers` del import si queda sin uso)
- Modify: `ui/src/App.tsx` (agregar `import "./modules/graphite/register";`)
- Modify: `ui/src/modules/registry.test.ts` (agregar `import "./graphite/register";`)

**Interfaces:**
- Consumes: `useGraphite` (Task 8), `useSessions` (`activeSessionId`), `useStore` (`openTab`).
- Produces: `GraphitePanel` (export nombrado); módulo registrado `id:"graphite"`. Click en archivo abre tab `id:"diff:<sessionId>:@<sha>:<path>"`, `type:"file"`, `label:basename(path)`.

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/modules/graphite/GraphitePanel.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useGraphite } from "../../state/graphite";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const toggleBranch = vi.fn();
const toggleCommit = vi.fn();
const restack = vi.fn();
const load = vi.fn();
import { GraphitePanel } from "./GraphitePanel";

function setGraphite(over: Partial<ReturnType<typeof useGraphite.getState>>) {
  useGraphite.setState({
    stack: [], current: null, commitsByBranch: {}, expandedBranches: [],
    expandedCommits: [], loading: false, error: null, restacking: null,
    load, toggleBranch, toggleCommit, restack, ...over,
  });
}

beforeEach(() => {
  load.mockReset(); toggleBranch.mockReset(); toggleCommit.mockReset(); restack.mockReset();
  useSessions.setState({ activeSessionId: "s1" } as any);
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
  setGraphite({});
});

describe("GraphitePanel", () => {
  it("sin sesión muestra estado neutro y no carga", () => {
    useSessions.setState({ activeSessionId: null } as any);
    setGraphite({});
    render(<GraphitePanel />);
    expect(screen.getByText(/selecciona una sesión/i)).toBeInTheDocument();
    expect(load).not.toHaveBeenCalled();
  });

  it("renderiza el stack y togglea la branch al clickear", () => {
    setGraphite({ stack: [
      { name: "main", parent: null, isTrunk: true, current: false, needsRestack: false, revision: "r0" },
      { name: "feat-a", parent: "main", isTrunk: false, current: true, needsRestack: false, revision: "r1" },
    ], current: "feat-a" });
    render(<GraphitePanel />);
    expect(screen.getByText("main")).toBeInTheDocument();
    fireEvent.click(screen.getByText("feat-a"));
    expect(toggleBranch).toHaveBeenCalledWith("s1", "feat-a");
  });

  it("needsRestack muestra flecha y pide confirmación antes de restackear", () => {
    setGraphite({ stack: [
      { name: "feat-a", parent: "main", isTrunk: false, current: false, needsRestack: true, revision: "r1" },
    ] });
    render(<GraphitePanel />);
    fireEvent.click(screen.getByLabelText("restack feat-a"));
    // aparece confirmación, aún no restackea
    expect(restack).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("sí"));
    expect(restack).toHaveBeenCalledWith("s1", "feat-a");
  });

  it("expande commits→archivos y abre tab de diff al clickear un archivo", () => {
    setGraphite({
      stack: [{ name: "feat-a", parent: "main", isTrunk: false, current: false, needsRestack: false, revision: "r1" }],
      expandedBranches: ["feat-a"],
      commitsByBranch: { "feat-a": [{ hash: "abc123", message: "msg", files: [
        { path: "src/a.py", status: "M", added: 3, removed: 1 }] }] },
      expandedCommits: ["abc123"],
    });
    render(<GraphitePanel />);
    fireEvent.click(screen.getByText("src/a.py"));
    const tab = useStore.getState().openTabs[0];
    expect(tab).toMatchObject({ id: "diff:s1:@abc123:src/a.py", type: "file", label: "a.py" });
  });

  it("muestra 'desconectado' en error", () => {
    setGraphite({ error: "no es repo Graphite" });
    render(<GraphitePanel />);
    expect(screen.getByText(/desconectado/i)).toBeInTheDocument();
  });
});
```

```typescript
// ui/src/modules/graphite/register.test.ts
import { describe, it, expect } from "vitest";
import "../stubs";
import "./register";
import { getModules } from "../registry";
import { GraphitePanel } from "./GraphitePanel";

describe("registro graphite", () => {
  it("usa el GraphitePanel real (no el stub)", () => {
    expect(getModules().find((m) => m.id === "graphite")?.Panel).toBe(GraphitePanel);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- graphite`
Expected: FAIL (no existe `./GraphitePanel`)

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/modules/graphite/GraphitePanel.tsx
import { useEffect, useState } from "react";
import { RefreshCw, CornerRightDown } from "lucide-react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";
import { useGraphite } from "../../state/graphite";

const basename = (p: string) => p.split("/").pop() || p;

export function GraphitePanel() {
  const activeSessionId = useSessions((s) => s.activeSessionId);
  const openTab = useStore((s) => s.openTab);
  const {
    stack, error, commitsByBranch, expandedBranches, expandedCommits,
    load, toggleBranch, toggleCommit, restack,
  } = useGraphite();
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    if (activeSessionId === null) return;
    load(activeSessionId);
    // sin polling: fetch al montar y al cambiar de sesión
  }, [activeSessionId, load]);

  if (activeSessionId === null) {
    return <div className="p-3 text-xs text-muted-foreground">selecciona una sesión</div>;
  }

  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Stack de branches
        </div>
        <button aria-label="refrescar" onClick={() => load(activeSessionId)}
          className="text-muted-foreground hover:text-foreground">
          <RefreshCw size={13} />
        </button>
      </div>
      {error && <div className="px-1 py-2 text-xs text-destructive">desconectado — {error}</div>}
      {!error && stack.map((b) => (
        <div key={b.name} className="mb-0.5">
          <div className="flex items-center gap-2 rounded px-1.5 py-1.5 hover:bg-accent">
            <span className="h-3 w-3 shrink-0 rounded-full border-2"
              style={{ borderColor: b.current ? "#e0863f" : b.needsRestack ? "#bd925f" : "#4a463d",
                       background: "#161513" }} />
            <button onClick={() => toggleBranch(activeSessionId, b.name)}
              className="min-w-0 flex-1 truncate text-left font-mono text-[11.5px]"
              style={{ color: b.current ? "#f0ece4" : "#cfc9bd" }}>
              {b.name}
            </button>
            {b.current && (
              <span className="shrink-0 text-[9px] font-semibold uppercase tracking-wide text-[#e0863f]">actual</span>
            )}
            {b.needsRestack && confirming !== b.name && (
              <button aria-label={`restack ${b.name}`} onClick={() => setConfirming(b.name)}
                className="shrink-0 text-[#bd925f] hover:text-[#e0863f]">
                <CornerRightDown size={13} />
              </button>
            )}
            {confirming === b.name && (
              <span className="flex shrink-0 items-center gap-1.5 text-[10px]">
                <span className="text-muted-foreground">restackear?</span>
                <button className="text-[#7fb069]"
                  onClick={() => { setConfirming(null); restack(activeSessionId, b.name); }}>sí</button>
                <button className="text-muted-foreground" onClick={() => setConfirming(null)}>no</button>
              </span>
            )}
          </div>
          {expandedBranches.includes(b.name) && (
            <div className="ml-[9px] pl-3.5"
              style={{ borderLeft: b.needsRestack ? "1px dashed #4a463d" : "1px solid #332f28" }}>
              {(commitsByBranch[b.name] ?? []).map((c) => (
                <div key={c.hash} className="my-0.5">
                  <button onClick={() => toggleCommit(c.hash)}
                    className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-accent">
                    <span className="shrink-0 font-mono text-[10.5px] text-[#e0863f]">{c.hash}</span>
                    <span className="min-w-0 flex-1 truncate text-[11px] text-[#cfc9bd]">{c.message}</span>
                  </button>
                  {expandedCommits.includes(c.hash) && (
                    <div className="pb-1 pl-4">
                      {c.files.map((f) => (
                        <button key={f.path}
                          onClick={() => openTab({
                            id: `diff:${activeSessionId ?? ""}:@${c.hash}:${f.path}`,
                            type: "file", label: basename(f.path),
                          })}
                          className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent">
                          <span className="min-w-0 flex-1 truncate text-left font-mono text-[10.5px] text-[#9c9488]">{f.path}</span>
                          <span className="font-mono text-[9.5px] text-[#7fb069]">+{f.added ?? 0}</span>
                          <span className="font-mono text-[9.5px] text-[#c96a4e]">-{f.removed ?? 0}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

```tsx
// ui/src/modules/graphite/register.tsx
import { Layers } from "lucide-react";
import { registerModule } from "../registry";
import { GraphitePanel } from "./GraphitePanel";

registerModule({ id: "graphite", title: "Graphite", icon: Layers, Panel: GraphitePanel });
```

Edit `ui/src/modules/stubs.tsx` — remove the `graphite` registration line and drop `Layers` from the import (Search/Tasks/Notion use `Search`/`ListChecks`/`BookOpen`, so `Layers` becomes unused):

```tsx
import { Search, ListChecks, BookOpen } from "lucide-react";
// ...
// (borrar la línea de registerModule del id "graphite")
```

Edit `ui/src/App.tsx` — add the register import next to the others:

```tsx
import "./modules/graphite/register";
```

Edit `ui/src/modules/registry.test.ts` — add the import so the "graphite" id is populated by the real module (mirror the existing `import "./changes/register";`):

```tsx
import "./graphite/register";
```

- [ ] **Step 4: Run test to verify it passes** (graphite + tsc + suite completa)

Run: `cd ui && npm test -- graphite && cd ui && npx tsc --noEmit && npm test`
Expected: PASS (GraphitePanel + register verdes; tsc limpio; suite completa verde)

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/graphite ui/src/modules/stubs.tsx ui/src/App.tsx ui/src/modules/registry.test.ts
git commit -m "feat(graphite): GraphitePanel en el rail (stack inline + restack con confirmación)"
```

---

### Task 10: `DiffTab` extendido para diff de commit (`@sha`)

**Files:**
- Modify: `ui/src/main/DiffTab.tsx`
- Test: `ui/src/main/DiffTab.test.tsx` (append)

**Interfaces:**
- Consumes: `fetchDiff` con `sha?` (Task 7). Recibe `id:"diff:<sessionId>:@<sha>:<path>"` para diffs de commit, o el `diff:<sessionId>:<status>:<path>` de R4.
- Produces: `DiffTab` detecta el slot de status con prefijo `@` → es un diff de commit; llama `fetchDiff` con `sha`.

- [ ] **Step 1: Write the failing test** (append a `ui/src/main/DiffTab.test.tsx`)

```typescript
it("con id @sha pide el diff del commit (fetchDiff con sha)", async () => {
  fetchDiff.mockResolvedValue([{ type: "add", text: "dos" }]);
  render(<DiffTab id="diff:s1:@abc123:src/a.py" />);
  await waitFor(() => screen.getByText("dos"));
  expect(fetchDiff).toHaveBeenCalledWith({ sessionId: "s1", path: "src/a.py", status: "", sha: "abc123" });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- DiffTab`
Expected: FAIL (fetchDiff se llama sin `sha`, la aserción no matchea)

- [ ] **Step 3: Write minimal implementation** — modify `ui/src/main/DiffTab.tsx` `parseId` + fetch

Update `parseId` to also return `sha` (when the status slot starts with `@`) and strip it from status:

```tsx
function parseId(id: string): { sessionId: string | null; status: string; sha?: string; path: string } {
  const rest = id.slice("diff:".length);
  const i1 = rest.indexOf(":");
  const i2 = rest.indexOf(":", i1 + 1);
  const slot = rest.slice(i1 + 1, i2);
  const isCommit = slot.startsWith("@");
  return {
    sessionId: rest.slice(0, i1) || null,
    status: isCommit ? "" : slot,
    sha: isCommit ? slot.slice(1) : undefined,
    path: rest.slice(i2 + 1),
  };
}
```

Update the component to pass `sha`:

```tsx
  const { sessionId, status, sha, path } = parseId(id);
  // ...
        const ls = await fetchDiff(getWs(), { sessionId, path, status, sha });
```

(`fetchDiff` ignora `sha` cuando es `undefined` — comportamiento R4 intacto.)

- [ ] **Step 4: Run test to verify it passes** (DiffTab + tsc + build + suite)

Run: `cd ui && npm test -- DiffTab && cd ui && npx tsc --noEmit && npm run build && npm test`
Expected: PASS; tsc limpio; build ok; suite completa verde

- [ ] **Step 5: Commit**

```bash
git add ui/src/main/DiffTab.tsx ui/src/main/DiffTab.test.tsx
git commit -m "feat(graphite): DiffTab muestra el diff de un archivo por commit (@sha)"
```

---

## Verificación final (post Task 10)

- [ ] Backend completo: `cd server && uv run pytest -q` → todo verde (110 previos + nuevos).
- [ ] Frontend completo: `cd ui && npm test` → verde; `npx tsc --noEmit` limpio; `npm run build` ok.
- [ ] E2E manual (opcional): levantar backend con un workspace cuyo repo esté trackeado por gt + `npm run dev`; seleccionar una sesión; abrir el rail "Graphite"; ver el stack, expandir branch→commits→archivos, abrir un diff; en una branch desactualizada ver el conector punteado + flecha, confirmar restack.
- [ ] Actualizar `docs/superpowers/HANDOFF.md`: R5a cerrado; R5b (checkout/submit) como próximo.

## Self-Review (notas del plan)

- **Cobertura del spec:** diff de commit (T1, T10), build_stack+needsRestack (T2), read_stack sqlite + commits/files (T3), resolve_repo (T4), restack+abort (T5), capability (T6), transport (T7), store con guard (T8), panel inline + restack confirm + file→tab (T9). Fuera de alcance (checkout, submit) no se implementa.
- **Reuso R4:** `parse_numstat`/`parse_diff`/`_git` (backend), `DiffTab`/`MainPanel`/`FileChange` (frontend) — sin duplicar.
- **Tab id de commit:** `diff:<sessionId>:@<sha>:<path>`; el prefijo `@` en el slot de status distingue commit-diff de working-tree-diff sin romper R4 (path va último, tolera `:`).
- **Sin fallos silenciosos:** `GraphiteError`/`GitError` suben por `bus.py` como `handler_error`; store limpia estado y setea `error`; restack hace `rebase --abort` defensivo.
- **Tipos consistentes entre tareas:** `StackBranch`, `Commit`, `FileChange` (reusado), `resolve_repo`, id `@sha`.
