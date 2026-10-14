# Config editable de mlx (Rebanada 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps
> usan checkbox (`- [ ]`).

**Goal:** Hacer editable la config `[mlx]` desde el panel "Modelos": toggle `enabled`, elegir modelo,
editar el router prompt. Escribe `.ide/config.toml` preservando el resto.

**Architecture:** Backend `mlx/config.py` gana `mlx_config_raw` (leer crudo) + `write_mlx_config`
(read-modify-write con `tomli_w`); capability `mlx.config.get/set` cableada en `app.py`. Frontend
`state/mlxConfig.ts` + handlers en `transport/modelsChannel.ts` + sección `MlxConfigSection` montada
arriba del `ModelsPanel`.

**Tech Stack:** Python/FastAPI (`tomllib`+`tomli-w`, ya deps), React/TS/vitest/zustand, shadcn/Tailwind.

## Global Constraints

- **Sin fallos silenciosos:** `enabled=true` con `model` vacío → `raise ValueError` (envelope; el form
  muestra el error), nunca guarda una config inerte. Error de escritura → envelope.
- **Preserva el resto del `config.toml`:** merge con `data.setdefault("mlx", {})` — no pisa otras
  secciones (roles/notion) ni otras claves de `[mlx]` (`port`).
- **Por-proyecto:** escribe/lee `root/.ide/config.toml` del workspace.
- **`router_prompt` == default → NO se persiste** (queda el default del código; toml limpio).
- **Fidelidad 1a/shadcn:** solo tokens (`bg-primary`, `border-border`, `text-muted-foreground`,
  `text-destructive`, `text-primary-foreground`, etc.). Sin hex arbitrario.
- **Commits atómicos, en español.** Un commit por tarea. Se trabaja en `main` directo.

---

### Task 1: `mlx/config.py` — `mlx_config_raw` + `write_mlx_config`

**Files:**
- Modify: `server/ide_server/mlx/config.py`
- Test: `server/tests/test_mlx_config_write.py`

**Interfaces:**
- Produces: `mlx_config_raw(root) -> dict` (`{enabled, model, router_prompt, default_prompt}`);
  `write_mlx_config(root, *, enabled: bool, model: str, router_prompt: str) -> None`.

- [ ] **Step 1: Tests que fallan** — `server/tests/test_mlx_config_write.py`:

```python
import tomllib
from ide_server.mlx.config import mlx_config_raw, write_mlx_config, mlx_config, DEFAULT_ROUTER_PROMPT


def test_raw_defaults_without_config(tmp_path):
    assert mlx_config_raw(tmp_path) == {
        "enabled": False, "model": "", "router_prompt": DEFAULT_ROUTER_PROMPT,
        "default_prompt": DEFAULT_ROUTER_PROMPT}


def test_raw_reads_values(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "config.toml").write_text('[mlx]\nenabled = true\nmodel = "m"\n')
    r = mlx_config_raw(tmp_path)
    assert r["enabled"] is True and r["model"] == "m"
    assert r["router_prompt"] == DEFAULT_ROUTER_PROMPT and r["default_prompt"] == DEFAULT_ROUTER_PROMPT


def test_write_preserves_other_sections_and_port(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "config.toml").write_text(
        '[roles]\narquitecto = { model = "opus" }\n\n[mlx]\nport = 9001\n')
    write_mlx_config(tmp_path, enabled=True, model="mlx-community/X",
                     router_prompt=DEFAULT_ROUTER_PROMPT)
    data = tomllib.loads((tmp_path / ".ide" / "config.toml").read_text())
    assert data["roles"]["arquitecto"]["model"] == "opus"       # preservado
    assert data["mlx"]["port"] == 9001                          # preservado
    assert data["mlx"]["enabled"] is True and data["mlx"]["model"] == "mlx-community/X"
    assert "router_prompt" not in data["mlx"]                   # == default → no se persiste
    cfg = mlx_config(tmp_path)
    assert cfg.model == "mlx-community/X" and cfg.port == 9001


def test_write_persists_custom_prompt(tmp_path):
    write_mlx_config(tmp_path, enabled=True, model="m", router_prompt="MI PROMPT")
    data = tomllib.loads((tmp_path / ".ide" / "config.toml").read_text())
    assert data["mlx"]["router_prompt"] == "MI PROMPT"
    assert mlx_config_raw(tmp_path)["router_prompt"] == "MI PROMPT"


def test_write_creates_ide_dir(tmp_path):
    write_mlx_config(tmp_path, enabled=False, model="", router_prompt=DEFAULT_ROUTER_PROMPT)
    assert (tmp_path / ".ide" / "config.toml").is_file()
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar** — agregar a `server/ide_server/mlx/config.py` (al final; `mlx_config` y
  `DEFAULT_ROUTER_PROMPT` ya existen). Agregar `import tomli_w` con los imports del tope:

```python
def mlx_config_raw(root: Path) -> dict:
    path = root / ".ide" / "config.toml"
    mlx: object = {}
    if path.is_file():
        try:
            mlx = tomllib.loads(path.read_text(encoding="utf-8")).get("mlx") or {}
        except (tomllib.TOMLDecodeError, OSError):
            mlx = {}
    if not isinstance(mlx, dict):
        mlx = {}
    return {
        "enabled": bool(mlx.get("enabled")),
        "model": str(mlx.get("model") or ""),
        "router_prompt": str(mlx.get("router_prompt") or DEFAULT_ROUTER_PROMPT),
        "default_prompt": DEFAULT_ROUTER_PROMPT,
    }


