# Módulo Archivos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps
> usan checkbox (`- [ ]`).

**Goal:** Módulo del rail "Archivos": árbol navegable (lazy, muestra todo) del worktree de la sesión
activa; click en archivo lo abre en vim/`$EDITOR` en un tab de terminal.

**Architecture:** Backend `capabilities/files.py` (`files.list` + `files.open` que delega en
`terminal.open`). Frontend `transport/filesChannel.ts` + `PanelId "files"` + `modules/files/FilesPanel.tsx`
(árbol recursivo) + `register.tsx` + import en `App.tsx`. Reusa el tab de terminal existente.

**Tech Stack:** Python/FastAPI (`pathlib`, `shlex`), React/TS/vitest/zustand, shadcn/Tailwind, lucide.

## Global Constraints

- **Sin fallos silenciosos:** path fuera de la raíz / no-dir → `ValueError` (envelope). `_safe_join` usa
  `.resolve()` y verifica que el destino sea `root` o descendiente (bloquea `..` y symlinks).
- **Reusa `terminal.open`:** `files.open` NO spawnea PTY propio; hace `registry.dispatch("terminal.open", …)`.
- **Muestra todo** en el árbol (sin ocultar `.git`/dotfiles/node_modules).
- **Raíz = `resolve_cwd(root, {sessionId})`** (worktree de la sesión activa).
- **Fidelidad 1a:** panel con el idiom de los otros (`aside w-64`, filas `text-xs hover:bg-accent`),
  íconos lucide. Sin hex arbitrario.
- **Commits atómicos, en español.** Un commit por tarea. Se trabaja en `main` directo. NO tocar `mlx/*.py`.

---

### Task 1: `capabilities/files.py` + wire `app.py`

**Files:**
- Create: `server/ide_server/capabilities/files.py`
- Modify: `server/ide_server/app.py`
- Test: `server/tests/test_files.py`

**Interfaces:**
- Produces: `register(registry, root)` con `files.list {sessionId, path}` → `{entries}` y
  `files.open {sessionId, path}` (delega en `terminal.open`). `_safe_join(root, rel) -> Path`.

- [ ] **Step 1: Tests que fallan** — `server/tests/test_files.py`:

```python
import pytest
from ide_server.plugins import Registry
import ide_server.capabilities.files as files_cap
from ide_server.capabilities.files import _safe_join


def test_safe_join_ok_and_escape(tmp_path):
    assert _safe_join(tmp_path, "a/b") == (tmp_path.resolve() / "a" / "b")
    assert _safe_join(tmp_path, "") == tmp_path.resolve()
    with pytest.raises(ValueError):
        _safe_join(tmp_path, "../escape")


@pytest.mark.asyncio
async def test_list_dirs_first_then_files(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir(); (tmp_path / "a.txt").write_text("x")
    (tmp_path / "src" / "b.py").write_text("y")
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    reg = Registry(); files_cap.register(reg, tmp_path)
    out = await reg.dispatch("files.list", {"sessionId": "s", "path": ""})
    pairs = [(e["name"], e["type"]) for e in out["entries"]]
    assert ("src", "dir") in pairs and ("a.txt", "file") in pairs
    assert pairs[0][1] == "dir"                       # dirs primero


@pytest.mark.asyncio
async def test_list_subdir(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "b.py").write_text("y")
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    reg = Registry(); files_cap.register(reg, tmp_path)
    out = await reg.dispatch("files.list", {"sessionId": "s", "path": "src"})
    assert [e["name"] for e in out["entries"]] == ["b.py"]


@pytest.mark.asyncio
async def test_list_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    reg = Registry(); files_cap.register(reg, tmp_path)
    with pytest.raises(ValueError):
        await reg.dispatch("files.list", {"sessionId": "s", "path": "../.."})


@pytest.mark.asyncio
async def test_open_delegates_to_terminal(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("x")
    monkeypatch.setattr(files_cap, "resolve_cwd", lambda root, payload: tmp_path)
    monkeypatch.setenv("EDITOR", "vim")
    reg = Registry(); files_cap.register(reg, tmp_path)
    captured = {}
    async def fake_term(payload): captured.update(payload); return {"id": "t1", "cwd": str(tmp_path)}
    reg.register("terminal.open", fake_term)
    out = await reg.dispatch("files.open", {"sessionId": "s", "path": "a.txt"})
    assert out == {"id": "t1", "cwd": str(tmp_path)}
    assert captured["cmd"] == ["vim", str((tmp_path.resolve() / "a.txt"))]
    assert captured["sessionId"] == "s"
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar** — `server/ide_server/capabilities/files.py`:

```python
from __future__ import annotations
import os
import shlex
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.workspace import resolve_cwd


