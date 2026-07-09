# R0 — Fundación · Design

Fecha: 2026-07-07 · Estado: **en revisión** · Rebanada: R0 del `docs/design/ROADMAP.md`.

## Objetivo

Levantar el **esqueleto de la aplicación** sobre el que cuelgan las rebanadas R1–R6:
un backend FastAPI con WebSocket, un frontend React con el **layout de 3 regiones** y el
**theming 1a**, una **arquitectura de estado** clara, y un **sistema de plugins** que
convierte los 6 módulos del rail en slots extensibles. Para probar que todo el circuito
funciona de punta a punta, R0 incluye **un "esqueleto que camina"**: listar los repos
reales de un directorio y renderizarlos en el sidebar.

R0 **no** implementa ninguna funcionalidad de módulo completa (eso es R1–R6). Establece el
contrato, el estilo y el listón de calidad de la UI.

## Alcance

**Dentro:**
- **Comando `ide`**: entry-point que hace *walk-up* hasta el `.ide/` del workspace (o
  `ide init` para crearlo), levanta el backend apuntado a ese workspace y abre el navegador.
- Backend FastAPI: config (lee `.ide/config.toml`), servidor HTTP+WebSocket, bus de mensajes,
  registro de plugins, una capacidad real (`repos.list`), endpoint de health.
- Frontend React+Vite+TS: shell de 3 regiones, theming 1a (CSS variables), store global,
  cliente WebSocket + REST, registro de módulos (plugins) con los 6 slots, pestaña Chat
  fija (placeholder).
- Esqueleto que camina: `repos.list` del backend → render en el sidebar.
- Tests: pytest (backend) + vitest/RTL (frontend).

**Fuera (rebanadas posteriores):** árbol de sesiones real, PTY, chat con Claude,
diffs, graphite, tasks, notion, settings, worktrees, DB/docker/puertos.

---

## Arquitectura

```
Comando `ide`  →  walk-up hasta <workspace>/.ide/  →  levanta backend + abre navegador

Navegador (localhost:5173, Vite dev)
  │  REST (lecturas simples)  +  WebSocket (eventos/streams)
  ▼
FastAPI (localhost:8787)  — apuntado al workspace detectado
  ├─ cli         `ide` / `ide init`: detección del workspace (walk-up) y arranque
  ├─ app         wiring, CORS, monta REST + WS
  ├─ config      lee <workspace>/.ide/config.toml (nombre, settings)
  ├─ workspace   raíz detectada; descubre los repos que contiene
  ├─ bus         ConnectionManager (WS) + envelope de mensajes
  ├─ plugins     registro de capacidades por nombre  ("repos.list", …)
  └─ capabilities/
        repos    capacidad real: listar repos git del workspace + branch actual
```

**Workspace**: la unidad de trabajo es un directorio que contiene el `.ide/` (y los repos).
El comando `ide` lo detecta por walk-up; `ide init` crea el `.ide/`. Config, repos y (a
futuro) sesiones son relativos a ese workspace.

Dos vías de comunicación, con roles distintos:
- **REST** para lecturas puntuales sin estado (health, `repos.list` inicial).
- **WebSocket** para todo lo que sea streaming o push (en R0: reemitir eventos; la vía
  se ejerce con un `repos.changed` ping para validar el canal). En R2/R3 lleva PTY y chat.

### Envelope de mensajes (WebSocket)

Un único sobre JSON, versionado, para no reinventarlo por módulo:

```json
{ "type": "req|res|event|error", "id": "uuid", "channel": "repos.list", "payload": { } }
```

- `req`/`res`: petición-respuesta correlacionadas por `id`.
- `event`: push del servidor (sin `id` de correlación).
- `error`: `payload = { code, message }`. **Nunca** se falla en silencio.

---

## Componentes (unidades aisladas)

Cada unidad tiene un propósito, una interfaz y dependencias explícitas. Deben poder
entenderse y testearse por separado.

### Backend

| Unidad | Qué hace | Depende de |
|--------|----------|------------|
| `cli.py` | Comando `ide` / `ide init`: walk-up hasta `<workspace>/.ide/`, arranca el backend apuntado al workspace y abre el navegador. `init` crea el `.ide/` con `config.toml` mínimo. | config, workspace |
| `workspace.py` | Resuelve la raíz del workspace (dir que contiene `.ide/`) y descubre los repos git adentro. | — |
| `config.py` | Settings (pydantic-settings): lee `<workspace>/.ide/config.toml` (nombre) + `host`, `port`, `cors_origins` de env/`.env`. | workspace |
| `bus.py` | `ConnectionManager`: acepta WS, trackea conexiones, `broadcast(event)`, rutea `req`→handler→`res`. Define el envelope. | plugins |
| `plugins.py` | `Registry`: `register(channel, handler)`, `dispatch(channel, payload)`. Un plugin = un handler async por `channel`. Base para R1–R6. | — |
| `capabilities/repos.py` | Capacidad `repos.list`: descubre los repos git del workspace y su branch actual (via `git`). Registrado como plugin. | workspace |
| `app.py` | Crea FastAPI, CORS, registra capacidades, monta `GET /health`, `GET /api/repos`, `WS /ws`. | todos |

