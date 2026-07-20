# Spec — Orquestación entre sesiones (meta-agente Fase 1)

> Fecha: 2026-07-19. Primera rebanada de comunicación agente-a-agente. Adapta el mecanismo
> `fide` de finnecto-ide (King orquesta hijos por repo vía un CLI/socket) a nuestro stack: al
> Claude Code de una sesión **coordinadora** se le monta un **SDK MCP server in-process** con
> tools para descubrir, comandar y crear sesiones hijas.

## Objetivo

Que la sesión coordinadora (sin branch, sin worktree) pueda, por sí misma, repartir tareas a sus
sesiones hijas y recibir sus respuestas — orquestación autónoma, base de un meta-agente. Hoy
existe el **modelo de datos** jerárquico (árbol `parentId`/`children[]`/`kind`) pero **ningún
canal** para que una sesión le hable a otra. Esta rebanada agrega ese canal.

## Decisiones tomadas (brainstorming 2026-07-19)

1. **Agente-a-agente autónomo.** El Claude Code coordinador orquesta solo (no es el humano
   relayando). Referencia: el `King` de `fide`.
2. **Request-reply bloqueante.** `ask_session(id, tarea)` bloquea (desde la óptica del agente) y
   devuelve la **respuesta final** de la hija como resultado de la tool. Referencia: `fide send`
   (que "espera la respuesta" por defecto, "anti fire-and-forget de los orquestadores").
3. **Fan-out en paralelo garantizado** vía `ask_sessions([...])` (`asyncio.gather`). El bloqueo
   es por-llamada; múltiples hijas en paralelo con una sola tool call determinística.
4. **Spawn incluido.** `spawn_session(repo, name, role?, branch?)` crea hijas on-demand
   (reusa la lógica de `sessions.create`). Referencia: `fide dev`.
5. **Mecanismo: SDK MCP tools in-process** (`create_sdk_mcp_server` + `@tool`, vía
   `ClaudeAgentOptions.mcp_servers`). Nativo al `ClaudeDriver`; sin CLI/socket/PATH.
6. **Hijas permisivas.** Las sesiones comandadas/spawneadas por el coordinador corren en
   `permission_mode="bypassPermissions"` (según su rol) y **no generan gates**. Orquestación
   fluida; el trade-off de seguridad se asume explícitamente (ver §Seguridad).
7. **La orquestación se ve como mensajes en ambos chats.** Cada `ask` emite eventos `RelayMessage`
   en el chat de la coordinadora (saliente + respuesta) y en el de la hija (entrante), con badge
   de origen/destino cruzado. Sin panel nuevo.

## Command surface (MCP server `orq`)

Cuatro tools, expuestas **solo** a sesiones coordinadoras (`kind != "work"`):

- `list_children()` → `[{sessionId, name, status, repoId}]` — las hijas de la coordinadora (mapea
  `fide status`).
- `ask_session(session_id, task)` → `str` (la respuesta final de la hija). Bloquea. (mapea
  `fide send`).
- `ask_sessions(requests)` donde `requests = [{session_id, task}]` → `[{session_id, reply}]` —
  fan-out con `asyncio.gather`.
- `spawn_session(repo, name, role?, branch?)` → `{sessionId, name}` — crea una hija de la
  coordinadora (worktree + branch + rol), la lanza permisiva, la devuelve lista para `ask`.
  (mapea `fide dev`).

Fuera de esta fase: `read` de pantalla (tenemos eventos estructurados), `answer_gate` (hijas
permisivas), `close_session`.

## Arquitectura

### Backend

**`chat/session_hub.py`** (nuevo) — `SessionHub`, dueño único del estado de drivers y de los
primitivos de orquestación. Reemplaza el dict `drivers` local del closure de la capability `chat`.

