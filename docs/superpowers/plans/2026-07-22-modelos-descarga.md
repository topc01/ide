# Modelos locales: descargar y gestionar (Rebanada 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps
> usan checkbox (`- [ ]`).

**Goal:** Panel "Modelos" en Settings para descargar modelos mlx (repos de HF) con progreso real
%/MB, ver instalados, borrarlos, y ver cuál está en uso por `[mlx]`. Descargas concurrentes + dedup.

**Architecture:** Backend paquete `ide_server/models/` (catálogo estático, store del cache HF,
downloader async con progreso por WebSocket) + capability `models.*` cableada en `app.py`. Frontend
`state/models.ts` + `transport/modelsChannel.ts` + `modules/settings/ModelsPanel.tsx` montado en el
`SettingsModal`. Eventos en canal `models.event` (payload lleva `repoId` → sirve para varias a la vez).

**Tech Stack:** Python/FastAPI (+ `huggingface_hub` runtime), React/TS/vitest/zustand, shadcn/Tailwind.

## Global Constraints

- **Sin fallos silenciosos:** descarga que falla / `repo_id` inválido / sin red → evento
  `{kind:"error", repoId, message}`, nunca se traga. `models.download` con `repoId` vacío → `raise
  ValueError` (viaja como envelope `handler_error`; **no** `KeyError`, que el bus mapea a "unknown_channel").
- **Descargar NO es solo-Mac ni importa `mlx-lm`.** Usa `huggingface_hub` (import lazy dentro de las
  funciones, para que los tests con fakes no lo necesiten). Correr modelos = Fase 1 (aparte).
- **No escribe `config.toml`.** Solo lee `[mlx].model` para el flag "en uso" (read-only).
- **Descargas concurrentes + dedup:** varias a la vez; no arrancar dos veces el mismo `repo_id`.
- **Eventos keyed por `repoId`** en canal único `models.event`.
- **Fidelidad 1a/shadcn:** tokens ámbar (`bg-primary`, `bg-secondary`, `text-primary-foreground`, etc.),
  sin estética por defecto. Barras y badges con el idiom existente.
- **Commits atómicos, en español.** Un commit por tarea. Se trabaja en `main` directo (sin worktree).

---

### Task 1: `models/catalog.py`

**Files:**
- Create: `server/ide_server/models/__init__.py` (vacío), `server/ide_server/models/catalog.py`
- Test: `server/tests/test_models_catalog.py`

**Interfaces:**
- Produces: `CuratedModel` (dataclass `{repo_id, label, params, quant, size_gb}`),
  `CURATED_MODELS: list[CuratedModel]`.

- [ ] **Step 1: Test que falla** — `server/tests/test_models_catalog.py`:

```python
from ide_server.models.catalog import CURATED_MODELS, CuratedModel


def test_curated_non_empty_and_shaped():
    assert len(CURATED_MODELS) >= 3
    for m in CURATED_MODELS:
        assert isinstance(m, CuratedModel)
        assert m.repo_id and m.label and m.params and m.quant
        assert m.size_gb > 0
    # sin repos duplicados
    assert len({m.repo_id for m in CURATED_MODELS}) == len(CURATED_MODELS)
```

- [ ] **Step 2: Correr, verificar que falla** → FAIL (`No module named ...models`).

- [ ] **Step 3: Implementar** — `server/ide_server/models/__init__.py` (vacío) y
  `server/ide_server/models/catalog.py`:

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedModel:
    repo_id: str
    label: str
    params: str
    quant: str
    size_gb: float


CURATED_MODELS: list[CuratedModel] = [
    CuratedModel("mlx-community/Llama-3.2-1B-Instruct-4bit", "Llama 3.2 1B Instruct", "1B", "4bit", 0.7),
    CuratedModel("mlx-community/Qwen2.5-3B-Instruct-4bit", "Qwen2.5 3B Instruct", "3B", "4bit", 1.7),
    CuratedModel("mlx-community/Llama-3.2-3B-Instruct-4bit", "Llama 3.2 3B Instruct", "3B", "4bit", 1.8),
    CuratedModel("mlx-community/Phi-3.5-mini-instruct-4bit", "Phi-3.5 mini Instruct", "3.8B", "4bit", 2.2),
    CuratedModel("mlx-community/Mistral-7B-Instruct-v0.3-4bit", "Mistral 7B Instruct v0.3", "7B", "4bit", 4.1),
    CuratedModel("mlx-community/Qwen2.5-7B-Instruct-4bit", "Qwen2.5 7B Instruct", "7B", "4bit", 4.3),
]
```

- [ ] **Step 4: Correr, verificar que pasa** → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/models/__init__.py server/ide_server/models/catalog.py server/tests/test_models_catalog.py
git commit -m "feat(models): catálogo curado de modelos mlx"
```