### Frontend

| Unidad | Qué hace | Depende de |
|--------|----------|------------|
| `theme/tokens.ts` + `theme.css` | Tokens 1a como CSS variables (`--accent`, `--panel-bg`, …). Fuente única de color/tipografía/spacing. | — |
| `transport/ws.ts` + `rest.ts` | Cliente WS (conecta, reconecta con backoff, correlaciona `req`/`res` por `id`, expone `on(channel)`) + fetch REST tipado. Tipos del envelope. | — |
| `state/store.ts` | Store global (Zustand): `repos[]`, `activePanel`, `openTabs[]`, `activeTabId`. Sin lógica de red adentro. | — |
| `modules/registry.tsx` | Interfaz `ActivityModule { id, icon, title, Panel }` + registro. Los 6 módulos se registran acá (5 stubs + repos mínimo). Base para R1–R6. | — |
| `layout/*` | `Sidebar`, `ActivityRail`, `ContextPanel`, `MainPanel`, `TabStrip` — estructura de 3 regiones, sin lógica de dominio. | state, modules, theme |
| `App.tsx` | Composición: monta layout, conecta transport, hidrata `repos` al iniciar. | todos |

### Interfaz de plugin (el punto de extensibilidad)

**Backend** — un plugin registra capacidades:
```python
def register(registry: Registry) -> None:
    registry.register("repos.list", handle_repos_list)
```
**Frontend** — un plugin registra un módulo del rail:
```ts
registerModule({ id: "changes", icon: FileDiff, title: "Changed files", Panel: ChangesPanel })
```
Agregar un módulo (o un meta-agente futuro) = un `register` de cada lado. Nada más toca.

---

## Flujo de datos — esqueleto que camina

1. Frontend arranca → `App` abre WS y hace `GET /api/repos`.
2. Backend `repos.list` descubre los repos del workspace, devuelve `[{ id, name, branch }]`.
3. Store guarda `repos`; el `Sidebar` los renderiza (nombre + chip de branch, estilo 1a).
4. (Validación del canal WS) Backend emite un `event repos.changed` de prueba; el cliente
   lo recibe y loguea — confirma que el WebSocket bidireccional funciona.

Esto prueba: config → capacidad → plugin → REST → transport → store → render → theming, y
el canal WS. Todo el circuito, sin implementar ningún módulo real.

---

## Manejo de errores

- **Backend**: cada handler puede lanzar; el bus/REST lo convierte en `error`
  (`{code, message}`), nunca en un 500 opaco ni en silencio. Workspace sin `.ide/` → el
  comando `ide` sugiere `ide init` (no arranca mudo); un workspace sin repos → lista vacía
  *explícita*, no un error confuso.
- **Frontend**: el cliente WS reconecta con backoff; mientras está caído, la UI muestra
  estado "desconectado" (no datos viejos como si fueran vivos). Errores de capacidad se
  renderizan, no se tragan.

## Testing

- **Backend (pytest)**: `repos.list` sobre un dir temporal con 2 repos git (fixture) →
  devuelve ambos con su branch; sobre dir inexistente → error tipado. Registro de plugins:
  `register`/`dispatch` de un canal dummy.
- **Frontend (vitest + RTL)**: el layout de 3 regiones renderiza; las CSS variables 1a
  están aplicadas (accent = `#e0863f`); el `Sidebar` renderiza repos desde un store
  mockeado; el cliente de transport correlaciona `req`/`res` por `id`.

## Criterios de aceptación (R0 hecho)

1. `ide` detecta el workspace por walk-up (o `ide init` lo crea), levanta el backend y abre
   el navegador; `GET /health` responde OK.
2. `vite` levanta el frontend; se ve el **layout de 3 regiones con estética 1a**.
3. Los **repos reales** del workspace aparecen en el sidebar (esqueleto que camina).
4. El canal WebSocket está probado (evento de ida y vuelta).
5. Existen los **6 slots de módulo** en el rail (5 stubs) y la pestaña **Chat** fija.
6. Los tests de backend y frontend pasan.
7. Agregar un módulo nuevo es demostrablemente un `register` de cada lado.

## Decisiones y alternativas

- **Zustand** sobre Redux/Context puro: store simple, sin boilerplate, testeable fuera de
  React. (Alt: Redux — demasiada ceremonia para esta etapa.)
- **Envelope único** sobre endpoints REST por módulo: un solo contrato para todos los
  canales, y el mismo sobre sirve para WS. (Alt: REST por recurso — se multiplican
  contratos y no cubre streaming.)
- **Vite dev separado del backend** (5173 ↔ 8787, con CORS) en desarrollo; en una rebanada
  futura se puede servir el build estático desde FastAPI para un solo puerto.

## Fuera de alcance explícito

Worktrees, sesiones reales, PTY, chat con Claude, diffs, graphite, tasks, notion, settings,
DB/docker/puertos. Cada uno es una rebanada posterior con su propio spec.