def write_mlx_config(root: Path, *, enabled: bool, model: str, router_prompt: str) -> None:
    path = root / ".ide" / "config.toml"
    data: dict = {}
    if path.is_file():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    mlx = data.setdefault("mlx", {})
    mlx["enabled"] = bool(enabled)
    mlx["model"] = model
    if router_prompt and router_prompt != DEFAULT_ROUTER_PROMPT:
        mlx["router_prompt"] = router_prompt
    else:
        mlx.pop("router_prompt", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(data), encoding="utf-8")
```

- [ ] **Step 4: Correr, verificar que pasan** → PASS. Suite completa → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/mlx/config.py server/tests/test_mlx_config_write.py
git commit -m "feat(mlx): mlx_config_raw + write_mlx_config (escribe [mlx] preservando el resto)"
```

---

### Task 2: `capabilities/mlx_config.py` + wire `app.py`

**Files:**
- Create: `server/ide_server/capabilities/mlx_config.py`
- Modify: `server/ide_server/app.py`
- Test: `server/tests/test_mlx_config_capability.py`

**Interfaces:**
- Consumes: `mlx_config_raw`/`write_mlx_config` (T1).
- Produces: `register(registry, root)` con `mlx.config.get` / `mlx.config.set`.

- [ ] **Step 1: Tests que fallan** — `server/tests/test_mlx_config_capability.py`:

```python
import pytest
from ide_server.plugins import Registry
import ide_server.capabilities.mlx_config as cap


def _reg(root):
    reg = Registry(); cap.register(reg, root); return reg


@pytest.mark.asyncio
async def test_get_returns_camel_defaults(tmp_path):
    out = await _reg(tmp_path).dispatch("mlx.config.get", {})
    assert out["enabled"] is False and out["model"] == ""
    assert out["defaultPrompt"] and out["routerPrompt"] == out["defaultPrompt"]


@pytest.mark.asyncio
async def test_set_writes_and_get_reflects(tmp_path):
    reg = _reg(tmp_path)
    assert await reg.dispatch("mlx.config.set",
        {"enabled": True, "model": "mlx-community/X", "routerPrompt": ""}) == {"saved": True}
    out = await reg.dispatch("mlx.config.get", {})
    assert out["enabled"] is True and out["model"] == "mlx-community/X"


@pytest.mark.asyncio
async def test_set_enabled_without_model_raises(tmp_path):
    with pytest.raises(ValueError):
        await _reg(tmp_path).dispatch("mlx.config.set",
            {"enabled": True, "model": "  ", "routerPrompt": ""})


@pytest.mark.asyncio
async def test_set_disabled_without_model_ok(tmp_path):
    assert await _reg(tmp_path).dispatch("mlx.config.set",
        {"enabled": False, "model": "", "routerPrompt": ""}) == {"saved": True}
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar** — `server/ide_server/capabilities/mlx_config.py`:

```python
from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.mlx.config import mlx_config_raw, write_mlx_config