---

### Task 2: `models/store.py` + dep `huggingface_hub`

**Files:**
- Create: `server/ide_server/models/store.py`
- Modify: `server/pyproject.toml` (dep runtime `huggingface_hub`)
- Test: `server/tests/test_models_store.py`

**Interfaces:**
- Produces: `InstalledModel` (dataclass `{repo_id, size_on_disk}`), `installed_models(scan=None) ->
  list[InstalledModel]`, `delete_model(repo_id, scan=None) -> None`. `scan` inyectable (default lee el
  cache HF vía `huggingface_hub.scan_cache_dir`).

- [ ] **Step 1: Tests que fallan** — `server/tests/test_models_store.py`:

```python
from ide_server.models.store import installed_models, delete_model, InstalledModel


class _Rev:
    def __init__(self, h): self.commit_hash = h


class _Repo:
    def __init__(self, repo_id, size, revs=(), repo_type="model"):
        self.repo_id = repo_id; self.size_on_disk = size
        self.repo_type = repo_type; self.revisions = [_Rev(r) for r in revs]


class _Info:
    def __init__(self, repos): self.repos = repos; self.deleted = None
    def delete_revisions(self, *hashes): self.deleted = hashes; return self
    def execute(self): return None


def test_installed_maps_and_filters_datasets():
    info = _Info([_Repo("mlx-community/A", 100),
                  _Repo("data/x", 5, repo_type="dataset")])
    assert installed_models(scan=lambda: info) == [InstalledModel("mlx-community/A", 100)]


def test_installed_empty_on_scan_error():
    def boom(): raise RuntimeError("no cache")
    assert installed_models(scan=boom) == []


def test_delete_calls_delete_revisions_for_repo():
    info = _Info([_Repo("mlx-community/A", 100, revs=["h1", "h2"])])
    delete_model("mlx-community/A", scan=lambda: info)
    assert set(info.deleted) == {"h1", "h2"}


def test_delete_absent_is_noop():
    info = _Info([_Repo("mlx-community/A", 100, revs=["h1"])])
    delete_model("mlx-community/Z", scan=lambda: info)
    assert info.deleted is None
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar** — `server/ide_server/models/store.py`:

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class InstalledModel:
    repo_id: str
    size_on_disk: int


def _scan_cache():
    from huggingface_hub import scan_cache_dir
    return scan_cache_dir()


def installed_models(scan=None) -> list[InstalledModel]:
    scan = scan or _scan_cache
    try:
        info = scan()
    except Exception:                                   # noqa: BLE001 — cache ausente = inventario vacío
        return []
    out: list[InstalledModel] = []
    for repo in info.repos:
        if getattr(repo, "repo_type", "model") == "model":
            out.append(InstalledModel(repo_id=repo.repo_id, size_on_disk=int(repo.size_on_disk)))
    return out


def delete_model(repo_id: str, scan=None) -> None:
    scan = scan or _scan_cache
    info = scan()
    hashes: list[str] = []
    for repo in info.repos:
        if repo.repo_id == repo_id:
            hashes.extend(rev.commit_hash for rev in repo.revisions)
    if not hashes:
        return
    info.delete_revisions(*hashes).execute()
```

En `server/pyproject.toml`, agregar `"huggingface_hub>=0.24",` a la lista `dependencies`.

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd server && uv sync` (por el cambio de dep) y `uv run pytest tests/test_models_store.py -q` → PASS.
Suite completa `cd server && uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/models/store.py server/pyproject.toml server/tests/test_models_store.py server/uv.lock
git commit -m "feat(models): inventario del cache HF (listar/borrar) + dep huggingface_hub"
```

---

### Task 3: `models/downloader.py`

**Files:**
- Create: `server/ide_server/models/downloader.py`
- Test: `server/tests/test_models_downloader.py`

**Interfaces:**
- Consumes: `ConnectionManager.broadcast(channel, payload)` (async).
- Produces: `DownloadState`, `ModelDownloader(manager, *, download_fn=None, poll_interval=0.5)` con
  `async start(repo_id) -> asyncio.Task | None` (dedup → `None` si ya activo), `active() -> dict`.
  `download_fn(repo_id, state)` muta `state.downloaded`/`state.total` (default: `snapshot_download`).

- [ ] **Step 1: Tests que fallan** — `server/tests/test_models_downloader.py`:

```python
import asyncio
import pytest
from ide_server.models.downloader import ModelDownloader