- `drivers: dict[str, ClaudeDriver]`, `locks: dict[str, asyncio.Lock]`.
- `register_driver(session_id, driver)` / `get(session_id)` / `has(session_id)`.
- `async ask(from_id, to_id, text) -> str`:
  1. emite `RelayMessage(peer=from, dir="in", text)` al canal de la hija `to_id` (entrante) y
     `RelayMessage(peer=to, dir="out", text)` al canal del coordinador `from_id` (saliente);
  2. bajo el **lock de `to_id`** (serializa con el `chat.send` del humano y con otros `ask`),
     llama `driver.send(text)` de la hija, que **devuelve el texto asistente acumulado**;
  3. emite `RelayMessage(peer=to, dir="in", text=reply)` al canal del coordinador (respuesta
     entrante) y devuelve `reply`.
- `list_children(coordinator_id) -> list[dict]` — lee el árbol (`load_sessions`), encuentra el
  nodo coordinador y devuelve sus `children` con `{sessionId, name, status, repoId}`.
- `async spawn(coordinator_id, repo, name, role, branch) -> dict` — misma lógica que
  `sessions.create` (worktree + branch + insert bajo `parentId=coordinator_id` + launcher);
  arranca la hija permisiva. Devuelve `{sessionId, name}`.

**`chat/events.py`** — nuevo evento `RelayMessage`:

```python
@dataclass
class RelayMessage:
    direction: str   # "in" | "out"
    peer: str        # nombre de la otra sesión
    peer_id: str
    text: str
```

`to_payload` agrega: `{"kind": "relay", "direction": ..., "peer": ..., "peerId": ..., "text": ...}`.

**`chat/driver.py`** — dos cambios:
- Acepta `mcp_servers: dict | None` en el constructor → `opts["mcp_servers"]` (y `allowed_tools`
  incluye las tools MCP `mcp__orq__*` cuando corresponde).
- `send(text)` **devuelve el texto asistente acumulado** (concatena los `TextDelta.text` hasta
  `Done`), además de emitir los eventos como hoy. `chat.send` ignora el retorno; `hub.ask` lo usa.
  (Cambio no-breaking: hoy `send` retorna `None` y nadie usa el retorno.)

**`chat/orchestration.py`** (nuevo) — `build_orq_server(hub, coordinator_id)`:
- Usa `create_sdk_mcp_server(name="orq", tools=[...])` con `@tool` para `list_children`,
  `ask_session`, `ask_sessions`, `spawn_session`, cada una delegando al `hub` (capturando
  `coordinator_id`).
- Devuelve el server (o `None` si no aplica). Las tool functions traducen errores a un payload
  `{content:[{type:"text", text:"error: ..."}], isError: True}` (sin fallos silenciosos: el
  agente ve el error como resultado de la tool).

**`capabilities/chat.py`** — `register` recibe/crea el `SessionHub` (una instancia por proceso,
compartida). En `start`:
- Determina si la sesión es coordinadora (`kind != "work"`; se lee del nodo del árbol).
- Si lo es: `mcp_servers = {"orq": build_orq_server(hub, sid)}` y se agregan `mcp__orq__*` a
  `allowed_tools`. Si no: como hoy.
- Registra el driver en el hub (`hub.register_driver(sid, driver)`).
- `send`/`interrupt` operan vía el hub (bajo lock de la sesión).

El `SessionHub` se construye en `app.py` y se inyecta a la capability `chat` (y tiene acceso a
`root`, al `manager` para broadcasts, y al `driver_factory`).

### Frontend

**`state/chat.ts`** — `Msg` gana un campo opcional `relay?: { direction: "in"|"out"; peer: string }`.
`applyEvent`: en `e.kind === "relay"`, empuja un `Msg` nuevo `{role: "user", text: e.text,
chips: [], relay: {direction: e.direction, peer: e.peer}}` (mensaje discreto, no toca el
streaming del agente).

**`main/ChatView.tsx`** — cuando un `Msg` tiene `relay`, se renderiza como burbuja con un badge:
`→ <peer>` si `dir==="out"`, `↳ de <peer>` / `← <peer>` si `dir==="in"`, en ámbar `#e0863f`.

**`transport/chatChannel.ts`** — el handler de `chat.event.{sid}` ya despacha por `kind`; el
nuevo `relay` fluye solo (no requiere cambio de transporte, solo el `applyEvent`).

## Flujo de datos (ask_session)