def register(registry: Registry, root: Path) -> None:
    async def get(_payload: dict) -> dict:
        r = mlx_config_raw(root)
        return {"enabled": r["enabled"], "model": r["model"],
                "routerPrompt": r["router_prompt"], "defaultPrompt": r["default_prompt"]}

    async def set_(payload: dict) -> dict:
        enabled = bool(payload.get("enabled"))
        model = (payload.get("model") or "").strip()
        router_prompt = payload.get("routerPrompt") or ""
        if enabled and not model:
            raise ValueError("elige un modelo para prender mlx")
        write_mlx_config(root, enabled=enabled, model=model, router_prompt=router_prompt)
        return {"saved": True}

    registry.register("mlx.config.get", get)
    registry.register("mlx.config.set", set_)
```

En `server/ide_server/app.py`: agregar el import con las otras capabilities
(`from ide_server.capabilities import mlx_config as mlx_config_cap`) y, dentro de `create_app` junto a
los otros `*_cap.register(...)`, agregar:

```python
    mlx_config_cap.register(registry, root)
```

- [ ] **Step 4: Correr, verificar que pasan** → PASS. Suite completa (incl. `create_app`) → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/mlx_config.py server/ide_server/app.py server/tests/test_mlx_config_capability.py
git commit -m "feat(mlx): capability mlx.config.get/set (valida enabled sin modelo) + wire en app"
```

---

### Task 3: Frontend — `state/mlxConfig.ts` + transport

**Files:**
- Create: `ui/src/state/mlxConfig.ts`
- Modify: `ui/src/transport/modelsChannel.ts`
- Test: `ui/src/state/mlxConfig.test.ts`, `ui/src/transport/modelsChannel.test.ts` (agregar un caso)

**Interfaces:**
- Produces: `MlxConfig`, `useMlxConfig` (store); `getMlxConfig`/`setMlxConfig`.

- [ ] **Step 1: Tests que fallan**

`ui/src/state/mlxConfig.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { useMlxConfig } from "./mlxConfig";

beforeEach(() => useMlxConfig.setState({ enabled: false, model: "", routerPrompt: "", defaultPrompt: "", loaded: false, error: null }));

describe("useMlxConfig", () => {
  it("setConfig puebla y marca loaded", () => {
    useMlxConfig.getState().setConfig({ enabled: true, model: "m", routerPrompt: "p", defaultPrompt: "d" });
    const s = useMlxConfig.getState();
    expect(s.enabled).toBe(true); expect(s.model).toBe("m"); expect(s.loaded).toBe(true);
  });
  it("update muta un campo", () => {
    useMlxConfig.getState().update({ model: "x" });
    expect(useMlxConfig.getState().model).toBe("x");
  });
  it("setError guarda el error", () => {
    useMlxConfig.getState().setError("boom");
    expect(useMlxConfig.getState().error).toBe("boom");
  });
});
```

En `ui/src/transport/modelsChannel.test.ts`, agregar (importando `getMlxConfig`, `setMlxConfig`):

```ts
  it("getMlxConfig y setMlxConfig pegan a los canales mlx.config", async () => {
    const ws = { request: vi.fn().mockResolvedValue({}) } as any;
    await getMlxConfig(ws);
    expect(ws.request).toHaveBeenCalledWith("mlx.config.get", {});
    setMlxConfig(ws, { enabled: true, model: "m", routerPrompt: "p" });
    expect(ws.request).toHaveBeenCalledWith("mlx.config.set", { enabled: true, model: "m", routerPrompt: "p" });
  });
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

`ui/src/state/mlxConfig.ts`:

```ts
import { create } from "zustand";

export interface MlxConfig { enabled: boolean; model: string; routerPrompt: string; defaultPrompt: string; }

interface MlxConfigState extends MlxConfig {
  loaded: boolean; error: string | null;
  setConfig: (c: MlxConfig) => void;
  update: (partial: Partial<MlxConfig>) => void;
  setError: (e: string | null) => void;
}

export const useMlxConfig = create<MlxConfigState>((set) => ({
  enabled: false, model: "", routerPrompt: "", defaultPrompt: "", loaded: false, error: null,
  setConfig: (c) => set({ ...c, loaded: true, error: null }),
  update: (partial) => set(partial),
  setError: (error) => set({ error }),
}));
```

En `ui/src/transport/modelsChannel.ts` agregar (con el import del tipo):

```ts
import type { MlxConfig } from "../state/mlxConfig";