class FakeManager:
    def __init__(self): self.events = []
    async def broadcast(self, channel, payload): self.events.append((channel, payload))


@pytest.mark.asyncio
async def test_progress_then_done_and_cleanup():
    mgr = FakeManager()
    def dl(repo_id, state): state.downloaded = 100; state.total = 100
    d = ModelDownloader(mgr, download_fn=dl, poll_interval=0)
    await (await d.start("r1"))
    kinds = [p["kind"] for _, p in mgr.events]
    assert "progress" in kinds and kinds[-1] == "done"
    assert all(p["repoId"] == "r1" for _, p in mgr.events)
    assert all(ch == "models.event" for ch, _ in mgr.events)
    assert d.active() == {}


@pytest.mark.asyncio
async def test_error_emits_error_and_cleanup():
    mgr = FakeManager()
    def dl(repo_id, state): raise RuntimeError("boom")
    d = ModelDownloader(mgr, download_fn=dl, poll_interval=0)
    await (await d.start("r1"))
    assert any(p["kind"] == "error" and p["message"] == "boom" for _, p in mgr.events)
    assert d.active() == {}


@pytest.mark.asyncio
async def test_dedup_same_repo():
    mgr = FakeManager()
    started = {"n": 0}
    def dl(repo_id, state): started["n"] += 1
    d = ModelDownloader(mgr, download_fn=dl, poll_interval=0)
    t1 = await d.start("r1")
    t2 = await d.start("r1")                              # ya activo → dedup
    assert t2 is None
    await t1
    assert started["n"] == 1


@pytest.mark.asyncio
async def test_concurrent_two_repos():
    mgr = FakeManager()
    def dl(repo_id, state): state.downloaded = 1; state.total = 1
    d = ModelDownloader(mgr, download_fn=dl, poll_interval=0)
    t1 = await d.start("r1"); t2 = await d.start("r2")
    assert t2 is not None
    await asyncio.gather(t1, t2)
    assert {p["repoId"] for _, p in mgr.events} == {"r1", "r2"}
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar** — `server/ide_server/models/downloader.py`:

```python
from __future__ import annotations
import asyncio


class DownloadState:
    def __init__(self) -> None:
        self.downloaded = 0
        self.total = 0


def _default_download(repo_id: str, state: "DownloadState") -> None:
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm as _tqdm

    class _Reporter(_tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.total:
                state.total += self.total

        def update(self, n=1):
            if n:
                state.downloaded += n
            return super().update(n)

    snapshot_download(repo_id, tqdm_class=_Reporter)


class ModelDownloader:
    def __init__(self, manager, *, download_fn=None, poll_interval: float = 0.5) -> None:
        self._manager = manager
        self._download = download_fn or _default_download
        self._poll = poll_interval
        self._active: dict[str, DownloadState] = {}

    async def start(self, repo_id: str):
        if repo_id in self._active:                      # dedup (event loop single-thread → sin lock)
            return None
        state = DownloadState()
        self._active[repo_id] = state
        return asyncio.create_task(self._run(repo_id, state))

    async def _run(self, repo_id: str, state: DownloadState) -> None:
        # el download bloqueante corre en un thread; el pump async emite progreso
        # leyendo el estado compartido (asignación de ints = GIL-safe).
        worker = asyncio.create_task(asyncio.to_thread(self._download, repo_id, state))
        try:
            while True:
                await self._manager.broadcast("models.event", {
                    "kind": "progress", "repoId": repo_id,
                    "downloaded": state.downloaded, "total": state.total})
                done, _ = await asyncio.wait({worker}, timeout=self._poll)
                if done:
                    break
            worker.result()                              # re-lanza si la descarga falló
            await self._manager.broadcast("models.event", {"kind": "done", "repoId": repo_id})
        except Exception as e:                           # noqa: BLE001 — todo error viaja como evento
            await self._manager.broadcast("models.event",
                {"kind": "error", "repoId": repo_id, "message": str(e)})
        finally:
            self._active.pop(repo_id, None)

    def active(self) -> dict:
        return {r: {"downloaded": s.downloaded, "total": s.total} for r, s in self._active.items()}
```