def _safe_join(root: Path, rel: str) -> Path:
    root = root.resolve()
    target = (root / (rel or "")).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path fuera de la raíz")
    return target


def register(registry: Registry, root: Path) -> None:
    async def list_(payload: dict) -> dict:
        base = resolve_cwd(root, payload)
        target = _safe_join(base, payload.get("path") or "")
        if not target.is_dir():
            raise ValueError(f"no es un directorio: {payload.get('path')!r}")
        entries = [
            {"name": p.name, "type": "dir" if p.is_dir() else "file"}
            for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        ]
        return {"entries": entries}

    async def open_(payload: dict) -> dict:
        base = resolve_cwd(root, payload)
        target = _safe_join(base, payload.get("path") or "")
        editor = shlex.split(os.environ.get("EDITOR") or "vim")
        return await registry.dispatch(
            "terminal.open",
            {"sessionId": payload.get("sessionId"), "cmd": editor + [str(target)]},
        )

    registry.register("files.list", list_)
    registry.register("files.open", open_)
```

En `server/ide_server/app.py`: agregar `from ide_server.capabilities import files as files_cap` con las
otras capabilities, y dentro de `create_app` (junto a los otros `*_cap.register`):

```python
    files_cap.register(registry, root)
```

- [ ] **Step 4: Correr, verificar que pasan** → PASS. Suite completa (incl. `create_app`) → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/files.py server/ide_server/app.py server/tests/test_files.py
git commit -m "feat(files): capability files.list + files.open (delega en terminal.open) + wire"
```

---

### Task 2: Frontend — transport + `PanelId`

**Files:**
- Create: `ui/src/transport/filesChannel.ts`
- Modify: `ui/src/state/store.ts`
- Test: `ui/src/transport/filesChannel.test.ts`

**Interfaces:**
- Produces: `FileEntry {name, type}`; `listFiles(ws, sessionId, path)`; `openFile(ws, sessionId, path)`.
  `PanelId` gana `"files"`.

- [ ] **Step 1: Test que falla** — `ui/src/transport/filesChannel.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { listFiles, openFile } from "./filesChannel";

describe("filesChannel", () => {
  it("listFiles pega a files.list con sessionId y path", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ entries: [] }) } as any;
    await listFiles(ws, "s1", "src");
    expect(ws.request).toHaveBeenCalledWith("files.list", { sessionId: "s1", path: "src" });
  });
  it("openFile pega a files.open", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ id: "t1", cwd: "/x" }) } as any;
    const r = await openFile(ws, "s1", "a.txt");
    expect(ws.request).toHaveBeenCalledWith("files.open", { sessionId: "s1", path: "a.txt" });
    expect(r.id).toBe("t1");
  });
});
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL.

- [ ] **Step 3: Implementar** — `ui/src/transport/filesChannel.ts`:

```ts
import type { WsClient } from "./ws";

export interface FileEntry { name: string; type: "dir" | "file"; }

