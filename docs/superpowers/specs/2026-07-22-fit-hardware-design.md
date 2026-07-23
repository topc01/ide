# Spec — Fit del hardware (llmfit), Rebanada 4

> Fecha: 2026-07-22. Cuarta rebanada del subsistema de modelos locales. Agrega al panel "Modelos" un
> indicador de si cada modelo **entra en el hardware de esta máquina** (antes de bajarlo) + una vista de
> **detalles** (tok/s estimados y otras métricas), vía la CLI externa **`llmfit`**.

## Objetivo

Por modelo del panel (catálogo + instalados), un **badge de fit** — *entra / justo / no entra* — y una
**vista de detalles**: tok/s estimados, RAM requerida vs disponible, tamaño en disco, mejor quant,
context length, y el score desglosado (fit / velocidad / calidad / contexto). Se calcula **sin bajar el
modelo**, con `llmfit`. Si `llmfit` no está instalado → sin badges (degrada, nunca rompe).

## Contrato de `llmfit` (verificado en spike, 2026-07-22)

- `llmfit info "<repo_id>" --json` **entiende nuestros `repo_id` de HF directo** (p.ej.
  `mlx-community/Qwen2.5-7B-Instruct-4bit`). Salida: `{"models": [ {…} ]}`.
- Campos usados: `fit_label` (str, p.ej. "Perfect"/"Too Tight"), `memory_required_gb`,
  `memory_available_gb`, `estimated_tps`, `disk_size_gb`, `best_quant`, `context_length`, `score`,
  `score_components` `{fit, speed, quality, context}`.
- `repo_id` desconocido → salida **no-JSON**, exit 0. `llmfit` ausente → el spawn falla (FileNotFoundError).
  Ambos → tratamos como **sin dato** (`None`), sin badge.
- Detecta Apple Silicon/MLX (memoria unificada). Es CLI (Rust, o `pip install llmfit`); **dep opcional
  externa**, no la bundleamos.

## Decisiones

1. **Nivel de fit derivado de la memoria** (robusto y explicable), no del string de llmfit:
   `req/avail <= 0.75` → **entra** (verde); `0.75 < req/avail <= 1.0` → **justo** (ámbar);
   `> 1.0` → **no entra** (rojo). Igual guardamos `fit_label` de llmfit para mostrarlo como texto.
2. **tok/s siempre visible** junto al badge; el resto de métricas en un **detalle expandible** por fila.
3. **Batch + concurrente + cache:** el panel pide `models.fit {repoIds:[...]}` una vez tras cargar el
   catálogo; el backend corre `llmfit` concurrente (thread pool) y **cachea por repo_id** (el fit es
   estable por máquina).
4. **Dep opcional:** `llmfit` no está en el PATH → todos `None` → panel sin badges (quizás un hint sutil
   "instalá llmfit para ver el fit"). Nunca tumba el panel.
5. **Archivos nuevos en backend** (`models/fit.py`, `capabilities/models_fit.py`) — no re-editar los
   `mlx/*.py` que el dueño está puliendo con type hints.

## Arquitectura

### Backend

- **`models/fit.py`** (nuevo):
  - `FitInfo` (dataclass): `{repo_id, level ("ok"|"tight"|"no"), fit_label, memory_required_gb,
    memory_available_gb, estimated_tps, disk_size_gb, best_quant, context_length, score,
    score_components: dict}`.
  - `_llmfit(repo_id) -> dict | None`: `subprocess.run(["llmfit","info",repo_id,"--json"], capture,
    timeout)`; parsea JSON y devuelve `models[0]`; `FileNotFoundError` (llmfit ausente) / `JSONDecodeError`
    / sin `models` / timeout → `None`.
  - `class ModelFit(run=_llmfit)`: cache `dict[str, FitInfo|None]`; `async fit_for(repo_ids) -> dict[str,
    FitInfo|None]` corre los no-cacheados concurrente (`asyncio.gather` sobre `asyncio.to_thread(run,id)`),
    mapea el dict crudo → `FitInfo` (deriva `level` de la razón de memoria), cachea, devuelve el mapa.
  - Helper puro `level_from(required, available) -> str` (testeable).

