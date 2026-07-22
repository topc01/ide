# Spec — Modelos locales: descargar y gestionar (Rebanada 2)

> Fecha: 2026-07-21. Segunda rebanada del subsistema de modelos locales (ver `docs/design/ROADMAP.md`).
> La Fase 1 (routing en el chat) ya está mergeada. Esta rebanada agrega el **panel "Modelos" en
> Settings** para **descargar y gestionar** modelos open-source. La UI de config editable (switch
> `enabled`, elegir modelo, editar el router prompt) queda para una rebanada posterior.

## Objetivo

Que el usuario pueda, desde la UI, **descargar** modelos mlx open-source (repos de HuggingFace),
**ver los instalados** (cache HF), **borrarlos**, y **ver cuál está en uso** por la config `[mlx]`.
La descarga muestra **progreso real (%/MB)** por WebSocket y admite **varias descargas concurrentes**.

Este es el primer panel de Settings con **acciones** (Settings sigue read-only para el resto del
catálogo de customizations). Todavía **no** escribe `config.toml` — configurar `[mlx]` sigue siendo a
mano hasta la rebanada de config editable. El "en uso" es lectura del toml.

## Decisiones tomadas (brainstorming 2026-07-21)

1. **Alcance = descargar/gestionar primero.** Tener modelos disponibles antes que la UI de switches.
2. **Catálogo = shortlist curado + `repo_id` libre.** Lista curada de modelos `mlx-community` buenos
   (un click para bajar) + un campo de texto para pegar cualquier `repo_id` de HF (avanzado).
3. **Progreso = barra real %/MB**, streaming por WebSocket (mismo patrón de eventos que chat/terminal).
4. **Descargas concurrentes + dedup.** Varias a la vez (cada una en su thread); no arrancar dos veces
   el mismo `repo_id`. Sin cap artificial (el cuello es la red). **Sin cancelación en v1** (interrumpir
   `snapshot_download` a mitad no es limpio; se difiere).
5. **In-process** (thread de fondo dentro del proceso FastAPI). Si el server reinicia, la descarga se
   corta — aceptable para v1.
6. **Descargar no es solo-Mac ni necesita `mlx-lm`.** Los modelos mlx son repos de HF; se bajan con
   `huggingface_hub` al cache de HF (`~/.cache/huggingface/hub`), compartido a nivel máquina. Correrlos
   sí necesita Mac+mlx (eso es la Fase 1). Dep nueva: `huggingface_hub` (runtime, pure-python, liviano).

## Arquitectura

### Backend — paquete `ide_server/models/`

- **`catalog.py`** — `CURATED_MODELS: list[CuratedModel]`, lista estática. `CuratedModel` (dataclass):
  `{repo_id: str, label: str, params: str, quant: str, size_gb: float}`. ~5-6 modelos a mano
  (p.ej. `mlx-community/Qwen2.5-3B-Instruct-4bit`, `...-7B-...`, `mlx-community/Llama-3.2-3B-Instruct-4bit`,
  etc.). Es data curada, no se consulta HF.

- **`store.py`** — inventario del cache HF:
  - `installed_models() -> list[InstalledModel]`: usa `huggingface_hub.scan_cache_dir()` para listar los
    repos bajados (filtrando `repo_type == "model"`), devolviendo `{repo_id, size_on_disk}`.
    `InstalledModel` (dataclass) `{repo_id: str, size_on_disk: int}`. Si el cache no existe → `[]`.
  - `delete_model(repo_id: str) -> None`: borra ese repo del cache (`scan_cache_dir().delete_revisions(...)
    .execute()`, o equivalente). `repo_id` no presente → no-op (idempotente).

- **`downloader.py`** — `ModelDownloader(manager: ConnectionManager)`:
  - Estado: `_active: dict[str, DownloadState]` (repo_id → progreso). `_loop` capturado en el primer
    `start` (`asyncio.get_running_loop()`) para hacer broadcast desde los worker threads.
  - `start(repo_id: str) -> None`: **dedup** — si `repo_id` ya está en `_active`, no-op. Si no, lo
    registra y lanza un thread daemon que corre `snapshot_download(repo_id, tqdm_class=<hook>)`. El hook
    (subclase de `tqdm`) reporta bytes descargados/total y, en cada update, agenda un broadcast del
    evento `progress` vía `run_coroutine_threadsafe(manager.broadcast("models.event", payload), self._loop)`.
    Al terminar el thread: emite `done` (o `error` si excepción) y saca el repo de `_active`.
  - `active() -> dict`: snapshot del progreso en curso (para que `models.list` incluya lo que está bajando).
  - Los hooks `snapshot_download`/`scan_cache_dir` se inyectan para tests (no se baja nada real).

- **`capabilities/models.py`** — `register(registry, root, manager, downloader=None)`:
  - `models.list {}` → `{"curated": [...], "installed": [...], "active": {...}, "inUse": <repo_id|null>}`.
    `inUse` se lee del `.ide/config.toml [mlx].model` (read-only; reusa la lectura de `mlx/config.py`
    o `tomllib` directo). Marca qué instalado está referenciado por la config.
  - `models.download {repoId}` → valida `repoId` no vacío, llama `downloader.start(repoId)`, devuelve
    `{"started": True}`. (El progreso llega por el canal de eventos, no por la respuesta.)
  - `models.delete {repoId}` → `delete_model(repoId)`, devuelve `{"deleted": True}`.
  - Cableado en `app.py`: `downloader = ModelDownloader(manager); models_cap.register(registry, root,
    manager, downloader=downloader)`.