- [ ] **Step 4: Correr, verificar que pasan** → PASS. Suite completa → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/models/downloader.py server/tests/test_models_downloader.py
git commit -m "feat(models): downloader async con progreso por WS, dedup y concurrencia"
```

---

### Task 4: `capabilities/models.py` + wire `app.py`

**Files:**
- Create: `server/ide_server/capabilities/models.py`
- Modify: `server/ide_server/app.py`
- Test: `server/tests/test_models_capability.py`

**Interfaces:**
- Consumes: `CURATED_MODELS` (T1), `installed_models`/`delete_model` (T2), `ModelDownloader` (T3).
- Produces: `register(registry, root, manager, downloader=None, installed=installed_models,
  remove=delete_model)` con handlers `models.list` / `models.download` / `models.delete`.

- [ ] **Step 1: Tests que fallan** — `server/tests/test_models_capability.py`:

```python
import pytest
from ide_server.plugins import Registry
import ide_server.capabilities.models as models_cap


class _FakeDownloader:
    def __init__(self): self.started = []
    async def start(self, repo_id): self.started.append(repo_id)
    def active(self): return {"r-en-curso": {"downloaded": 5, "total": 10}}


def _reg(tmp_path, downloader, installed=None, removed=None):
    reg = Registry()
    models_cap.register(reg, tmp_path, manager=None, downloader=downloader,
                        installed=(installed if installed is not None else (lambda: [])),
                        remove=(removed if removed is not None else (lambda r: None)))
    return reg


@pytest.mark.asyncio
async def test_list_curated_installed_active_inuse(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "config.toml").write_text('[mlx]\nmodel = "mlx-community/A"\n')
    from ide_server.models.store import InstalledModel
    reg = _reg(tmp_path, _FakeDownloader(),
               installed=lambda: [InstalledModel("mlx-community/A", 123)])
    out = await reg.dispatch("models.list", {})
    assert out["curated"] and out["curated"][0]["repoId"]
    assert out["installed"] == [{"repoId": "mlx-community/A", "sizeOnDisk": 123}]
    assert out["active"] == {"r-en-curso": {"downloaded": 5, "total": 10}}
    assert out["inUse"] == "mlx-community/A"


@pytest.mark.asyncio
async def test_list_inuse_none_without_config(tmp_path):
    reg = _reg(tmp_path, _FakeDownloader())
    out = await reg.dispatch("models.list", {})
    assert out["inUse"] is None


@pytest.mark.asyncio
async def test_download_calls_start(tmp_path):
    dl = _FakeDownloader()
    reg = _reg(tmp_path, dl)
    assert await reg.dispatch("models.download", {"repoId": "mlx-community/X"}) == {"started": True}
    assert dl.started == ["mlx-community/X"]


@pytest.mark.asyncio
async def test_download_empty_raises(tmp_path):
    reg = _reg(tmp_path, _FakeDownloader())
    with pytest.raises(ValueError):
        await reg.dispatch("models.download", {"repoId": "  "})


@pytest.mark.asyncio
async def test_delete_calls_remove(tmp_path):
    removed = []
    reg = _reg(tmp_path, _FakeDownloader(), removed=lambda r: removed.append(r))
    assert await reg.dispatch("models.delete", {"repoId": "mlx-community/A"}) == {"deleted": True}
    assert removed == ["mlx-community/A"]
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar** — `server/ide_server/capabilities/models.py`:

```python
from __future__ import annotations
import tomllib
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.models.catalog import CURATED_MODELS
from ide_server.models.store import installed_models, delete_model


def _in_use(root: Path) -> str | None:
    path = root / ".ide" / "config.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    mlx = data.get("mlx")
    if isinstance(mlx, dict) and mlx.get("model"):
        return str(mlx["model"])
    return None


def register(registry: Registry, root: Path, manager, downloader=None,
             installed=installed_models, remove=delete_model) -> None:
    async def list_(_payload: dict) -> dict:
        return {
            "curated": [{"repoId": m.repo_id, "label": m.label, "params": m.params,
                         "quant": m.quant, "sizeGb": m.size_gb} for m in CURATED_MODELS],
            "installed": [{"repoId": m.repo_id, "sizeOnDisk": m.size_on_disk} for m in installed()],
            "active": downloader.active() if downloader is not None else {},
            "inUse": _in_use(root),
        }

    async def download(payload: dict) -> dict:
        repo_id = (payload.get("repoId") or "").strip()
        if not repo_id:
            raise ValueError("repoId vacío")
        if downloader is not None:
            await downloader.start(repo_id)
        return {"started": True}

    async def delete(payload: dict) -> dict:
        repo_id = (payload.get("repoId") or "").strip()
        if repo_id:
            remove(repo_id)
        return {"deleted": True}

    for ch, fn in {"models.list": list_, "models.download": download,
                   "models.delete": delete}.items():
        registry.register(ch, fn)
```