export function getMlxConfig(ws: WsClient): Promise<MlxConfig> {
  return ws.request("mlx.config.get", {});
}
export function setMlxConfig(ws: WsClient, c: { enabled: boolean; model: string; routerPrompt: string }): Promise<any> {
  return ws.request("mlx.config.set", c);
}
```

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd ui && npm test -- mlxConfig modelsChannel` → PASS. `cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/state/mlxConfig.ts ui/src/transport/modelsChannel.ts ui/src/state/mlxConfig.test.ts ui/src/transport/modelsChannel.test.ts
git commit -m "feat(mlx): store + transport de la config editable en el frontend"
```

---

### Task 4: Frontend — `MlxConfigSection` + wire `ModelsPanel`

**Files:**
- Create: `ui/src/modules/settings/MlxConfigSection.tsx`, `ui/src/modules/settings/MlxConfigSection.test.tsx`
- Modify: `ui/src/modules/settings/ModelsPanel.tsx`, `ui/src/modules/settings/ModelsPanel.test.tsx`,
  `ui/src/modules/settings/SettingsModal.test.tsx`

**Interfaces:**
- Consumes: `useMlxConfig` (T3), `useModels`, `getMlxConfig`/`setMlxConfig`/`fetchModels` (T3/anterior).

- [ ] **Step 1: Tests que fallan**

`ui/src/modules/settings/MlxConfigSection.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useMlxConfig } from "../../state/mlxConfig";
import { useModels } from "../../state/models";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const setMlxConfig = vi.fn().mockResolvedValue({});
vi.mock("../../transport/modelsChannel", () => ({
  getMlxConfig: () => Promise.resolve({ enabled: false, model: "", routerPrompt: "D", defaultPrompt: "D" }),
  setMlxConfig: (...a: any[]) => setMlxConfig(...a),
  fetchModels: () => Promise.resolve({ curated: [], installed: [], inUse: null, active: {} }),
}));
import { MlxConfigSection } from "./MlxConfigSection";

beforeEach(() => {
  setMlxConfig.mockClear();
  useMlxConfig.setState({ enabled: true, model: "mlx-community/A", routerPrompt: "P", defaultPrompt: "D", loaded: true, error: null });
  useModels.setState({ installed: [{ repoId: "mlx-community/A", sizeOnDisk: 100 }] } as any);
});

describe("MlxConfigSection", () => {
  it("renderiza toggle, modelo y prompt", () => {
    render(<MlxConfigSection />);
    expect(screen.getByText(/Activar routing/i)).toBeInTheDocument();
    expect((screen.getByPlaceholderText("mlx-community/...") as HTMLInputElement).value).toBe("mlx-community/A");
  });
  it("restaurar default setea el prompt al defaultPrompt", () => {
    render(<MlxConfigSection />);
    fireEvent.click(screen.getByText(/restaurar default/i));
    expect(useMlxConfig.getState().routerPrompt).toBe("D");
  });
  it("Guardar llama setMlxConfig con los valores", () => {
    render(<MlxConfigSection />);
    fireEvent.click(screen.getByText("Guardar", { selector: "[data-save-config]" }));
    expect(setMlxConfig).toHaveBeenCalledWith({}, { enabled: true, model: "mlx-community/A", routerPrompt: "P" });
  });
});
```

En `ui/src/modules/settings/ModelsPanel.test.tsx` y `ui/src/modules/settings/SettingsModal.test.tsx`:
el `vi.mock("../../transport/modelsChannel", ...)` de AMBOS archivos debe ganar las funciones nuevas
(si no, `MlxConfigSection` —que ahora renderiza `ModelsPanel`— llama `getMlxConfig` undefined y rompe).
Agregar al objeto mockeado de cada uno:

```tsx
  getMlxConfig: () => Promise.resolve({ enabled: false, model: "", routerPrompt: "D", defaultPrompt: "D" }),
  setMlxConfig: () => Promise.resolve({}),
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

`ui/src/modules/settings/MlxConfigSection.tsx`:

```tsx
import { useEffect } from "react";
import { useMlxConfig } from "../../state/mlxConfig";
import { useModels } from "../../state/models";
import { getMlxConfig, setMlxConfig, fetchModels } from "../../transport/modelsChannel";
import { getWs } from "../../transport/wsClient";