- **Eventos** en canal `models.event` (payload lleva `repoId`, así que sirve para varias descargas a la
  vez): `{kind:"progress", repoId, downloaded, total}`, `{kind:"done", repoId}`,
  `{kind:"error", repoId, message}`.

- **Dep**: `huggingface_hub>=0.24` a `dependencies` (runtime) en `server/pyproject.toml`.

### Frontend

- **`transport/modelsChannel.ts`** — `subscribeModels(ws, onEvent)` sobre el canal `models.event`
  (`ws.on("models.event", onEvent)`), análogo a `chatChannel`/`terminalChannel`.
- **`state/models.ts`** — store (zustand, patrón de `state/chat.ts`):
  - `curated: CuratedModel[]`, `installed: InstalledModel[]`, `inUse: string | null`,
    `downloads: Record<repoId, { downloaded: number; total: number; error?: string; done?: boolean }>`.
  - `load()` (llama `models.list` y puebla), `applyEvent(e)` (progress/done/error actualizan `downloads`;
    en `done` refresca `installed`), `download(repoId)` / `remove(repoId)` (disparan las capabilities).
- **`modules/settings/ModelsPanel.tsx`** — el panel, enganchado al nav del `SettingsModal`:
  - **Catálogo**: filas del `CURATED_MODELS` (label, params, quant, tamaño) con botón *Descargar*
    (deshabilitado / con barra si está en `downloads`).
  - **Campo `repo_id` libre**: input + botón *Descargar*.
  - **Instalados**: filas con tamaño en disco, botón *Borrar*, badge **"en uso"** si `repo_id === inUse`.
  - **Barras de progreso** por descarga activa (%/MB), estilo 1a/shadcn (tokens ámbar).
- Wire en `SettingsModal.tsx`: agregar "Modelos" al nav izquierdo + montar el panel.

## Manejo de errores (sin fallos silenciosos)

- `repo_id` inválido / sin red / falla de `snapshot_download` → el thread captura la excepción y emite
  `{kind:"error", repoId, message}` → el panel muestra el error en esa fila. Nunca se traga.
- `models.download` con `repoId` vacío → la capability devuelve envelope de error (no arranca thread).
- `delete_model` de un repo inexistente → no-op (idempotente), `{"deleted": True}`.
- Si `huggingface_hub` no estuviera disponible en runtime (no debería, es dep): import lazy en la
  capability; el error de import viaja como envelope, no rompe el arranque del server.

## Config / persistencia

- **No escribe `config.toml`** en esta rebanada. Solo **lee** `[mlx].model` para el flag "en uso".
- Los modelos viven en el cache de HF (máquina-global). No hay store propio: "instalados" = escaneo del
  cache; "en curso" = estado en memoria del `ModelDownloader`.

## Plan de tests (TDD)

**Backend (fakes; nada se baja de verdad):**
1. `catalog`: `CURATED_MODELS` no vacío; cada item tiene los campos.
2. `store.installed_models`: con un `scan_cache_dir` fake → mapea a `InstalledModel`; cache vacío → `[]`.
   `delete_model`: llama al borrado del cache con el repo correcto; repo ausente → no-op.
3. `downloader`: con `snapshot_download` fake que invoca el `tqdm_class` → emite `progress`+`done` por el
   manager fake; **dedup** (segundo `start` del mismo repo mientras está activo → no re-lanza);
   dos repos distintos concurrentes → dos entradas en `_active`, eventos con `repoId` correcto;
   excepción en la descarga → emite `error` y saca el repo de `_active`.
4. `capabilities/models`: `list` (curado + instalados + `inUse` leído del toml); `download` (dispara
   `downloader.start`, valida vacío); `delete` (llama `delete_model`).

**Frontend:**
5. `state/models`: `applyEvent` progress/done/error actualiza `downloads`; `done` marca la fila.
6. `modelsChannel`: subscribe/emit sobre `models.event`.
7. `ModelsPanel`: renderiza catálogo + instalados; click en *Descargar* dispara `models.download`;
   una descarga activa muestra su barra; badge "en uso" en el instalado que matchea `inUse`.

**Verificación en vivo (fuera del plan, opcional):** con `huggingface_hub` instalado, bajar un modelo
chico real desde el panel y ver la barra avanzar hasta `done` + aparecer en instalados. (No requiere Mac.)

## Fuera de alcance (rebanadas siguientes)

- **Config editable**: escribir `[mlx]` desde la UI (toggle `enabled`, elegir modelo, editar el router
  prompt, elegir backend). Es la rebanada que sigue a esta.
- **Cancelar** una descarga en curso; pausar/reanudar.
- **Backends alternativos** (Ollama / LM Studio / Unsloth Studio vía `base_url` OpenAI) — va con la
  config editable.
- Búsqueda en vivo en HuggingFace; múltiples revisiones/quants de un mismo repo; verificación de que el
  modelo es realmente mlx-compatible antes de bajar.

## Fidelidad de UI

Panel con el idiom de shadcn tematizado a 1a — Terminal/amber. Barras de progreso, botones y filas con
los tokens ámbar (`docs/design/REFERENCES.md`). El nav de "Modelos" sigue el patrón del `SettingsModal`
existente. Badge "en uso" con el estilo de los chips/badges ya presentes.
