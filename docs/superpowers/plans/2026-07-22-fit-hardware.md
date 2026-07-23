# Fit del hardware (llmfit) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps
> usan checkbox (`- [ ]`).

**Goal:** Por modelo del panel "Modelos", un badge de fit (entra/justo/no entra) + tok/s + detalles,
vía la CLI `llmfit` (dep opcional externa). Degrada sin badges si `llmfit` no está.

**Architecture:** Backend `models/fit.py` (spawn `llmfit info <repo_id> --json`, parse, cache) +
capability `models.fit` (archivo nuevo `capabilities/models_fit.py`). Frontend: `fit` en `state/models.ts`,
`fetchFit` en `transport/modelsChannel.ts`, componente `FitBadge` en `ModelsPanel`.

**Tech Stack:** Python/FastAPI (`subprocess`, `asyncio`), React/TS/vitest/zustand, shadcn/Tailwind.

## Global Constraints

- **Sin fallos silenciosos:** `llmfit` ausente / repo desconocido / JSON malformado / timeout → `None`
  (sin badge), nunca una excepción que tumbe `models.fit`. `None` = "sin dato", no error tragado.
- **Nivel derivado de memoria** (no del string de llmfit): `req/avail <= 0.75` → "ok"; `<= 1.0` →
  "tight"; `> 1.0` → "no". Igual se guarda `fit_label` de llmfit para mostrar.
- **Archivos NUEVOS en backend** (`models/fit.py`, `capabilities/models_fit.py`) — NO re-editar
  `mlx/*.py` (el dueño los está puliendo con type hints).
- **`llmfit` NO se importa ni bundlea** — se spawnea; los tests inyectan `run` fake, nada real corre.
- **Fidelidad 1a:** verde `#7fb069` (entra), ámbar `#e0863f` (justo), `text-destructive` (no entra).
- **Commits atómicos, en español.** Un commit por tarea. Se trabaja en `main` directo.

---

### Task 1: `models/fit.py`

**Files:**
- Create: `server/ide_server/models/fit.py`
- Test: `server/tests/test_models_fit.py`

**Interfaces:**
- Produces: `FitInfo` (dataclass), `level_from(required, available) -> str`,
  `_run_llmfit(repo_id) -> dict | None`, `ModelFit(run=_run_llmfit)` con `async fit_for(repo_ids) -> dict`.

- [ ] **Step 1: Tests que fallan** — `server/tests/test_models_fit.py`:

```python
import pytest
from ide_server.models.fit import level_from, ModelFit, FitInfo, _run_llmfit


def test_level_from():
    assert level_from(10, 24) == "ok"       # 0.42
    assert level_from(18, 24) == "ok"       # 0.75 (borde inclusive)
    assert level_from(20, 24) == "tight"    # 0.83
    assert level_from(24, 24) == "tight"    # 1.0
    assert level_from(40, 24) == "no"       # 1.67
    assert level_from(5, 0) == "no"         # sin memoria conocida


RAW = {"fit_label": "Perfect", "memory_required_gb": 6.72, "memory_available_gb": 24.0,
       "estimated_tps": 9.5, "disk_size_gb": 5.79, "best_quant": "mlx-8bit",
       "context_length": 32768, "score": 87.0,
       "score_components": {"fit": 100, "speed": 20, "quality": 99, "context": 100}}


@pytest.mark.asyncio
async def test_fit_for_builds_fitinfo():
    mf = ModelFit(run=lambda rid: dict(RAW))
    fi = (await mf.fit_for(["mlx-community/Q"]))["mlx-community/Q"]
    assert isinstance(fi, FitInfo) and fi.level == "ok"
    assert fi.estimated_tps == 9.5 and fi.best_quant == "mlx-8bit"
    assert fi.score_components["speed"] == 20


@pytest.mark.asyncio
async def test_fit_for_none_when_unknown():
    assert await ModelFit(run=lambda rid: None).fit_for(["x"]) == {"x": None}


@pytest.mark.asyncio
async def test_fit_for_caches():
    calls = {"n": 0}
    def run(rid): calls["n"] += 1; return dict(RAW)
    mf = ModelFit(run=run)
    await mf.fit_for(["a"]); await mf.fit_for(["a"])
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_fit_for_concurrent_two():
    out = await ModelFit(run=lambda rid: dict(RAW)).fit_for(["a", "b"])
    assert set(out) == {"a", "b"} and out["a"].level == "ok"


def test_run_llmfit_absent_returns_none(monkeypatch):
    import ide_server.models.fit as fitmod
    def boom(*a, **k): raise FileNotFoundError("no llmfit")
    monkeypatch.setattr(fitmod.subprocess, "run", boom)
    assert _run_llmfit("x") is None


def test_run_llmfit_non_json_returns_none(monkeypatch):
    import ide_server.models.fit as fitmod
    class _P: stdout = "no soy json"
    monkeypatch.setattr(fitmod.subprocess, "run", lambda *a, **k: _P())
    assert _run_llmfit("x") is None


def test_run_llmfit_parses_models0(monkeypatch):
    import ide_server.models.fit as fitmod, json
    class _P: stdout = json.dumps({"models": [RAW]})
    monkeypatch.setattr(fitmod.subprocess, "run", lambda *a, **k: _P())
    assert _run_llmfit("x")["best_quant"] == "mlx-8bit"
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar** — `server/ide_server/models/fit.py`:

```python
from __future__ import annotations
import asyncio
import json
import subprocess
from dataclasses import dataclass