Coordinador razona "que la hija X compile" → llama `mcp__orq__ask_session(X, "compilá y reportá")`
→ tool delega en `hub.ask(coord, X, texto)` → hub emite relay entrante al chat de X (badge "↳ de
Coordinadora") y relay saliente al chat del coordinador (badge "→ X") → bajo lock de X,
`driverX.send(texto)` procesa (los `TextDelta`/`ToolUse` de X fluyen a `chat.event.{X}` como
siempre) y devuelve el texto final → hub emite relay entrante al coordinador (badge "← X: <texto>")
→ la tool devuelve el texto → el agente coordinador razona con la respuesta.

Fan-out: `ask_sessions([{A,taskA},{B,taskB}])` → `asyncio.gather(hub.ask(coord,A,..),
hub.ask(coord,B,..))` → ambas hijas en paralelo (locks distintos) → devuelve las dos respuestas.

## Concurrencia y seguridad

- **Lock por sesión** en el hub: el `chat.send` del humano y los `ask` del coordinador no se
  pisan sobre el mismo `ClaudeSDKClient`. Un `ask` a una hija ocupada espera su turno.
- **Hijas permisivas (trade-off asumido).** Las hijas del coordinador corren
  `bypassPermissions`: el meta-agente puede hacer que una hija tome acciones sensibles sin
  aprobación humana. Es una decisión de producto del dueño para su IDE local (equivalente al modo
  bypass del propio Claude Code), acotada a sesiones que el usuario creó/coordinó en worktrees.
  La aprobación de las tools del **propio coordinador** sigue el modo de su rol.
- Sin fallos silenciosos: errores del hub/tools viajan como resultado de tool con `isError` o
  como envelope; nunca se tragan.

## Plan de tests (TDD)

**Backend:**
1. `SessionHub.ask`: con driver fake que "responde" un texto, `ask` devuelve ese texto, serializa
   bajo lock (dos `ask` concurrentes a la misma sesión no se solapan), y emite los `RelayMessage`
   en ambos canales (fake manager captura broadcasts).
2. `SessionHub.list_children`: sobre árbol de prueba, devuelve las hijas del coordinador con sus
   campos; coordinador inexistente → `[]`.
3. `SessionHub.spawn`: crea worktree + inserta bajo el parent + lanza; devuelve `{sessionId,name}`
   (launcher fake).
4. `driver.send` devuelve el texto asistente acumulado (fake client que emite dos `TextDelta` +
   `Done`).
5. `events.RelayMessage` → `to_payload` shape.
6. `orchestration.build_orq_server`: expone las 4 tools; cada una delega al hub (hub fake);
   error del hub → resultado de tool con `isError`.
7. Capability `chat.start`: monta `mcp_servers={"orq":...}` + `mcp__orq__*` en allowed_tools solo
   si la sesión es coordinadora; registra el driver en el hub; sesión `work` no monta el server.

**Frontend:**
8. `state/chat` `applyEvent` con `kind:"relay"` empuja un `Msg` con `relay:{direction,peer}` sin
   romper el streaming del agente.
9. `ChatView` renderiza la burbuja relay con el badge correcto (`→ peer` / `← peer`).

## Fuera de alcance (deuda / fases siguientes)

- `answer_gate` / permisos por-hija con humano en el loop (elegimos hijas permisivas).
- `close_session` / lifecycle avanzado desde el coordinador.
- Panel/árbol de orquestación en vivo (esta fase reusa el stream de chat).
- Hijas escribiéndole espontáneamente al coordinador (buzón simétrico) — hoy el coordinador
  inicia; la hija responde dentro del `ask`.
- Streaming del texto de la hija hacia el coordinador token-a-token (el `ask` devuelve el texto
  completo al terminar; el chat de la hija sí streamea como siempre).
- Timeout/cancelación de un `ask` colgado (una hija que nunca termina bloquea esa tool call).

## Fidelidad de UI

Burbujas relay con el idiom del chat existente (`ChatView`), badge en ámbar `#e0863f`. Sin panel
nuevo; la orquestación vive en el stream de chat de ambas sesiones.