export function listFiles(ws: WsClient, sessionId: string, path: string): Promise<{ entries: FileEntry[] }> {
  return ws.request("files.list", { sessionId, path });
}
export function openFile(ws: WsClient, sessionId: string, path: string): Promise<{ id: string; cwd: string }> {
  return ws.request("files.open", { sessionId, path });
}
```

En `ui/src/state/store.ts`: agregar `"files"` al union `PanelId`. Cambiar:
```ts
export type PanelId = "search" | "changes" | "graphite" | "tasks" | "terminal" | "notion";
```
por:
```ts
export type PanelId = "search" | "changes" | "graphite" | "tasks" | "terminal" | "notion" | "files";
```

- [ ] **Step 4: Correr, verificar que pasa**

Run: `cd ui && npm test -- filesChannel` → PASS. `cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/filesChannel.ts ui/src/state/store.ts ui/src/transport/filesChannel.test.ts
git commit -m "feat(files): transport listFiles/openFile + PanelId files"
```

---

### Task 3: Frontend — `FilesPanel` + registro del módulo

**Files:**
- Create: `ui/src/modules/files/FilesPanel.tsx`, `ui/src/modules/files/register.tsx`,
  `ui/src/modules/files/FilesPanel.test.tsx`
- Modify: `ui/src/App.tsx`

**Interfaces:**
- Consumes: `listFiles`/`openFile` (T2), `useSessions.activeSessionId`, `useStore.openTab`.

- [ ] **Step 1: Test que falla** — `ui/src/modules/files/FilesPanel.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const listFiles = vi.fn();
const openFile = vi.fn().mockResolvedValue({ id: "t1", cwd: "/x" });
vi.mock("../../transport/filesChannel", () => ({
  listFiles: (...a: any[]) => listFiles(...a),
  openFile: (...a: any[]) => openFile(...a),
}));
import { FilesPanel } from "./FilesPanel";

beforeEach(() => {
  listFiles.mockReset().mockResolvedValue({ entries: [
    { name: "src", type: "dir" }, { name: "a.txt", type: "file" }] });
  openFile.mockClear();
  useSessions.setState({ activeSessionId: "s1" } as any);
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
});