@dataclass
class FitInfo:
    repo_id: str
    level: str            # "ok" | "tight" | "no"
    fit_label: str
    memory_required_gb: float
    memory_available_gb: float
    estimated_tps: float
    disk_size_gb: float
    best_quant: str
    context_length: int
    score: float
    score_components: dict


def level_from(required: float, available: float) -> str:
    if not available or available <= 0:
        return "no"
    ratio = required / available
    if ratio <= 0.75:
        return "ok"
    if ratio <= 1.0:
        return "tight"
    return "no"


def _run_llmfit(repo_id: str) -> dict | None:
    try:
        proc = subprocess.run(["llmfit", "info", repo_id, "--json"],
                              capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not models:
        return None
    return models[0]


def _to_fit(repo_id: str, raw: dict) -> FitInfo:
    req = float(raw.get("memory_required_gb") or 0)
    avail = float(raw.get("memory_available_gb") or 0)
    comps = raw.get("score_components") or {}
    return FitInfo(
        repo_id=repo_id, level=level_from(req, avail), fit_label=str(raw.get("fit_label") or ""),
        memory_required_gb=req, memory_available_gb=avail,
        estimated_tps=float(raw.get("estimated_tps") or 0),
        disk_size_gb=float(raw.get("disk_size_gb") or 0),
        best_quant=str(raw.get("best_quant") or ""),
        context_length=int(raw.get("context_length") or 0),
        score=float(raw.get("score") or 0),
        score_components={k: comps.get(k) for k in ("fit", "speed", "quality", "context")},
    )


class ModelFit:
    def __init__(self, run=_run_llmfit) -> None:
        self._run = run
        self._cache: dict[str, FitInfo | None] = {}

    async def fit_for(self, repo_ids: list[str]) -> dict[str, FitInfo | None]:
        todo = [r for r in repo_ids if r not in self._cache]
        raws = await asyncio.gather(*(asyncio.to_thread(self._run, r) for r in todo))
        for repo_id, raw in zip(todo, raws):
            self._cache[repo_id] = _to_fit(repo_id, raw) if raw else None
        return {r: self._cache.get(r) for r in repo_ids}
```

- [ ] **Step 4: Correr, verificar que pasan** → PASS. Suite completa → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/models/fit.py server/tests/test_models_fit.py
git commit -m "feat(models): fit del hardware vía llmfit (parse + nivel + cache, degrada si ausente)"
```

---

### Task 2: `capabilities/models_fit.py` + wire `app.py`

**Files:**
- Create: `server/ide_server/capabilities/models_fit.py`
- Modify: `server/ide_server/app.py`
- Test: `server/tests/test_models_fit_capability.py`

**Interfaces:**
- Consumes: `ModelFit`/`FitInfo` (T1).
- Produces: `register(registry, root, fit=None)` con `models.fit {repoIds}` → `{repoId: dict|null}`.

- [ ] **Step 1: Tests que fallan** — `server/tests/test_models_fit_capability.py`:

```python
import pytest
from ide_server.plugins import Registry
import ide_server.capabilities.models_fit as cap
from ide_server.models.fit import FitInfo


class _FakeFit:
    def __init__(self, mapping): self._m = mapping
    async def fit_for(self, repo_ids): return {r: self._m.get(r) for r in repo_ids}


def _fi():
    return FitInfo("a", "ok", "Perfect", 6.7, 24.0, 9.5, 5.8, "mlx-8bit", 32768, 87.0,
                   {"fit": 100, "speed": 20, "quality": 99, "context": 100})


@pytest.mark.asyncio
async def test_models_fit_serializes_camel(tmp_path):
    reg = Registry(); cap.register(reg, tmp_path, fit=_FakeFit({"a": _fi()}))
    out = await reg.dispatch("models.fit", {"repoIds": ["a"]})
    assert out["a"]["level"] == "ok" and out["a"]["estimatedTps"] == 9.5
    assert out["a"]["memoryRequiredGb"] == 6.7 and out["a"]["scoreComponents"]["speed"] == 20


@pytest.mark.asyncio
async def test_models_fit_none_stays_null(tmp_path):
    reg = Registry(); cap.register(reg, tmp_path, fit=_FakeFit({"a": None}))
    assert await reg.dispatch("models.fit", {"repoIds": ["a"]}) == {"a": None}


@pytest.mark.asyncio
async def test_models_fit_empty_repoids(tmp_path):
    reg = Registry(); cap.register(reg, tmp_path, fit=_FakeFit({}))
    assert await reg.dispatch("models.fit", {}) == {}
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar** — `server/ide_server/capabilities/models_fit.py`:

```python
from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.models.fit import ModelFit, FitInfo


def _to_payload(fi: FitInfo) -> dict:
    return {
        "level": fi.level, "fitLabel": fi.fit_label,
        "memoryRequiredGb": fi.memory_required_gb, "memoryAvailableGb": fi.memory_available_gb,
        "estimatedTps": fi.estimated_tps, "diskSizeGb": fi.disk_size_gb,
        "bestQuant": fi.best_quant, "contextLength": fi.context_length,
        "score": fi.score, "scoreComponents": fi.score_components,
    }


def register(registry: Registry, root: Path, fit=None) -> None:
    fit = fit or ModelFit()

    async def models_fit(payload: dict) -> dict:
        repo_ids = list(payload.get("repoIds") or [])
        result = await fit.fit_for(repo_ids)
        return {r: (_to_payload(v) if v is not None else None) for r, v in result.items()}

    registry.register("models.fit", models_fit)
```

En `server/ide_server/app.py`: agregar `from ide_server.capabilities import models_fit as models_fit_cap`
con las otras capabilities, y dentro de `create_app` (junto a los otros `*_cap.register`):

```python
    models_fit_cap.register(registry, root)
```

- [ ] **Step 4: Correr, verificar que pasan** → PASS. Suite completa (incl. `create_app`) → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/models_fit.py server/ide_server/app.py server/tests/test_models_fit_capability.py
git commit -m "feat(models): capability models.fit (serializa camelCase, null si sin dato) + wire en app"
```

---

### Task 3: Frontend — `fit` en el store + `fetchFit`

**Files:**
- Modify: `ui/src/state/models.ts`, `ui/src/transport/modelsChannel.ts`
- Test: `ui/src/state/models.test.ts` (agregar), `ui/src/transport/modelsChannel.test.ts` (agregar)

**Interfaces:**
- Produces: `FitInfo` (TS), `fit`/`setFit` en `useModels`; `fetchFit(ws, repoIds)`.

- [ ] **Step 1: Tests que fallan**

En `ui/src/state/models.test.ts` agregar:

```ts
it("setFit puebla el fit", () => {
  useModels.getState().setFit({ "a": { level: "ok", fitLabel: "Perfect", memoryRequiredGb: 6.7,
    memoryAvailableGb: 24, estimatedTps: 9.5, diskSizeGb: 5.8, bestQuant: "mlx-8bit",
    contextLength: 32768, score: 87, scoreComponents: { fit: 100, speed: 20, quality: 99, context: 100 } } });
  expect(useModels.getState().fit["a"]?.level).toBe("ok");
});
```
(el `beforeEach` del archivo resetea el store — agregarle `fit: {}` al `setState` de reset.)

En `ui/src/transport/modelsChannel.test.ts` agregar (importando `fetchFit`):

```ts
it("fetchFit pega a models.fit con repoIds", async () => {
  const ws = { request: vi.fn().mockResolvedValue({ a: null }) } as any;
  await fetchFit(ws, ["a", "b"]);
  expect(ws.request).toHaveBeenCalledWith("models.fit", { repoIds: ["a", "b"] });
});
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

En `ui/src/state/models.ts`: agregar la interfaz y el slice de `fit`:

```ts
export interface FitInfo {
  level: "ok" | "tight" | "no"; fitLabel: string;
  memoryRequiredGb: number; memoryAvailableGb: number; estimatedTps: number;
  diskSizeGb: number; bestQuant: string; contextLength: number;
  score: number; scoreComponents: { fit: number; speed: number; quality: number; context: number };
}
```
Agregar `fit: Record<string, FitInfo | null>;` y `setFit: (m: Record<string, FitInfo | null>) => void;`
a la interfaz `ModelsState`; en el `create(...)` inicializar `fit: {}` y agregar
`setFit: (m) => set((s) => ({ fit: { ...s.fit, ...m } })),`.

En `ui/src/transport/modelsChannel.ts` agregar:

```ts
import type { FitInfo } from "../state/models";

export function fetchFit(ws: WsClient, repoIds: string[]): Promise<Record<string, FitInfo | null>> {
  return ws.request("models.fit", { repoIds });
}
```

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd ui && npm test -- models modelsChannel` → PASS. `cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/state/models.ts ui/src/transport/modelsChannel.ts ui/src/state/models.test.ts ui/src/transport/modelsChannel.test.ts
git commit -m "feat(models): fit en el store + fetchFit en el transport"
```

---

### Task 4: Frontend — `FitBadge` + wire `ModelsPanel`

**Files:**
- Create: `ui/src/modules/settings/FitBadge.tsx`, `ui/src/modules/settings/FitBadge.test.tsx`
- Modify: `ui/src/modules/settings/ModelsPanel.tsx`, `ui/src/modules/settings/ModelsPanel.test.tsx`,
  `ui/src/modules/settings/SettingsModal.test.tsx`

- [ ] **Step 1: Tests que fallan**

`ui/src/modules/settings/FitBadge.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FitBadge } from "./FitBadge";

const FIT = { level: "ok" as const, fitLabel: "Perfect", memoryRequiredGb: 6.7, memoryAvailableGb: 24,
  estimatedTps: 9.5, diskSizeGb: 5.8, bestQuant: "mlx-8bit", contextLength: 32768, score: 87,
  scoreComponents: { fit: 100, speed: 20, quality: 99, context: 100 } };

describe("FitBadge", () => {
  it("muestra 'entra' + tok/s para level ok", () => {
    render(<FitBadge fit={FIT} />);
    expect(screen.getByText("entra")).toBeInTheDocument();
    expect(screen.getByText(/9\.5 tok\/s/)).toBeInTheDocument();
  });
  it("toggle detalles despliega las métricas", () => {
    render(<FitBadge fit={FIT} />);
    expect(screen.queryByText(/mlx-8bit/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("detalles", { selector: "[data-fit-details]" }));
    expect(screen.getByText(/mlx-8bit/)).toBeInTheDocument();
  });
  it("sin dato (null) no renderiza nada", () => {
    const { container } = render(<FitBadge fit={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

En `ui/src/modules/settings/ModelsPanel.test.tsx` y `SettingsModal.test.tsx`: agregar `fetchFit` al
`vi.mock("../../transport/modelsChannel", ...)` de AMBOS (si no, `ModelsPanel` llama `fetchFit` undefined
y rompe):

```tsx
  fetchFit: () => Promise.resolve({}),
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

`ui/src/modules/settings/FitBadge.tsx`:

```tsx
import { useState } from "react";
import type { FitInfo } from "../../state/models";

const LABEL: Record<string, string> = { ok: "entra", tight: "justo", no: "no entra" };

function levelProps(level: string): { className: string; style?: React.CSSProperties } {
  if (level === "no") return { className: "font-medium text-destructive" };
  if (level === "tight") return { className: "font-medium", style: { color: "#e0863f" } };
  return { className: "font-medium", style: { color: "#7fb069" } };
}

export function FitBadge({ fit }: { fit?: FitInfo | null }) {
  const [open, setOpen] = useState(false);
  if (!fit) return null;
  const lp = levelProps(fit.level);
  const sc = fit.scoreComponents;
  return (
    <div className="mt-1 text-[10px]">
      <div className="flex items-center gap-2">
        <span data-fit={fit.level} className={lp.className} style={lp.style}>{LABEL[fit.level]}</span>
        <span className="text-muted-foreground">{fit.estimatedTps} tok/s</span>
        <button data-fit-details onClick={() => setOpen((o) => !o)}
          className="text-muted-foreground hover:text-foreground">detalles</button>
      </div>
      {open && (
        <div data-fit-detail className="mt-1 flex flex-col gap-0.5 text-muted-foreground">
          <span>RAM: {fit.memoryRequiredGb} GB de {fit.memoryAvailableGb} GB</span>
          <span>Disco: {fit.diskSizeGb} GB · quant: {fit.bestQuant}</span>
          <span>Contexto: {fit.contextLength}</span>
          <span>Score {fit.score} — fit {sc.fit} · velocidad {sc.speed} · calidad {sc.quality} · contexto {sc.context}</span>
        </div>
      )}
    </div>
  );
}
```

En `ui/src/modules/settings/ModelsPanel.tsx`:
1. Importar: `import { FitBadge } from "./FitBadge";` y agregar `fetchFit` al import de `modelsChannel`
   (`import { fetchModels, downloadModel, deleteModel, subscribeModels, fetchFit } from "../../transport/modelsChannel";`).
2. En el componente, tomar `fit` y `setFit` del store: cambiar la desestructuración a
   `const { curated, installed, inUse, downloads, fit, setCatalog, setFit, applyEvent } = useModels();`.
3. En el `useEffect` de carga, tras el `reload()`, pedir el fit — reemplazar el cuerpo del efecto por:

```tsx
  useEffect(() => {
    const reload = () => fetchModels(getWs()).then((c) => {
      setCatalog(c);
      const ids = [...c.curated.map((m) => m.repoId), ...c.installed.map((m) => m.repoId)];
      fetchFit(getWs(), ids).then(setFit).catch(() => {});
    }).catch(() => {});
    reload();
    return subscribeModels(getWs(), (e) => { applyEvent(e); if (e.kind === "done") reload(); });
  }, [setCatalog, setFit, applyEvent]);
```

4. Renderizar el badge en la fila de catálogo: dentro del `<div data-curated ...>`, después del
   `{dl?.error && ...}` (última línea antes de cerrar el div de la fila), agregar:
   `<FitBadge fit={fit[m.repoId]} />`.
5. Renderizar el badge en la fila de instalados: la fila `data-installed` hoy es un flex de una línea;
   envolverla para poner el badge debajo. Reemplazar el bloque de la fila instalada por:

```tsx
              <div key={m.repoId} data-installed className="rounded border border-border px-2 py-1.5 text-xs">
                <div className="flex items-center justify-between">
                  <span>{m.repoId}<span className="text-muted-foreground"> · {gb(m.sizeOnDisk)} GB</span></span>
                  <div className="flex items-center gap-2">
                    {m.repoId === inUse && <Badge variant="secondary" className="bg-role-pill text-primary text-[10px]">en uso</Badge>}
                    <button data-delete={m.repoId} onClick={() => deleteModel(getWs(), m.repoId).then(reload)}
                      className="text-[10px] text-muted-foreground hover:text-destructive">Borrar</button>
                  </div>
                </div>
                <FitBadge fit={fit[m.repoId]} />
              </div>
```
   (el `reload` que usa el botón Borrar sigue siendo el `const reload` del scope del componente — mantenerlo.)

- [ ] **Step 2/4: Correr, verificar que pasan**

Run: `cd ui && npm test -- FitBadge ModelsPanel SettingsModal` → PASS. Suite completa `cd ui && npm test`
→ PASS. `cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/settings/FitBadge.tsx ui/src/modules/settings/FitBadge.test.tsx ui/src/modules/settings/ModelsPanel.tsx ui/src/modules/settings/ModelsPanel.test.tsx ui/src/modules/settings/SettingsModal.test.tsx
git commit -m "feat(models): badge de fit + detalles por modelo en el panel"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** `fit.py` parse+nivel+cache (T1), capability serialización (T2), store+transport
  (T3), badge+detalles+wire (T4). ✓
- **Consistencia:** `FitInfo` backend snake ↔ capability camelCase (`estimatedTps`, `memoryRequiredGb`,
  `scoreComponents`) ↔ `FitInfo` TS ↔ `FitBadge`. `models.fit {repoIds}` ↔ `fetchFit`. `null` ↔ sin badge.
- **Sin fallos silenciosos:** `llmfit` ausente/desconocido/JSON malo/timeout → `None` en `_run_llmfit`,
  nunca excepción; `None` = sin dato (no error tragado). `models.fit` real que falle → envelope.
- **Riesgo señalado (T4):** los mocks de `modelsChannel` en `ModelsPanel.test` y `SettingsModal.test`
  DEBEN ganar `fetchFit` o rompen. El glue de subprocess (`_run_llmfit`) se testea con `monkeypatch` del
  `subprocess.run`; nada de llmfit real corre en CI.
- **Verificación en vivo (fuera del plan):** con `llmfit` instalado, abrir el panel y ver badges reales.
```