En `server/ide_server/app.py`: importar y cablear (después del bloque de capabilities, junto a los otros
`*_cap.register`). Agregar el import con los demás (`from ide_server.capabilities import models as
models_cap`) y `from ide_server.models.downloader import ModelDownloader`, y en `create_app`:

```python
    downloader = ModelDownloader(manager)
    models_cap.register(registry, root, manager, downloader=downloader)
```

- [ ] **Step 4: Correr, verificar que pasan** → PASS. Suite completa (incl. tests que arman
  `create_app`) → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/capabilities/models.py server/ide_server/app.py server/tests/test_models_capability.py
git commit -m "feat(models): capability models.list/download/delete + wire en app"
```

---

### Task 5: Frontend — transport + state

**Files:**
- Create: `ui/src/transport/modelsChannel.ts`, `ui/src/state/models.ts`
- Test: `ui/src/transport/modelsChannel.test.ts`, `ui/src/state/models.test.ts`

**Interfaces:**
- Produces: `CuratedModel`, `InstalledModel`, `useModels` (store con `curated/installed/inUse/downloads`,
  `setCatalog`, `applyEvent`); `fetchModels`/`downloadModel`/`deleteModel`/`subscribeModels`.

- [ ] **Step 1: Tests que fallan**

`ui/src/state/models.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { useModels } from "./models";

beforeEach(() => useModels.setState({ curated: [], installed: [], inUse: null, downloads: {} }));

describe("useModels", () => {
  it("progress y done actualizan downloads", () => {
    const { applyEvent } = useModels.getState();
    applyEvent({ kind: "progress", repoId: "r1", downloaded: 50, total: 100 });
    expect(useModels.getState().downloads["r1"]).toEqual({ downloaded: 50, total: 100 });
    applyEvent({ kind: "done", repoId: "r1" });
    expect(useModels.getState().downloads["r1"].done).toBe(true);
  });
  it("error guarda el mensaje", () => {
    useModels.getState().applyEvent({ kind: "error", repoId: "r1", message: "boom" });
    expect(useModels.getState().downloads["r1"].error).toBe("boom");
  });
  it("setCatalog puebla curated/installed/inUse", () => {
    useModels.getState().setCatalog({
      curated: [{ repoId: "a", label: "A", params: "1B", quant: "4bit", sizeGb: 0.7 }],
      installed: [{ repoId: "a", sizeOnDisk: 100 }], inUse: "a", active: {},
    });
    const s = useModels.getState();
    expect(s.curated).toHaveLength(1); expect(s.inUse).toBe("a");
  });
});
```

`ui/src/transport/modelsChannel.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { fetchModels, downloadModel, deleteModel, subscribeModels } from "./modelsChannel";

describe("modelsChannel", () => {
  it("fetchModels pega a models.list", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ curated: [], installed: [], inUse: null, active: {} }) };
    const cat = await fetchModels(ws as any);
    expect(ws.request).toHaveBeenCalledWith("models.list", {});
    expect(cat.installed).toEqual([]);
  });
  it("downloadModel y deleteModel mandan el repoId", () => {
    const ws = { request: vi.fn().mockResolvedValue({}) } as any;
    downloadModel(ws, "r1"); deleteModel(ws, "r2");
    expect(ws.request).toHaveBeenCalledWith("models.download", { repoId: "r1" });
    expect(ws.request).toHaveBeenCalledWith("models.delete", { repoId: "r2" });
  });
  it("subscribeModels se suscribe y desuscribe de models.event", () => {
    const on = vi.fn(), off = vi.fn();
    const unsub = subscribeModels({ on, off } as any, () => {});
    expect(on).toHaveBeenCalledWith("models.event", expect.any(Function));
    unsub();
    expect(off).toHaveBeenCalledWith("models.event", expect.any(Function));
  });
});
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

`ui/src/state/models.ts`:

```ts
import { create } from "zustand";

export interface CuratedModel { repoId: string; label: string; params: string; quant: string; sizeGb: number; }
export interface InstalledModel { repoId: string; sizeOnDisk: number; }
export interface DownloadProgress { downloaded: number; total: number; error?: string; done?: boolean; }
export interface Catalog {
  curated: CuratedModel[]; installed: InstalledModel[];
  inUse: string | null; active: Record<string, { downloaded: number; total: number }>;
}

interface ModelsState {
  curated: CuratedModel[]; installed: InstalledModel[]; inUse: string | null;
  downloads: Record<string, DownloadProgress>;
  setCatalog: (c: Catalog) => void;
  applyEvent: (e: any) => void;
}

export const useModels = create<ModelsState>((set) => ({
  curated: [], installed: [], inUse: null, downloads: {},
  setCatalog: ({ curated, installed, inUse, active }) => set((s) => ({
    curated, installed, inUse,
    downloads: { ...Object.fromEntries(Object.entries(active).map(([r, p]) => [r, { ...p }])), ...s.downloads },
  })),
  applyEvent: (e) => set((s) => {
    const downloads = { ...s.downloads };
    const prev = downloads[e.repoId] ?? { downloaded: 0, total: 0 };
    if (e.kind === "progress") downloads[e.repoId] = { downloaded: e.downloaded, total: e.total };
    else if (e.kind === "done") downloads[e.repoId] = { ...prev, done: true };
    else if (e.kind === "error") downloads[e.repoId] = { ...prev, error: e.message };
    return { downloads };
  }),
}));
```

`ui/src/transport/modelsChannel.ts`:

```ts
import type { WsClient } from "./ws";
import type { Catalog } from "../state/models";

export function fetchModels(ws: WsClient): Promise<Catalog> {
  return ws.request("models.list", {});
}
export function downloadModel(ws: WsClient, repoId: string): Promise<any> {
  return ws.request("models.download", { repoId });
}
export function deleteModel(ws: WsClient, repoId: string): Promise<any> {
  return ws.request("models.delete", { repoId });
}
export function subscribeModels(ws: WsClient, onEvent: (e: any) => void): () => void {
  ws.on("models.event", onEvent);
  return () => ws.off("models.event", onEvent);
}
```

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd ui && npm test -- models` → PASS. `cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/transport/modelsChannel.ts ui/src/state/models.ts ui/src/transport/modelsChannel.test.ts ui/src/state/models.test.ts
git commit -m "feat(models): transport + store de modelos en el frontend"
```

---

### Task 6: Frontend — `ModelsPanel` + wire `SettingsModal`

**Files:**
- Create: `ui/src/modules/settings/ModelsPanel.tsx`, `ui/src/modules/settings/ModelsPanel.test.tsx`
- Modify: `ui/src/modules/settings/SettingsModal.tsx`, `ui/src/modules/settings/SettingsModal.test.tsx`

**Interfaces:**
- Consumes: `useModels` (T5), `fetchModels`/`downloadModel`/`deleteModel`/`subscribeModels` (T5),
  `getWs` (existente).

- [ ] **Step 1: Tests que fallan**

`ui/src/modules/settings/ModelsPanel.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useModels } from "../../state/models";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const downloadModel = vi.fn();
const deleteModel = vi.fn().mockResolvedValue({});
vi.mock("../../transport/modelsChannel", () => ({
  fetchModels: () => Promise.resolve({ curated: [], installed: [], inUse: null, active: {} }),
  subscribeModels: () => () => {},
  downloadModel: (...a: any[]) => downloadModel(...a),
  deleteModel: (...a: any[]) => deleteModel(...a),
}));
import { ModelsPanel } from "./ModelsPanel";

beforeEach(() => {
  downloadModel.mockClear();
  useModels.setState({
    curated: [{ repoId: "mlx-community/A", label: "Modelo A", params: "3B", quant: "4bit", sizeGb: 1.7 }],
    installed: [{ repoId: "mlx-community/B", sizeOnDisk: 2_000_000_000 }],
    inUse: "mlx-community/B", downloads: {},
  });
});