describe("FilesPanel", () => {
  it("lista la raíz de la sesión activa", async () => {
    render(<FilesPanel />);
    await waitFor(() => expect(screen.getByText("src")).toBeInTheDocument());
    expect(screen.getByText("a.txt")).toBeInTheDocument();
  });
  it("click en carpeta pide sus hijos", async () => {
    render(<FilesPanel />);
    await waitFor(() => screen.getByText("src"));
    listFiles.mockResolvedValueOnce({ entries: [{ name: "b.py", type: "file" }] });
    fireEvent.click(screen.getByText("src"));
    await waitFor(() => expect(screen.getByText("b.py")).toBeInTheDocument());
    expect(listFiles).toHaveBeenCalledWith({}, "s1", "src");
  });
  it("click en archivo lo abre en un tab de terminal", async () => {
    render(<FilesPanel />);
    await waitFor(() => screen.getByText("a.txt"));
    fireEvent.click(screen.getByText("a.txt"));
    expect(openFile).toHaveBeenCalledWith({}, "s1", "a.txt");
    await waitFor(() => expect(useStore.getState().openTabs.some((t) => t.id === "t1")).toBe(true));
  });
  it("sin sesión muestra un mensaje", () => {
    useSessions.setState({ activeSessionId: null } as any);
    render(<FilesPanel />);
    expect(screen.getByText(/Seleccioná una sesión/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL.

- [ ] **Step 3: Implementar**

`ui/src/modules/files/FilesPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Folder, File as FileIcon } from "lucide-react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";
import { listFiles, openFile, type FileEntry } from "../../transport/filesChannel";
import { getWs } from "../../transport/wsClient";

const join = (base: string, name: string) => (base ? `${base}/${name}` : name);

function TreeNode({ sessionId, path, entry, depth }:
  { sessionId: string; path: string; entry: FileEntry; depth: number }) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<FileEntry[] | null>(null);
  const openTab = useStore((s) => s.openTab);
  const full = join(path, entry.name);
  const onClick = () => {
    if (entry.type === "file") {
      openFile(getWs(), sessionId, full)
        .then(({ id }) => openTab({ id, type: "terminal", label: entry.name }))
        .catch(() => {});
      return;
    }
    const next = !open;
    setOpen(next);
    if (next && children === null)
      listFiles(getWs(), sessionId, full).then((r) => setChildren(r.entries)).catch(() => setChildren([]));
  };
  return (
    <div>
      <button data-file-node={full} onClick={onClick} style={{ paddingLeft: depth * 12 + 10 }}
        className="flex w-full items-center gap-1.5 py-0.5 text-xs text-foreground hover:bg-accent">
        {entry.type === "dir" ? <Folder size={12} className="text-muted-foreground" />
          : <FileIcon size={12} className="text-muted-foreground" />}
        <span>{entry.name}</span>
      </button>
      {open && children && children.map((c) => (
        <TreeNode key={c.name} sessionId={sessionId} path={full} entry={c} depth={depth + 1} />
      ))}
    </div>
  );
}

export function FilesPanel() {
  const sessionId = useSessions((s) => s.activeSessionId);
  const [roots, setRoots] = useState<FileEntry[] | null>(null);
  useEffect(() => {
    if (!sessionId) { setRoots(null); return; }
    listFiles(getWs(), sessionId, "").then((r) => setRoots(r.entries)).catch(() => setRoots([]));
  }, [sessionId]);
  return (
    <aside className="w-64 overflow-auto border-r border-border bg-card">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Archivos</div>
      {!sessionId ? (
        <div className="mx-2.5 text-[11px] text-muted-foreground">Seleccioná una sesión para ver sus archivos.</div>
      ) : (
        <div className="flex flex-col">
          {roots?.map((e) => <TreeNode key={e.name} sessionId={sessionId} path="" entry={e} depth={0} />)}
        </div>
      )}
    </aside>
  );
}
```

`ui/src/modules/files/register.tsx`:

```tsx
import { FolderTree } from "lucide-react";
import { registerModule } from "../registry";
import { FilesPanel } from "./FilesPanel";

registerModule({ id: "files", title: "Files", icon: FolderTree, Panel: FilesPanel });
```

En `ui/src/App.tsx`: agregar el import junto a los otros módulos (después de la línea de tasks):

```ts
import "./modules/files/register";
```

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd ui && npm test -- FilesPanel filesChannel` → PASS. Suite completa `cd ui && npm test` → PASS.
`cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/files/FilesPanel.tsx ui/src/modules/files/register.tsx ui/src/modules/files/FilesPanel.test.tsx ui/src/App.tsx
git commit -m "feat(files): módulo Archivos en el rail (árbol lazy, abre en vim)"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** `files.list`+`files.open` con seguridad de path y delegación a terminal (T1),
  transport + PanelId (T2), panel árbol recursivo lazy + registro del módulo (T3). ✓
- **Consistencia:** `files.open` → `{id, cwd}` (T1) ↔ `openFile` (T2) ↔ `openTab({id, type:"terminal"})`
  (T3). `FileEntry {name, type}` (T2) ↔ `files.list` (T1) ↔ `TreeNode` (T3).
- **Sin fallos silenciosos:** `_safe_join` bloquea escapes → `ValueError` → envelope; `files.open` reusa
  `terminal.open` (su error propaga). En el front, `listFiles` que falla → `[]` (nodo vacío, no rompe).
- **Riesgo señalado:** `resolve_cwd` con `sessionId` inválido lanza `KeyError` (el bus lo mapea a
  "unknown_channel") — pero el front siempre pasa la sesión activa válida; consistente con `terminal.open`.
  El test de `files.open` compara contra `str(tmp_path.resolve() / "a.txt")` para evitar symlinks de macOS.
- **Verificación en vivo (fuera del plan):** abrir el módulo, navegar el árbol, clickear un archivo → vim
  en el tab de terminal.
```