- **`capabilities/models_fit.py`** (nuevo) — `register(registry, root, fit=None)` (default `ModelFit()`):
  - `models.fit {repoIds: [str]}` → `{repoId: FitInfoDict | null}` (serializa `FitInfo` a camelCase:
    `{level, fitLabel, memoryRequiredGb, memoryAvailableGb, estimatedTps, diskSizeGb, bestQuant,
    contextLength, score, scoreComponents}`; `null` para los sin dato).
  - Wire en `app.py`: `models_fit_cap.register(registry, root)`.

### Frontend

- **`state/models.ts`** (extender): `fit: Record<string, FitInfo | null>` + `setFit(map)`. `FitInfo` TS
  con los campos camelCase de arriba.
- **`transport/modelsChannel.ts`** (extender): `fetchFit(ws, repoIds) -> Record<string, FitInfo|null>`
  (`ws.request("models.fit", {repoIds})`).
- **`ModelsPanel.tsx`** (extender): tras cargar el catálogo, `fetchFit([...curated, ...installed ids])` →
  `setFit`. Por fila (catálogo + instalados): **badge de fit** (verde "entra" / ámbar "justo" / rojo "no
  entra") + **tok/s** al lado; y un toggle **"detalles"** que despliega RAM req/disponible, disco,
  mejor quant, context length, y el score desglosado. Sin dato → sin badge.

## Manejo de errores (sin fallos silenciosos)

- `llmfit` ausente / repo desconocido / JSON malformado / timeout → `None` (sin badge), nunca excepción
  que tumbe `models.fit`. Un `None` en el mapa es "sin dato", no un error tragado.
- Si `models.fit` fallara de verdad (bug), viaja como envelope (bus) y el panel no muestra badges.

## Plan de tests (TDD)

**Backend (fakes; no se corre llmfit real):**
1. `level_from`: <=0.75 → "ok"; 0.75–1.0 → "tight"; >1.0 → "no".
2. `ModelFit.fit_for`: con `run` fake que devuelve el dict crudo → arma `FitInfo` con `level` correcto;
   `run` que devuelve `None` (desconocido/ausente) → `None` en el mapa; cache (segundo `fit_for` del
   mismo id no re-llama `run`); dos ids concurrentes.
3. `_llmfit` parseo: JSON válido → `models[0]`; salida no-JSON → `None`; `FileNotFoundError` → `None`
   (con un `run_subprocess` inyectable).
4. Capability `models.fit`: serializa camelCase; `None` → `null` en el payload.

**Frontend:**
5. `state/models`: `setFit` puebla `fit`.
6. `transport`: `fetchFit` pega a `models.fit` con `{repoIds}`.
7. `ModelsPanel`: una fila con fit "ok" muestra badge "entra" + tok/s; toggle "detalles" despliega las
   métricas; fila sin dato (`null`) no muestra badge.

**Verificación en vivo (fuera del plan):** con `llmfit` instalado (ya está), abrir el panel y ver los
badges reales + detalles de los modelos del catálogo.

## Fuera de alcance (siguientes)

- Recomendaciones ("qué modelo te conviene") con `llmfit recommend`; comparación lado-a-lado (`diff`);
  planificar upgrades de hardware (`plan`). Esta rebanada es solo el fit + detalles por modelo del panel.
- Backends alternativos (Rebanada 5).

## Fidelidad de UI

Badges con el idiom de chips/badges existentes: verde `#7fb069` (entra), ámbar `#e0863f` (justo), rojo
`text-destructive` (no entra). Detalles con los tokens del panel (mismo estilo que las filas). Sin hex
arbitrario fuera de los verdes/ámbar ya usados en el proyecto.