export function MlxConfigSection() {
  const { enabled, model, routerPrompt, defaultPrompt, error, setConfig, update, setError } = useMlxConfig();
  const installed = useModels((s) => s.installed);
  const setCatalog = useModels((s) => s.setCatalog);
  useEffect(() => { getMlxConfig(getWs()).then(setConfig).catch(() => {}); }, [setConfig]);
  const save = () => {
    setError(null);
    setMlxConfig(getWs(), { enabled, model, routerPrompt })
      .then(() => fetchModels(getWs()).then(setCatalog).catch(() => {}))
      .catch((e) => setError(e?.message || "no se pudo guardar"));
  };
  return (
    <section data-mlx-config>
      <div className="mb-1 text-xs font-medium text-foreground">Configuración</div>
      <div className="flex flex-col gap-2 rounded border border-border px-2 py-2 text-xs">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={enabled} onChange={(e) => update({ enabled: e.target.checked })} />
          <span>Activar routing con modelo local (mlx)</span>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">Modelo</span>
          <input list="mlx-installed" value={model} onChange={(e) => update({ model: e.target.value })}
            placeholder="mlx-community/..." className="rounded border border-border bg-transparent px-2 py-1" />
          <datalist id="mlx-installed">
            {installed.map((m) => <option key={m.repoId} value={m.repoId} />)}
          </datalist>
        </label>
        <label className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Prompt del router</span>
            <button onClick={() => update({ routerPrompt: defaultPrompt })}
              className="text-[10px] text-muted-foreground hover:text-foreground">restaurar default</button>
          </div>
          <textarea value={routerPrompt} onChange={(e) => update({ routerPrompt: e.target.value })}
            rows={4} className="rounded border border-border bg-transparent px-2 py-1 font-mono text-[11px]" />
        </label>
        {error && <div className="text-[10px] text-destructive">{error}</div>}
        <div>
          <button data-save-config onClick={save}
            className="rounded bg-primary px-2 py-1 text-[10px] text-primary-foreground">Guardar</button>
        </div>
      </div>
    </section>
  );
}
```

En `ui/src/modules/settings/ModelsPanel.tsx`: importar y renderizar la sección como PRIMERA del panel.
Agregar `import { MlxConfigSection } from "./MlxConfigSection";` y, justo después de
`<div className="flex flex-col gap-4">`, agregar `<MlxConfigSection />` antes de la `<section>` de
Catálogo. No tocar el resto del componente.

- [ ] **Step 2/4: Correr, verificar que pasan**

Run: `cd ui && npm test -- MlxConfigSection ModelsPanel SettingsModal` → PASS. Suite completa
`cd ui && npm test` → PASS (sin regresiones). `cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/settings/MlxConfigSection.tsx ui/src/modules/settings/MlxConfigSection.test.tsx ui/src/modules/settings/ModelsPanel.tsx ui/src/modules/settings/ModelsPanel.test.tsx ui/src/modules/settings/SettingsModal.test.tsx
git commit -m "feat(mlx): sección Configuración editable en el panel Modelos (toggle/model/prompt)"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** `mlx_config_raw`+`write_mlx_config` (T1), capability get/set+validación+wire
  (T2), store+transport (T3), sección editable + wire panel (T4). ✓
- **Consistencia:** `write_mlx_config(enabled,model,router_prompt)` (T1) ↔ capability `set` (T2) ↔
  `setMlxConfig({enabled,model,routerPrompt})` (T3) ↔ `MlxConfigSection.save` (T4). `mlx_config_raw`
  keys snake ↔ capability serializa a camel (`routerPrompt`/`defaultPrompt`) ↔ `MlxConfig` front.
- **Sin fallos silenciosos:** `enabled` sin `model` → `ValueError` → envelope; el form muestra `error`.
  `router_prompt`==default → no se persiste (toml limpio) pero el form siempre muestra algo (default).
- **Riesgo señalado (T4):** los mocks de `modelsChannel` en `ModelsPanel.test` y `SettingsModal.test`
  DEBEN ganar `getMlxConfig`/`setMlxConfig` o esos tests rompen (MlxConfigSection se monta vía ModelsPanel).
- **Verificación en vivo (fuera del plan):** prender mlx desde el panel con un modelo instalado, guardar,
  ver `[mlx]` en el toml y el badge "en uso" aparecer.
```
