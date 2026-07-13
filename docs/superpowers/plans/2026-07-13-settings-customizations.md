# Settings / Customizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Footer de 9 items de Customizations al pie del sidebar de sesiones + modal de Settings (read-only) que muestra el catálogo **global** de customizations de Claude Code, marcando lo que está en uso en el workspace actual.

**Architecture:** El backend expone `customizations.list` que lee fuentes globales (`~/.claude/*`, `~/.ide/config.toml`, PRESETS de roles) vía lectores puros e inyectables (`home: Path`), y devuelve 9 items normalizados con filas `{label, inUse}`. El frontend (shadcn/1a) renderiza el footer y un modal (nav izq + panel derecho) con badge "en uso".

**Tech Stack:** Python 3.12 / FastAPI / `tomllib` (stdlib) / pytest (backend); React 19 + Vite + TS + Tailwind/shadcn + Zustand + vitest/RTL (frontend).

## Global Constraints

- **Scope global (nivel usuario).** Se lee `Path.home()` — pero los lectores reciben `home: Path` por parámetro (default `Path.home()` en la capability) para testear con `tmp_path` sin tocar el `~/.claude` real.
- **Read-only.** Nada escribe. Ningún secreto de MCP se expone (solo nombres de servidores).
- **Tolerante a ausencia/corrupción.** Un archivo/dir inexistente o corrupto → lista vacía para ese item, nunca una excepción que tumbe el resto.
- **Sin fallos silenciosos** (a nivel transport): si `customizations.list` falla, el envelope `error` viaja; el footer no muestra datos viejos como vivos.
- **Identidad 1a vía shadcn.** Tests asertan comportamiento/roles/texto, no estilos computados.
- **TDD.** Test que falla → implementación mínima → test que pasa → commit. Un commit por tarea.
- **Orden de los 9 items** (footer y nav): `overview, roles, agents, skills, instructions, hooks, mcp, plugins, tools`.
- **Set de tools built-in** (lista estática, verbatim): `["bash","read","write","edit","grep","glob","webSearch","webFetch","task","todoWrite","notebookEdit","multiEdit"]`.

---

## Task 1: Lector de roles (roster global + in-use del workspace)

**Files:**
- Create: `server/ide_server/customizations/__init__.py`, `server/ide_server/customizations/readers.py`
- Test: `server/tests/test_customizations_roles.py`

**Interfaces:**
- Consumes: `ide_server.roles.PRESETS`, `ide_server.sessions_store.load_sessions`.
- Produces: `read_roles(home: Path, workspace_root: Path) -> list[dict]` (filas `{"label": str, "inUse": bool}`); helper `roles_in_use(workspace_root: Path) -> set[str]`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_customizations_roles.py
from pathlib import Path
from ide_server.customizations.readers import read_roles, roles_in_use

def _seed_sessions(root: Path, roles: list[str | None]):
    import json
    (root / ".ide").mkdir(parents=True, exist_ok=True)
    tree = [{"id": f"s{i}", "name": f"s{i}", "role": r, "children": []}
            for i, r in enumerate(roles)]
    (root / ".ide" / "sessions.json").write_text(json.dumps(tree))

def test_roles_in_use_reads_workspace_sessions(tmp_path):
    _seed_sessions(tmp_path, ["lector", "arquitecto", None])
    assert roles_in_use(tmp_path) == {"lector", "arquitecto"}

def test_read_roles_includes_presets_and_marks_in_use(tmp_path):
    _seed_sessions(tmp_path, ["arquitecto"])
    home = tmp_path / "home"           # sin ~/.ide/config.toml global
    rows = read_roles(home, tmp_path)
    labels = {r["label"] for r in rows}
    assert {"lector", "revisor", "arquitecto", "disenador"} <= labels   # PRESETS
    by = {r["label"]: r["inUse"] for r in rows}
    assert by["arquitecto"] is True and by["lector"] is False

