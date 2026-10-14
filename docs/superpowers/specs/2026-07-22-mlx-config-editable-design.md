# Spec — Config editable de mlx (Rebanada 3)

> Fecha: 2026-07-22. Tercera rebanada del subsistema de modelos locales. Las Fases 1 (routing) y 2
> (descargar/gestionar) ya están mergeadas. Esta rebanada hace **editable** la config `[mlx]` desde el
> panel "Modelos" — la **primera config editable de la app** (hoy Settings es read-only).

## Objetivo

Que el usuario configure mlx **desde la UI**, sin editar `.ide/config.toml` a mano: prender/apagar el
switch, elegir el modelo, y editar el prompt del router. Al guardar, el badge "en uso" del panel
(Rebanada 2) refleja el cambio.

## Decisiones (brainstorming 2026-07-22)

1. **Alcance = config editable de mlx.** Toggle `enabled`, elegir `model`, editar `router_prompt`.
   Backends alternativos (Ollama/LM Studio/Unsloth) = Rebanada 5 (tocan el orquestador).
2. **Por-proyecto**, coherente con la lectura: escribe `.ide/config.toml [mlx]` del workspace.
3. **Preserva el resto del archivo.** Read-modify-write con `tomllib` + `tomli-w` (patrón de
   `notion/config.py`): carga el doc entero, muta `[mlx]`, lo vuelve a escribir. No pisa otras secciones
   (roles, notion) ni otras claves de `[mlx]` (p.ej. `port`).
4. **Modelo = dropdown de instalados + texto libre** (input con `datalist` de los repos bajados; se
   puede tipear uno no instalado, mlx lo baja al arrancar el server).
5. **Router prompt** = `textarea` pre-cargado, con botón **restaurar default**. Si el prompt guardado
   iguala al default, no se persiste (queda el default del código; toml limpio).
6. **Sin fallos silenciosos:** `enabled=true` con `model` vacío → `raise ValueError` (envelope, no se
   guarda); si no, `mlx_config` devolvería `None` y mlx quedaría apagado en silencio. Error de escritura
   → envelope. El form muestra el error.

## Arquitectura

### Backend

- **`mlx/config.py`** (extender):
  - `mlx_config_raw(root: Path) -> dict`: valores **crudos** para poblar el form, aun con mlx apagado.
    Devuelve `{"enabled": bool, "model": str, "router_prompt": str, "default_prompt": str}` —
    `router_prompt` = el guardado o `DEFAULT_ROUTER_PROMPT`; `default_prompt` = `DEFAULT_ROUTER_PROMPT`
    siempre (para el botón "restaurar default"). Sin config/sección → `enabled=False, model="",
    router_prompt=default`.
  - `write_mlx_config(root, *, enabled: bool, model: str, router_prompt: str) -> None`: carga el toml
    (o `{}`), `mlx = data.setdefault("mlx", {})` (**merge**, preserva `port` etc.), setea
    `mlx["enabled"]=enabled` y `mlx["model"]=model`; si `router_prompt` != `DEFAULT_ROUTER_PROMPT` y no
    vacío → `mlx["router_prompt"]=router_prompt`, si es igual al default → `mlx.pop("router_prompt", None)`.
    Crea `.ide/` si falta. Escribe con `tomli_w.dumps`.

- **`capabilities/mlx_config.py`** (nuevo) — `register(registry, root)`:
  - `mlx.config.get {}` → `{enabled, model, routerPrompt, defaultPrompt}` (camelCase, desde `mlx_config_raw`).
  - `mlx.config.set {enabled, model, routerPrompt}` → valida (`enabled and not model.strip()` → `ValueError`),
    `write_mlx_config(...)`, devuelve `{saved: True}`.
  - Wire en `app.py`: `mlx_config_cap.register(registry, root)`.

### Frontend

- **`state/mlxConfig.ts`** (nuevo) — store zustand: `{enabled, model, routerPrompt, defaultPrompt, error}`
  + `setConfig(data)` (poblar desde `mlx.config.get`), `update(partial)` (editar campos), `setError`.
- **`transport/modelsChannel.ts`** (extender) — `getMlxConfig(ws)` → `mlx.config.get`;
  `setMlxConfig(ws, {enabled, model, routerPrompt})` → `mlx.config.set`.
- **`modules/settings/ModelsPanel.tsx`** (extender) — sección **"Configuración"** arriba del catálogo:
  - Toggle `enabled` (checkbox tematizado).
  - Input de `model` con `<datalist>` de los `installed` repoIds.
  - `<textarea>` del `routerPrompt` + botón **"restaurar default"** (setea `routerPrompt = defaultPrompt`).
  - Botón **Guardar** → `setMlxConfig(...)` y, en éxito, `reload()` del catálogo (actualiza "en uso");
    en error, muestra el mensaje (sin fallo silencioso).
  - Carga la config en el mount (`getMlxConfig`).

## Manejo de errores (sin fallos silenciosos)

- `enabled` sin `model` → `ValueError` → envelope → el form muestra "elige un modelo para prender mlx".
- Error de escritura del toml → envelope → el form muestra el error.
- `mlx.config.get` sobre un toml malformado → `mlx_config_raw` devuelve defaults (form usable), no rompe.

## Plan de tests (TDD)

**Backend:**
1. `mlx_config_raw`: sin config → defaults (`enabled=False, model="", router_prompt=default`);
   con `[mlx]` → valores; `default_prompt` siempre presente.
2. `write_mlx_config`: escribe `[mlx]` y **preserva otras secciones** (roles/notion) y `[mlx].port`;
   round-trip con `mlx_config`/`mlx_config_raw`; `router_prompt`==default → no se persiste la clave.
3. Capability `mlx.config.get`/`set`: get devuelve camelCase; set escribe y valida (`enabled` sin
   `model` → `ValueError`); set con model → `{saved: True}` y re-lectura lo confirma.

**Frontend:**
4. `state/mlxConfig`: `setConfig` puebla; `update` muta un campo; `setError`.
5. `transport`: `getMlxConfig`/`setMlxConfig` pegan a los canales correctos con el payload correcto.
6. `ModelsPanel` config section: renderiza toggle/model/textarea; "restaurar default" setea el prompt al
   default; Guardar llama `setMlxConfig` con los valores; datalist lista los instalados.

**Verificación en vivo (fuera del plan):** prender mlx desde el panel eligiendo un modelo instalado,
guardar, y ver el badge "en uso" aparecer + `[mlx]` escrito en el toml.

## Fuera de alcance (rebanadas siguientes)

- **Backends alternativos** (Ollama/LM Studio/Unsloth vía `base_url`) — Rebanada 5.
- **Fit del hardware** (llmfit) — Rebanada 4.
- Editar otras configs (roles/skills/MCP) desde la app — tema mayor aparte.

## Fidelidad de UI

Sección "Configuración" con el idiom shadcn/1a: toggle, input, textarea y botones con los tokens ámbar.
Coherente con el resto del `ModelsPanel`.
