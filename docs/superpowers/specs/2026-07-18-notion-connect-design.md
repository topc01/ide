# Spec — Conectar Notion in-app

> Fecha: 2026-07-18. Mejora chica del módulo Notion (Fase 1 ya mergeada): configurar la
> conexión sin editar `~/.ide/config.toml` a mano.

## Objetivo

Eliminar la fricción de setup de Notion: hoy, sin token, el panel dice "conectá Notion" y
agregar una página falla con un mensaje que manda a editar TOML a mano. Con esto, el usuario
**pega su token de integración en la app** y queda conectado — la app valida y persiste el token
en su config global.

## Decisiones tomadas (brainstorming 2026-07-18)

1. **Config in-app, escribe el mismo archivo de siempre.** El token se guarda en
   `~/.ide/config.toml [notion].token` (global), preservando otras secciones. Sin cambiar la
   resolución existente (`notion_token`: env > local > global).
2. **Validar antes de persistir.** `notion.connect` valida el token provisto con `users.me`;
   si es inválido, **no** escribe nada.
3. **Alcance mínimo:** connect + disconnect + validación. Sin OAuth, sin rotación, sin
   múltiples tokens/workspaces.
4. **El usuario ingresa su propio secreto** en su propia herramienta local; input tipo password;
   viaja por WS localhost; se guarda plaintext local no-commiteado (igual que hoy).

## Arquitectura

Extiende el paquete `notion/` y la capability `notion` de la Fase 1.

### Backend

**Dep nueva:** `tomli-w` (escribir TOML; `tomllib` solo lee).

- `notion/config.py`:
  - `write_token(home: Path, token: str) -> None` — lee `home/.ide/config.toml` con `tomllib`
    (o `{}` si falta), `data.setdefault("notion", {})["token"] = token`, reescribe con
    `tomli_w.dumps` (crea `home/.ide/` si falta). Preserva todas las demás secciones.
  - `clear_token(home: Path) -> None` — carga el toml, quita `notion.token` (y la sección
    `[notion]` si queda vacía), reescribe. Si el archivo no existe, no-op.
- `capabilities/notion.py`:
  - `notion.connect {token}` → construye un cliente con **el token provisto** (`client_factory`
    inyectable, igual que hoy), `await users.me()` en try/except. Éxito → `write_token(home,
    token)` → `{connected: true}`. Falla (token inválido) → **no escribe** → `{connected:
    false}`. Token vacío → `{connected: false}` sin llamar a la API.
  - `notion.disconnect {}` → `clear_token(home)` → `{connected: false}`.
  - `register` ya recibe `home`; se reutiliza. `write_token`/`clear_token` operan sobre `home`.

Errores → envelope (sin fallos silenciosos). `connect` con token inválido no es error de
transporte: devuelve `{connected:false}` (el front muestra "token inválido"), consistente con
`health`.

### Frontend

- `transport/notionChannel.ts`: `connect(ws, token) -> Promise<boolean>` (→ `.connected`),
  `disconnect(ws) -> Promise<void>`.
- `state/notion.ts`: acciones `connect(token)` (llama `notion.connect`; si `connected` →
  `load()`; si no → setea `error: "token inválido"`) y `disconnect()` (llama `notion.disconnect`
  → `set({connected:false, pages:[]})`).
- `modules/notion/NotionPanel.tsx`:
  - Estado "conectá Notion" (`!connected && !error` o estado desconectado): **input de token**
    (`type="password"`, placeholder "Internal Integration Secret") + botón **"Conectar"**;
    link a `https://www.notion.so/my-integrations` (abre en pestaña nueva) y un mini-instructivo
    de 1-2 líneas ("Creá una integración interna, pegá su secret, y compartí tus páginas con la
    integración"). Enter o click → `connect(token)`.
  - Cuando `connected`: un botón/ícono **"Desconectar"** en el header (además de "+ Nueva" y
    refrescar) → `disconnect()`.

## Flujo de datos

Panel desconectado → usuario pega token → `connect` → `notion.connect {token}` → valida
`users.me` → `write_token` → `{connected:true}` → store `load()` → `notion.health` (ahora true)
+ `notion.list`. Desconectar → `notion.disconnect` → `clear_token` → estado desconectado.

## Manejo de errores

- Token inválido → `connect` devuelve `{connected:false}` → panel "token inválido, revisá el
  secret". No se persiste.
- Error de red al validar → envelope → panel muestra error.
- `write_token`/`clear_token` con IO error → excepción → envelope (no se pretende éxito falso).

## Plan de tests (TDD)

1. `notion/config.py`: `write_token` crea el archivo y setea `[notion].token`; preserva una
   sección previa (`[roles]`/`name`); `clear_token` lo quita y deja el resto; `clear_token`
   sobre archivo inexistente es no-op. (tmp_path.)
2. Capability `notion.connect`/`notion.disconnect`: token válido (fake client `users.me` OK) →
   escribe + `connected:true`; token inválido (fake raise) → **no** escribe + `connected:false`;
   token vacío → `connected:false` sin tocar la API; `disconnect` → limpia.
3. Frontend `notionChannel.connect/disconnect` (ws mock).
4. `state/notion` `connect`/`disconnect` (éxito → load; inválido → error).
5. `NotionPanel`: estado desconectado muestra input+Conectar; Enter/click llama `connect`;
   conectado muestra "Desconectar" → llama `disconnect`.

## Fuera de alcance

- OAuth / flujo de autorización de Notion.
- Rotación/expiración proactiva del token, múltiples tokens o workspaces.
- Editar el token local (`.ide/config.toml`) o el env — `connect`/`disconnect` operan solo
  sobre el global `~/.ide/config.toml`.

## Fidelidad de UI

Panel Notion fiel al mockup (231-251); ámbar `#e0863f` para acciones. Input y botón con el
idiom de los inputs existentes (NewSessionModal / el input de "+ por URL" de Fase 1).