def test_read_roles_merges_global_ide_config(tmp_path):
    _seed_sessions(tmp_path, [])
    home = tmp_path / "home"; (home / ".ide").mkdir(parents=True)
    (home / ".ide" / "config.toml").write_text('[roles.mirole]\nmodel = "haiku"\n')
    labels = {r["label"] for r in read_roles(home, tmp_path)}
    assert "mirole" in labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_customizations_roles.py -q`
Expected: FAIL (`ModuleNotFoundError: ide_server.customizations`). (Env ya tiene el extra dev; NO correr `uv sync`.)

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/customizations/__init__.py
```
```python
# server/ide_server/customizations/readers.py
from __future__ import annotations
import json, tomllib
from pathlib import Path

def roles_in_use(workspace_root: Path) -> set[str]:
    from ide_server.sessions_store import load_sessions
    used: set[str] = set()
    def walk(nodes: list[dict]) -> None:
        for n in nodes:
            if n.get("role"):
                used.add(n["role"])
            walk(n.get("children") or [])
    try:
        walk(load_sessions(workspace_root))
    except Exception:
        pass
    return used

def read_roles(home: Path, workspace_root: Path) -> list[dict]:
    from ide_server.roles import PRESETS
    names: list[str] = list(PRESETS.keys())
    global_cfg = home / ".ide" / "config.toml"
    if global_cfg.exists():
        try:
            data = tomllib.loads(global_cfg.read_text())
            for name in (data.get("roles") or {}):
                if name not in names:
                    names.append(name)
        except Exception:
            pass
    used = roles_in_use(workspace_root)
    return [{"label": n, "inUse": n in used} for n in names]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_customizations_roles.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/customizations/__init__.py server/ide_server/customizations/readers.py server/tests/test_customizations_roles.py
git commit -m "feat(server): lector de roles del catálogo (PRESETS + ~/.ide global + in-use)"
```

---

## Task 2: Lectores basados en `~/.claude` (mcp, instructions, hooks, skills, agents, plugins)

**Files:**
- Modify: `server/ide_server/customizations/readers.py`
- Test: `server/tests/test_customizations_claude.py`

**Interfaces:**
- Produces: `read_mcp(home)`, `read_instructions(home)`, `read_hooks(home)`, `read_skills(home)`, `read_agents(home)`, `read_plugins(home)` → cada uno `list[dict]` (`{"label", "inUse": False}`), tolerante a ausencia/corrupción.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_customizations_claude.py
from pathlib import Path
from ide_server.customizations.readers import (
    read_mcp, read_instructions, read_hooks, read_skills, read_agents, read_plugins,
)

def test_absent_sources_return_empty(tmp_path):
    for fn in (read_mcp, read_instructions, read_hooks, read_skills, read_agents, read_plugins):
        assert fn(tmp_path) == []

def test_read_mcp_lists_server_names(tmp_path):
    (tmp_path / ".claude.json").write_text('{"mcpServers": {"github": {}, "linear": {}}}')
    assert {r["label"] for r in read_mcp(tmp_path)} == {"github", "linear"}