describe("ModelsPanel", () => {
  it("lista catálogo e instalados con badge en uso", () => {
    render(<ModelsPanel />);
    expect(screen.getByText("Modelo A")).toBeInTheDocument();
    expect(screen.getByText("mlx-community/B")).toBeInTheDocument();
    const row = screen.getByText("mlx-community/B").closest("[data-installed]") as HTMLElement;
    expect(row.textContent).toMatch(/en uso/i);
  });
  it("clickear Descargar dispara downloadModel con el repoId", () => {
    render(<ModelsPanel />);
    fireEvent.click(screen.getByText("Descargar", { selector: "[data-download]" }));
    expect(downloadModel).toHaveBeenCalledWith({}, "mlx-community/A");
  });
  it("una descarga activa muestra su porcentaje", () => {
    useModels.setState({ downloads: { "mlx-community/A": { downloaded: 50, total: 100 } } });
    render(<ModelsPanel />);
    expect(screen.getByText("50%")).toBeInTheDocument();
  });
});
```

En `ui/src/modules/settings/SettingsModal.test.tsx`, agregar al inicio (después de los imports) los mocks
para que montar el panel de Modelos no toque la red, y un test del nav:

```tsx
vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/modelsChannel", () => ({
  fetchModels: () => Promise.resolve({ curated: [], installed: [], inUse: null, active: {} }),
  subscribeModels: () => () => {}, downloadModel: vi.fn(), deleteModel: vi.fn(),
}));
```
y (importando `vi` en el `import` de vitest existente) un caso nuevo:

```tsx
  it("el nav tiene Modelos y al seleccionarlo muestra el panel", () => {
    render(<SettingsModal />);
    fireEvent.click(screen.getByRole("button", { name: /Modelos/i }));
    expect(useSettings.getState().selectedKey).toBe("models");
    expect(screen.getByText(/Descargar y gestionar/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Correr, verificar que fallan** → FAIL.

- [ ] **Step 3: Implementar**

`ui/src/modules/settings/ModelsPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useModels } from "../../state/models";
import { fetchModels, downloadModel, deleteModel, subscribeModels } from "../../transport/modelsChannel";
import { getWs } from "../../transport/wsClient";
import { Badge } from "../../components/ui/badge";

const pct = (d: number, t: number) => (t > 0 ? Math.min(100, Math.round((d / t) * 100)) : 0);
const gb = (bytes: number) => (bytes / 1e9).toFixed(1);

function RepoIdInput() {
  const [v, setV] = useState("");
  return (
    <div className="flex gap-1">
      <input value={v} onChange={(e) => setV(e.target.value)} placeholder="mlx-community/..."
        className="flex-1 rounded border border-border bg-transparent px-2 py-1 text-xs" />
      <button onClick={() => { const r = v.trim(); if (r) { downloadModel(getWs(), r); setV(""); } }}
        className="rounded bg-primary px-2 py-1 text-[10px] text-primary-foreground">Descargar</button>
    </div>
  );
}

export function ModelsPanel() {
  const { curated, installed, inUse, downloads, setCatalog, applyEvent } = useModels();
  useEffect(() => {
    const reload = () => fetchModels(getWs()).then(setCatalog).catch(() => {});
    reload();
    return subscribeModels(getWs(), (e) => { applyEvent(e); if (e.kind === "done") reload(); });
  }, [setCatalog, applyEvent]);
  const installedIds = new Set(installed.map((m) => m.repoId));
  const reload = () => fetchModels(getWs()).then(setCatalog).catch(() => {});
  return (
    <div className="flex flex-col gap-4">
      <section>
        <div className="mb-1 text-xs font-medium text-foreground">Catálogo</div>
        <div className="flex flex-col gap-1">
          {curated.map((m) => {
            const dl = downloads[m.repoId];
            const done = installedIds.has(m.repoId) || dl?.done;
            return (
              <div key={m.repoId} data-curated className="rounded border border-border px-2 py-1.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span>{m.label}<span className="text-muted-foreground"> · {m.params} · {m.quant} · {m.sizeGb} GB</span></span>
                  {done ? (
                    <span className="text-[10px] text-muted-foreground">instalado</span>
                  ) : (
                    <button data-download={m.repoId} disabled={!!dl && !dl.error}
                      onClick={() => downloadModel(getWs(), m.repoId)}
                      className="rounded bg-primary px-2 py-0.5 text-[10px] text-primary-foreground disabled:opacity-50">
                      {dl && !dl.error ? `${pct(dl.downloaded, dl.total)}%` : "Descargar"}
                    </button>
                  )}
                </div>
                {dl && !dl.done && !dl.error && (
                  <div className="mt-1 h-1 w-full rounded bg-secondary">
                    <div className="h-1 rounded bg-primary" style={{ width: `${pct(dl.downloaded, dl.total)}%` }} />
                  </div>
                )}
                {dl?.error && <div className="mt-1 text-[10px] text-destructive">{dl.error}</div>}
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <div className="mb-1 text-xs font-medium text-foreground">Descargar por repo_id</div>
        <RepoIdInput />
      </section>

      <section>
        <div className="mb-1 text-xs font-medium text-foreground">Instalados</div>
        {installed.length === 0 ? (
          <div className="text-xs text-muted-foreground">Ninguno.</div>
        ) : (
          <div className="flex flex-col gap-1">
            {installed.map((m) => (
              <div key={m.repoId} data-installed className="flex items-center justify-between rounded border border-border px-2 py-1.5 text-xs">
                <span>{m.repoId}<span className="text-muted-foreground"> · {gb(m.sizeOnDisk)} GB</span></span>
                <div className="flex items-center gap-2">
                  {m.repoId === inUse && <Badge variant="secondary" className="bg-role-pill text-primary text-[10px]">en uso</Badge>}
                  <button data-delete={m.repoId} onClick={() => deleteModel(getWs(), m.repoId).then(reload)}
                    className="text-[10px] text-muted-foreground hover:text-destructive">Borrar</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
```

En `ui/src/modules/settings/SettingsModal.tsx`: importar el panel y agregar el nav estático + render
condicional. Import: `import { ModelsPanel } from "./ModelsPanel";`. Calcular `const isModels =
selectedKey === "models";` dentro del componente. En el `<nav>`, después del `{items.map(...)}`, agregar:

```tsx
          <button onClick={() => openSettings("models")}
            className={cn("flex w-full items-center justify-between rounded px-2 py-1.5 text-xs",
              isModels ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>
            <span>Modelos</span>
          </button>
```

En el panel derecho, reemplazar `{item && (...)}` por un condicional que muestre el panel de Modelos:

```tsx
        <div className="min-w-0 flex-1 overflow-auto p-4">
          {isModels ? (
            <>
              <div className="text-base font-medium text-foreground">Modelos</div>
              <div className="mb-3 text-xs text-muted-foreground">Descargar y gestionar modelos locales</div>
              <ModelsPanel />
            </>
          ) : item && (
            <>
              {/* ...bloque existente del item genérico, sin cambios... */}
            </>
          )}
        </div>
```

(El bloque genérico existente —título, descripción, filas con badge "en uso"— se mantiene idéntico dentro
del `item && (...)`.)

- [ ] **Step 4: Correr, verificar que pasan**

Run: `cd ui && npm test -- ModelsPanel SettingsModal` → PASS. Suite completa `cd ui && npm test` → PASS.
`cd ui && npx tsc --noEmit` → limpio.

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/settings/ModelsPanel.tsx ui/src/modules/settings/ModelsPanel.test.tsx ui/src/modules/settings/SettingsModal.tsx ui/src/modules/settings/SettingsModal.test.tsx
git commit -m "feat(models): panel Modelos en Settings (catálogo, descarga con progreso, instalados)"
```

---

## Self-Review (autor del plan)

- **Cobertura del spec:** catálogo curado (T1), inventario cache HF + dep (T2), downloader concurrente
  con progreso/dedup (T3), capability list/download/delete + inUse read-only + wire (T4), transport+store
  (T5), panel + wire SettingsModal (T6). ✓
- **Consistencia de tipos:** `CuratedModel{repo_id,label,params,quant,size_gb}` (T1) → serializado a
  `{repoId,label,params,quant,sizeGb}` en la capability (T4) → `CuratedModel` camelCase en el front (T5).
  `InstalledModel{repo_id,size_on_disk}` → `{repoId,sizeOnDisk}`. Canal `models.event` con eventos
  `progress/done/error` (T3) ↔ `applyEvent` (T5). `ModelDownloader.start`/`active` (T3) ↔ capability (T4).
- **Sin fallos silenciosos:** error de descarga → evento `error`; `repoId` vacío → `ValueError` →
  envelope; `scan` que falla en `installed_models` = inventario vacío (caso legítimo, no error tragado).
- **Riesgos señalados:** el glue `_default_download` (tqdm + `snapshot_download`) es el único seam sin
  test unitario (se ejercita en la verificación en vivo); los tests inyectan `download_fn` fake. `tqdm`
  viene transitivo por `huggingface_hub`.
- **Verificación en vivo (fuera del plan):** con `huggingface_hub` ya instalado, bajar un modelo chico
  real desde el panel y ver la barra hasta `done` + aparecer en instalados (no requiere Mac).
```