def test_read_hooks_lists_keys(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": [], "Stop": []}}')
    assert {r["label"] for r in read_hooks(tmp_path)} == {"PreToolUse", "Stop"}

def test_read_skills_and_agents_and_plugins_list_dir_entries(tmp_path):
    c = tmp_path / ".claude"
    (c / "skills" / "make-deck").mkdir(parents=True)
    (c / "agents").mkdir(parents=True); (c / "agents" / "reviewer.md").write_text("x")
    (c / "plugins" / "superpowers").mkdir(parents=True)
    assert [r["label"] for r in read_skills(tmp_path)] == ["make-deck"]
    assert [r["label"] for r in read_agents(tmp_path)] == ["reviewer"]
    assert [r["label"] for r in read_plugins(tmp_path)] == ["superpowers"]

def test_read_instructions_presence(tmp_path):
    assert read_instructions(tmp_path) == []
    (tmp_path / ".claude").mkdir(); (tmp_path / ".claude" / "CLAUDE.md").write_text("reglas")
    assert [r["label"] for r in read_instructions(tmp_path)] == ["CLAUDE.md"]

def test_corrupt_json_degrades_to_empty(tmp_path):
    (tmp_path / ".claude.json").write_text("{not json")
    assert read_mcp(tmp_path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_customizations_claude.py -q`
Expected: FAIL (funciones no definidas).

- [ ] **Step 3: Write minimal implementation**

Agregar a `server/ide_server/customizations/readers.py`:

```python
def _rows(labels) -> list[dict]:
    return [{"label": str(l), "inUse": False} for l in labels]

def _json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def read_mcp(home: Path) -> list[dict]:
    return _rows((_json(home / ".claude.json").get("mcpServers") or {}).keys())

def read_hooks(home: Path) -> list[dict]:
    return _rows((_json(home / ".claude" / "settings.json").get("hooks") or {}).keys())

def read_instructions(home: Path) -> list[dict]:
    p = home / ".claude" / "CLAUDE.md"
    return _rows(["CLAUDE.md"]) if p.exists() and p.read_text().strip() else []

def _dir_entries(d: Path, *, files: bool) -> list[str]:
    if not d.is_dir():
        return []
    out = []
    for entry in sorted(d.iterdir()):
        if files and entry.is_file():
            out.append(entry.stem)
        elif not files and entry.is_dir():
            out.append(entry.name)
    return out

def read_skills(home: Path) -> list[dict]:
    return _rows(_dir_entries(home / ".claude" / "skills", files=False))

def read_agents(home: Path) -> list[dict]:
    return _rows(_dir_entries(home / ".claude" / "agents", files=True))

def read_plugins(home: Path) -> list[dict]:
    return _rows(_dir_entries(home / ".claude" / "plugins", files=False))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_customizations_claude.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/customizations/readers.py server/tests/test_customizations_claude.py
git commit -m "feat(server): lectores de mcp/instructions/hooks/skills/agents/plugins (~/.claude)"
```

---

## Task 3: Tools (lista estática + in-use por roles) y armado de items

**Files:**
- Modify: `server/ide_server/customizations/readers.py`
- Create: `server/ide_server/customizations/items.py`
- Test: `server/tests/test_customizations_items.py`

**Interfaces:**
- Consumes: todos los lectores; `ide_server.roles.resolve_role`.
- Produces: `read_tools(used_tools: set[str]) -> list[dict]` (marca inUse los del set); `build_items(home: Path, workspace_root: Path) -> list[dict]` — arma los 9 items `{key, title, description, count, rows}` en el orden del constraint. `TOOLS` constante.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_customizations_items.py
from pathlib import Path
import json
from ide_server.customizations.readers import read_tools, TOOLS
from ide_server.customizations.items import build_items

def test_read_tools_marks_in_use(tmp_path):
    rows = read_tools({"bash", "read"})
    assert {r["label"] for r in rows} == set(TOOLS)
    by = {r["label"]: r["inUse"] for r in rows}
    assert by["bash"] is True and by["glob"] is False

def test_build_items_has_nine_in_order(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps([]))
    home = tmp_path / "home"
    items = build_items(home, tmp_path)
    assert [i["key"] for i in items] == [
        "overview", "roles", "agents", "skills", "instructions", "hooks", "mcp", "plugins", "tools"]
    roles = next(i for i in items if i["key"] == "roles")
    assert roles["count"] == len(roles["rows"]) and roles["count"] >= 4   # PRESETS
    overview = next(i for i in items if i["key"] == "overview")
    assert isinstance(overview["rows"], list)   # resumen (conteos)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_customizations_items.py -q`
Expected: FAIL (`read_tools`/`TOOLS`/`build_items` no definidos).

- [ ] **Step 3: Write minimal implementation**

Agregar a `readers.py`:

```python
TOOLS = ["bash", "read", "write", "edit", "grep", "glob",
         "webSearch", "webFetch", "task", "todoWrite", "notebookEdit", "multiEdit"]

def read_tools(used_tools: set[str]) -> list[dict]:
    return [{"label": t, "inUse": t in used_tools} for t in TOOLS]
```

```python
# server/ide_server/customizations/items.py
from __future__ import annotations
from pathlib import Path
from ide_server.customizations.readers import (
    read_roles, read_mcp, read_instructions, read_hooks, read_skills,
    read_agents, read_plugins, read_tools, roles_in_use,
)

_META = {
    "overview": ("Overview", "Resumen del catálogo global de customizations."),
    "roles": ("Roles", "Roles disponibles para las sesiones."),
    "agents": ("Agents", "Subagentes disponibles."),
    "skills": ("Skills", "Skills reutilizables."),
    "instructions": ("Instructions", "Instrucciones globales (CLAUDE.md)."),
    "hooks": ("Hooks", "Hooks de ciclo de vida."),
    "mcp": ("MCP Servers", "Servidores MCP conectados."),
    "plugins": ("Plugins", "Plugins instalados."),
    "tools": ("Tools", "Tools disponibles para el agente."),
}

def _used_tools(home: Path, workspace_root: Path) -> set[str]:
    from ide_server.roles import resolve_role
    used: set[str] = set()
    for name in roles_in_use(workspace_root):
        r = resolve_role(workspace_root, name)
        if r and r.tools:
            used.update(r.tools)
    return used

def _item(key: str, rows: list[dict]) -> dict:
    title, desc = _META[key]
    return {"key": key, "title": title, "description": desc, "count": len(rows), "rows": rows}

def build_items(home: Path, workspace_root: Path) -> list[dict]:
    roles = read_roles(home, workspace_root)
    agents = read_agents(home)
    skills = read_skills(home)
    instructions = read_instructions(home)
    hooks = read_hooks(home)
    mcp = read_mcp(home)
    plugins = read_plugins(home)
    tools = read_tools(_used_tools(home, workspace_root))
    counts = {"roles": len(roles), "agents": len(agents), "skills": len(skills),
              "instructions": len(instructions), "hooks": len(hooks), "mcp": len(mcp),
              "plugins": len(plugins), "tools": len(tools)}
    overview = [{"label": f"{_META[k][0]}: {v}", "inUse": False} for k, v in counts.items()]
    return [
        _item("overview", overview), _item("roles", roles), _item("agents", agents),
        _item("skills", skills), _item("instructions", instructions), _item("hooks", hooks),
        _item("mcp", mcp), _item("plugins", plugins), _item("tools", tools),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_customizations_items.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/customizations/readers.py server/ide_server/customizations/items.py server/tests/test_customizations_items.py
git commit -m "feat(server): tools (in-use por roles) + build_items de los 9 items"
```

---

## Task 4: Capability `customizations.list` + registro en app

**Files:**
- Create: `server/ide_server/capabilities/customizations.py`
- Modify: `server/ide_server/app.py`
- Test: `server/tests/test_customizations_capability.py`

**Interfaces:**
- Consumes: `build_items`, `Registry`.
- Produces: `register(registry, root, home=None)` que registra `customizations.list` `{}` → `{"items": build_items(home or Path.home(), root)}`. `home` inyectable para tests.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_customizations_capability.py
import json
import pytest
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.capabilities import customizations as cap

@pytest.mark.asyncio
async def test_list_returns_nine_items(tmp_path):
    (tmp_path / ".ide").mkdir(); (tmp_path / ".ide" / "sessions.json").write_text(json.dumps([]))
    home = tmp_path / "home"
    reg = Registry()
    cap.register(reg, tmp_path, home=home)
    out = await reg.dispatch("customizations.list", {})
    assert [i["key"] for i in out["items"]] == [
        "overview", "roles", "agents", "skills", "instructions", "hooks", "mcp", "plugins", "tools"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_customizations_capability.py -q`
Expected: FAIL (`ModuleNotFoundError: ...capabilities.customizations`).

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/capabilities/customizations.py
from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.customizations.items import build_items

def register(registry: Registry, root: Path, home: Path | None = None) -> None:
    base = home or Path.home()

    async def list_(_payload: dict) -> dict:
        return {"items": build_items(base, root)}

    registry.register("customizations.list", list_)
```

En `server/ide_server/app.py`: importar y registrar junto a las otras capabilities:

```python
from ide_server.capabilities import customizations as customizations_cap
# ... tras registrar las demás:
customizations_cap.register(registry, root)
```

(Seguir el patrón exacto de registro de `repos_cap`/`sessions_cap` en `app.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_customizations_capability.py -q && cd server && uv run pytest -q`
Expected: PASS (1 nuevo; suite backend completa verde).

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/customizations.py server/ide_server/app.py server/tests/test_customizations_capability.py
git commit -m "feat(server): capability customizations.list + registro en app"
```

---

## Task 5: Frontend — transport `settingsChannel` + store `state/settings`

**Files:**
- Create: `ui/src/transport/settingsChannel.ts`, `ui/src/transport/settingsChannel.test.ts`, `ui/src/state/settings.ts`, `ui/src/state/settings.test.ts`

**Interfaces:**
- Produces: `fetchCustomizations(ws) -> Promise<Item[]>` (canal `customizations.list`). Store `useSettings` con `{ items: Item[], open: boolean, selectedKey: string, setData(items), openSettings(key), closeSettings() }`. Tipos `Row = {label, inUse}`, `Item = {key, title, description, count, rows: Row[]}`.

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/transport/settingsChannel.test.ts
import { describe, it, expect, vi } from "vitest";
import { fetchCustomizations } from "./settingsChannel";
describe("settingsChannel", () => {
  it("fetchCustomizations pide customizations.list y devuelve items", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ items: [{ key: "roles" }] }) } as any;
    expect(await fetchCustomizations(ws)).toEqual([{ key: "roles" }]);
    expect(ws.request).toHaveBeenCalledWith("customizations.list", {});
  });
});
```
```ts
// ui/src/state/settings.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { useSettings } from "./settings";
beforeEach(() => useSettings.setState({ items: [], open: false, selectedKey: "overview" }));
describe("useSettings", () => {
  it("openSettings abre en el item elegido; closeSettings cierra", () => {
    useSettings.getState().openSettings("roles");
    expect(useSettings.getState()).toMatchObject({ open: true, selectedKey: "roles" });
    useSettings.getState().closeSettings();
    expect(useSettings.getState().open).toBe(false);
  });
  it("setData guarda los items", () => {
    useSettings.getState().setData([{ key: "roles", title: "Roles", description: "", count: 1, rows: [] }] as any);
    expect(useSettings.getState().items).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- settings`
Expected: FAIL (módulos no encontrados).

- [ ] **Step 3: Write minimal implementation**

```ts
// ui/src/transport/settingsChannel.ts
import type { WsClient } from "./ws";
export interface Row { label: string; inUse: boolean }
export interface Item { key: string; title: string; description: string; count: number; rows: Row[] }
export async function fetchCustomizations(ws: WsClient): Promise<Item[]> {
  return (await ws.request("customizations.list", {})).items;
}
```
```ts
// ui/src/state/settings.ts
import { create } from "zustand";
import type { Item } from "../transport/settingsChannel";
interface SettingsState {
  items: Item[]; open: boolean; selectedKey: string;
  setData: (items: Item[]) => void;
  openSettings: (key: string) => void;
  closeSettings: () => void;
}
export const useSettings = create<SettingsState>((set) => ({
  items: [], open: false, selectedKey: "overview",
  setData: (items) => set({ items }),
  openSettings: (selectedKey) => set({ open: true, selectedKey }),
  closeSettings: () => set({ open: false }),
}));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- settings && npx tsc --noEmit`
Expected: PASS (3 tests), tsc limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/settingsChannel.ts ui/src/transport/settingsChannel.test.ts ui/src/state/settings.ts ui/src/state/settings.test.ts
git commit -m "feat(ui): transport + store de customizations/settings"
```

---

## Task 6: Frontend — `SettingsModal` (nav izq + panel derecho, badge "en uso")

**Files:**
- Create: `ui/src/modules/settings/SettingsModal.tsx`, `ui/src/modules/settings/SettingsModal.test.tsx`

**Interfaces:**
- Consumes: `useSettings`, shadcn `Dialog`, `Badge`.
- Produces: `SettingsModal()` — `Dialog` controlado por `useSettings().open`; nav izquierda lista `items` (activo resaltado, click → `openSettings(key)`); panel derecho muestra title/description del item seleccionado + filas (cada una con badge "en uso" si `row.inUse`); empty state si `rows` vacío. Cierra vía `onOpenChange` → `closeSettings`.

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/modules/settings/SettingsModal.test.tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useSettings } from "../../state/settings";
import { SettingsModal } from "./SettingsModal";

const items = [
  { key: "overview", title: "Overview", description: "resumen", count: 0, rows: [] },
  { key: "roles", title: "Roles", description: "roles del ws", count: 2,
    rows: [{ label: "arquitecto", inUse: true }, { label: "lector", inUse: false }] },
];
beforeEach(() => useSettings.setState({ items: items as any, open: true, selectedKey: "roles" }));

describe("SettingsModal", () => {
  it("muestra el item seleccionado con filas y badge en uso", () => {
    render(<SettingsModal />);
    expect(screen.getByText("roles del ws")).toBeInTheDocument();
    expect(screen.getByText("arquitecto")).toBeInTheDocument();
    const row = screen.getByText("arquitecto").closest("[data-row]") as HTMLElement;
    expect(row.textContent).toMatch(/en uso/i);
  });
  it("clickear otro item del nav lo selecciona", () => {
    render(<SettingsModal />);
    fireEvent.click(screen.getByRole("button", { name: /Overview/i }));
    expect(useSettings.getState().selectedKey).toBe("overview");
    expect(screen.getByText("resumen")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- SettingsModal`
Expected: FAIL (módulo no encontrado).

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/modules/settings/SettingsModal.tsx
import { Dialog, DialogContent } from "../../components/ui/dialog";
import { Badge } from "../../components/ui/badge";
import { cn } from "../../lib/utils";
import { useSettings } from "../../state/settings";

export function SettingsModal() {
  const { items, open, selectedKey, openSettings, closeSettings } = useSettings();
  const item = items.find((i) => i.key === selectedKey) ?? items[0];
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) closeSettings(); }}>
      <DialogContent className="flex h-[540px] max-w-[760px] gap-0 p-0 sm:max-w-[760px]">
        <nav className="w-[212px] shrink-0 border-r border-border bg-card p-2">
          {items.map((i) => (
            <button key={i.key} onClick={() => openSettings(i.key)}
              className={cn("flex w-full items-center justify-between rounded px-2 py-1.5 text-xs",
                i.key === selectedKey ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>
              <span>{i.title}</span>
              {i.count > 0 && <span className="text-[10px] text-muted-foreground">{i.count}</span>}
            </button>
          ))}
        </nav>
        <div className="min-w-0 flex-1 overflow-auto p-4">
          {item && (
            <>
              <div className="text-base font-medium text-foreground">{item.title}</div>
              <div className="mb-3 text-xs text-muted-foreground">{item.description}</div>
              {item.rows.length === 0 ? (
                <div className="text-xs text-muted-foreground">No configurado.</div>
              ) : (
                <div className="flex flex-col gap-1">
                  {item.rows.map((r, idx) => (
                    <div key={idx} data-row className="flex items-center justify-between rounded border border-border px-2 py-1.5 text-xs">
                      <span>{r.label}</span>
                      {r.inUse && <Badge variant="secondary" className="bg-role-pill text-primary text-[10px]">en uso</Badge>}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- SettingsModal && npx tsc --noEmit`
Expected: PASS (2 tests), tsc limpio. (El `Dialog` de Radix ya tiene los polyfills jsdom en `vitest.setup.ts`.)

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/settings/SettingsModal.tsx ui/src/modules/settings/SettingsModal.test.tsx
git commit -m "feat(ui): SettingsModal (nav izq + panel derecho + badge en uso)"
```

---

## Task 7: Frontend — `CustomizationsFooter` + integrar en `SessionsPanel` + montar el modal

**Files:**
- Create: `ui/src/modules/settings/CustomizationsFooter.tsx`, `ui/src/modules/settings/CustomizationsFooter.test.tsx`
- Modify: `ui/src/modules/sessions/SessionsPanel.tsx`, `ui/src/App.tsx`

**Interfaces:**
- Consumes: `useSettings`, `fetchCustomizations`, `getWs`.
- Produces: `CustomizationsFooter()` — al montar hace `fetchCustomizations` → `setData`; renderiza los 9 items (label + count) como lista vertical con borde superior; click en un item → `openSettings(key)`. `SessionsPanel` lo renderiza al pie; `App` monta `<SettingsModal />` (junto a `NewSessionModal`).

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/modules/settings/CustomizationsFooter.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useSettings } from "../../state/settings";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/settingsChannel", () => ({
  fetchCustomizations: vi.fn().mockResolvedValue([
    { key: "roles", title: "Roles", description: "", count: 3, rows: [] },
    { key: "tools", title: "Tools", description: "", count: 12, rows: [] },
  ]),
}));
import { CustomizationsFooter } from "./CustomizationsFooter";

beforeEach(() => useSettings.setState({ items: [], open: false, selectedKey: "overview" }));

describe("CustomizationsFooter", () => {
  it("carga los items y abre el modal al clickear uno", async () => {
    render(<CustomizationsFooter />);
    await waitFor(() => screen.getByText("Roles"));
    expect(screen.getByText("Tools")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Roles"));
    expect(useSettings.getState()).toMatchObject({ open: true, selectedKey: "roles" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- CustomizationsFooter`
Expected: FAIL (módulo no encontrado).

- [ ] **Step 3: Write minimal implementation**

```tsx
// ui/src/modules/settings/CustomizationsFooter.tsx
import { useEffect } from "react";
import { useSettings } from "../../state/settings";
import { fetchCustomizations } from "../../transport/settingsChannel";
import { getWs } from "../../transport/wsClient";

export function CustomizationsFooter() {
  const { items, setData, openSettings } = useSettings();
  useEffect(() => {
    fetchCustomizations(getWs()).then(setData).catch(() => setData([]));
  }, [setData]);
  return (
    <div className="mt-auto border-t border-border py-1">
      {items.map((i) => (
        <button key={i.key} onClick={() => openSettings(i.key)}
          className="flex w-full items-center justify-between px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground">
          <span>{i.title}</span>
          {i.count > 0 && <span className="text-[10px]">{i.count}</span>}
        </button>
      ))}
    </div>
  );
}
```

En `ui/src/modules/sessions/SessionsPanel.tsx`: importar `CustomizationsFooter` y renderizarlo como último hijo del `<aside>` (después del árbol / fila "+ Agregar sesión"). El `<aside>` ya es `flex flex-col`; el footer usa `mt-auto` para irse abajo.

En `ui/src/App.tsx`: importar `SettingsModal` y montarlo junto a `NewSessionModal`:
```tsx
import { SettingsModal } from "./modules/settings/SettingsModal";
// ... dentro del árbol de App, junto a <NewSessionModal />:
<SettingsModal />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- CustomizationsFooter && npm test && npx tsc --noEmit && npm run build`
Expected: PASS (1 nuevo; suite frontend verde; tsc + build limpios). Ajustar `SessionsPanel.test.tsx` sólo si una aserción existente choca (el footer agrega items al aside; el mock de `settingsChannel`/`wsClient` puede necesitar añadirse al test de SessionsPanel si el footer dispara el fetch — mockearlo ahí como en este test, sin aflojar aserciones).

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/settings/CustomizationsFooter.tsx ui/src/modules/settings/CustomizationsFooter.test.tsx ui/src/modules/sessions/SessionsPanel.tsx ui/src/App.tsx ui/src/modules/sessions/SessionsPanel.test.tsx
git commit -m "feat(ui): CustomizationsFooter en el sidebar + montar SettingsModal"
```

---

## Task 8: Verificación end-to-end (manual)

**Files:** ninguno (validación).

- [ ] **Step 1: Suites + tsc + build**

```bash
cd server && uv run pytest -q && cd ../ui && npm test && npx tsc --noEmit && npm run build
```
Expected: backend + frontend verdes; tsc + build limpios.

- [ ] **Step 2: En vivo**

```bash
cd server && uv run ide --cwd ~/ide-demo --no-browser &
sleep 3; cd ui && npm run dev
```
Expected: en `localhost:5173`, al pie del sidebar de sesiones aparecen los 9 items (Overview, Roles, Agents, …, Tools) con counts. Click en **Roles** → modal con nav izq + panel derecho, roster de roles con badge **"en uso"** en los asignados a sesiones. Los items sin datos muestran "No configurado". Verificar con Playwright (captura).

- [ ] **Step 3: Commit (si hubo ajustes)**

```bash
git commit -am "chore: settings/customizations end-to-end verificado" || true
```

---

## Self-Review

**Spec coverage:** Footer 9 items → Tasks 3,7. Modal nav+panel+badge → Task 6. Scope global (home inyectable) → constraint + Tasks 1-4. Read-only → sin escritura en ninguna tarea. Roles roster global + in-use → Task 1. Lectores `~/.claude` tolerantes → Task 2. Tools estático + in-use → Task 3. Overview conteos → Task 3. Capability + registro → Task 4. Transport+store → Task 5. Empty states → Task 6. Errores sin fallo silencioso (footer `.catch(setData([]))`) → Task 7. Tests back+front → todas. **Sin gaps.**

**Placeholder scan:** sin TBD/TODO; todo step trae código real y comandos con expected. La única nota condicional (ajustar `SessionsPanel.test.tsx` si choca) es un contingente explícito de integración, no un placeholder de lógica.

**Type consistency:** `Row {label, inUse}` y `Item {key, title, description, count, rows}` consistentes backend (dicts en `build_items`) ↔ transport (`settingsChannel.ts`) ↔ store/UI. Canal WS `customizations.list` idéntico entre `capabilities/customizations.py` y `settingsChannel.ts`. Orden de los 9 keys idéntico en constraint, Task 3, Task 4 test. `read_roles(home, workspace_root)` / `build_items(home, workspace_root)` / `register(registry, root, home=None)` con firmas consistentes entre tareas.

## Notas de ejecución

- Rama `feat/settings-customizations` (sale de `main` con R0–R3 + fixes + spec).
- Los lectores nunca tocan el `~/.claude` real en tests: reciben `home=tmp_path`. La capability usa `Path.home()` en runtime.
- `tomllib` es stdlib (py3.11+); el proyecto es py3.12. `~/.claude.json` y `~/.claude/settings.json` son JSON.
