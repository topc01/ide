# Spec — Modelos locales (mlx) + routing en el chat, Fase 1 (fundación)

> Fecha: 2026-07-21. Primera rebanada del subsistema de modelos locales (ver `docs/design/ROADMAP.md`).
> Objetivo: que un modelo mlx local corriendo pueda **triar** los mensajes del chat — responder los
> simples él mismo y **rutear los de código/agente a Claude Code**. Opt-in; router **pluggable** y
> **prompt-based** (prompt editable por config). La UI de descarga/config y RouteLLM son rebanadas
> siguientes.

## Objetivo

Cerrar el circuito end-to-end: el IDE spawnea `mlx_lm.server`, y en el chat un **router** decide por
mensaje entre el **modelo local** (tareas simples/chat — responde ahí, sin gastar contexto de Claude)
y **Claude Code** (código/agente). Se ve qué backend respondió (badge). Todo detrás de un flag; si
mlx no está configurado, el chat funciona como hoy.

## Decisiones tomadas (brainstorming 2026-07-21)

1. **Uso = triage en el chat** (modelo utilitario que discierne), no reemplazar al agente.
2. **Local (mlx) vs Claude Code**, la decisión se toma en `chat.send` (path humano). **No** en
   `hub.ask` de orquestación (una hija comandada siempre es Claude).
3. **El IDE spawnea `mlx_lm.server`** (lifecycle propio). Dep opcional `ide-server[mlx]`, solo-Mac.
4. **Router prompt-based, en una llamada**: el modelo local recibe el mensaje con un system prompt de
   triage; si es simple, responde (esa es la respuesta local); si requiere código/tools, responde
   exactamente `ROUTE_TO_CLAUDE` → va a Claude Code.
5. **Router pluggable**: interfaz `Router.route(text) -> RouteDecision`; Fase 1 implementa el
   prompt-based; RouteLLM entra después por la misma interfaz.
6. **Prompt del router editable por config** (`.ide/config.toml [mlx].router_prompt`), con default
   en código. (La UI para editarlo es Rebanada 2.)
7. **Switch por-proyecto**: `[mlx].enabled` en el `.ide/config.toml` del **workspace** (no global)
   es el interruptor on/off. Sin `[mlx]` o `enabled=false` → chat Claude-only (comportamiento actual).
8. **Degradar con aviso**: si mlx está prendido pero no disponible, cae a Claude **y avisa
   visiblemente** (nunca falla silencioso, nunca rompe el chat).

## Arquitectura

### Backend — paquete `mlx/`

**Dep**: `httpx>=0.27` pasa a runtime (ya viene transitivo por `notion-client`; se declara explícito).
`mlx-lm` como extra opcional: `[project.optional-dependencies] mlx = ["mlx-lm>=0.19"]`.

- **`mlx/config.py`**: `mlx_config(root: Path) -> MlxConfig | None`. Lee el `.ide/config.toml` del
  **workspace** (`root/.ide/config.toml`, sección `[mlx]`) — **por-proyecto**, no global; si falta la
  sección o `enabled` no es true → `None` (mlx apagado). `MlxConfig = {model: str, router_prompt:
  str, port: int | None}`. `router_prompt` default `DEFAULT_ROUTER_PROMPT` (constante del módulo) si
  no está en el toml. Reutiliza el patrón de lectura toml de `notion/config.py`. (El download del
  modelo sigue siendo global en el cache de HF; lo que es por-proyecto es el *switch* y el prompt.)
- **`mlx/server.py`** — `MlxServer(model, *, spawn=subprocess.Popen, http_get=..., find_port=...)`:
  - `async ensure_running() -> str` (base url): si ya corre, devuelve la url; si no, elige puerto
    libre (`find_free_port` de `cli.py`, reusado), `spawn([sys.executable, "-m", "mlx_lm.server",
    "--model", model, "--port", str(port)])`, y **hace polling de health** (`GET {url}/v1/models`
    hasta 200, con timeout — la carga del modelo tarda) antes de devolver. Errores: spawn falla
    (mlx-lm no instalado) → `MlxUnavailable("instala ide-server[mlx]")`; timeout de carga →
    `MlxUnavailable("el modelo no cargó a tiempo")`.
  - `stop()`: termina el subproceso si está vivo.
  - Los hooks `spawn`/`http_get`/`find_port` son inyectables para tests (no se corre mlx real).
- **`mlx/client.py`** — `MlxClient(base_url, *, http_post=...)`:
  - `async chat(messages: list[dict]) -> str`: `POST {base_url}/v1/chat/completions` con
    `{"model": "local", "messages": messages}` (OpenAI-compatible), devuelve
    `resp["choices"][0]["message"]["content"]`. `http_post` inyectable (httpx real por default).
- **`mlx/router.py`** — router pluggable:
  - `@dataclass RouteDecision: route: str ("local"|"claude"); reply: str | None; degraded: bool = False`
    (`degraded=True` cuando se cae a Claude porque mlx no estaba disponible — el handler lo usa para avisar).
  - `class Router(Protocol): async def route(self, text: str) -> RouteDecision`.
  - `class PromptRouter(client: MlxClient, router_prompt: str)`: `route(text)` manda
    `[{role:"system", content: router_prompt}, {role:"user", content: text}]` al client; si la
    respuesta (stripeada) es exactamente `ROUTE_TO_CLAUDE` (o la contiene como única línea/última
    palabra — parseo tolerante) → `RouteDecision("claude", None)`; si no → `RouteDecision("local",
    reply)`. La lógica de parseo del sentinela es **pura y testeable** (helper `parse_route(text) ->
    (route, reply)`).
  - `DEFAULT_ROUTER_PROMPT`: instruye al modelo a responder tareas simples y emitir
    `ROUTE_TO_CLAUDE` si requiere leer/editar código, correr comandos o trabajar con el proyecto.

**`MlxRouter` (orquestador del subsistema)** — atado en `app.py` con `root` del workspace: construye
`MlxServer` + `MlxClient` (lazy) + `PromptRouter` desde `mlx_config(root)`. Expone `async decide(text)
-> RouteDecision | None` (`None` si mlx está apagado; si prendido, `ensure_running` + `router.route`).
Errores de mlx (`MlxUnavailable`) → devuelve una decisión **claude** con un flag `degraded=True` (no
rompe el chat) para que el handler **avise** (evento de aviso visible), no lo trague.

### Integración en el chat (`capabilities/chat.py`)

`chat.send {sessionId, text}` (path humano) pasa a:

1. `decision = await mlx_router.decide(text)` (si `mlx_router` fue inyectado y está enabled).
2. Si `decision` trae `degraded=True` → emite un aviso visible (`ChatError` o un evento de aviso:
   "modelo local no disponible, usando Claude") **antes** de seguir — el usuario se entera de que el
   switch está prendido pero mlx no arrancó.
3. Si `decision is None` o `decision.route == "claude"` → emite `Routed(source="claude")` (badge) y
   sigue el flujo actual: `hub.send_human(sid, text)` (Claude Code responde).
4. Si `decision.route == "local"` → emite `Routed(source="local")` + la respuesta del modelo como
   evento(s) de chat (`TextDelta(reply)` + `Done`) al canal `chat.event.{sid}`, **sin** tocar el
   driver de Claude (el turno no entra al contexto de Claude — ahorro de tokens). Emite vía el hub
   (`hub.emit` / broadcast), respetando el patrón de flush.

`hub.ask` (orquestación) **no** cambia — no pasa por el router.

### Evento nuevo (`chat/events.py`)

`@dataclass Routed: source: str` → `to_payload` mapea a `{"kind":"routed","source": <"local"|"claude">}`.
Se emite al inicio del turno humano para que el front sepa quién responde.

### Frontend

- **`state/chat.ts`**: `Msg` gana `source?: "local" | "claude"`. `applyEvent`: en `kind:"routed"`,
  guarda un `pendingSource` en el convo; cuando se crea el próximo `Msg` de agente (`lastAgent`), se
  le setea `source = pendingSource`. (Análogo al patrón del badge de relay.)
- **`main/ChatView.tsx` / `MessageBubble`**: si `m.source`, badge chico: **"local"** (color distinto,
  p.ej. un verde/azul suave) o **"claude"** (ámbar), junto al mensaje del agente.

## Config (opt-in, por-proyecto)

El `.ide/config.toml` **del workspace** (el mismo donde viven `name` y los roles):
```toml
[mlx]
enabled = true                                          # el switch on/off
model = "mlx-community/Qwen2.5-3B-Instruct-4bit"
# router_prompt = "..."   # opcional; default en código
```
Sin esta sección (o `enabled=false`) → mlx apagado, chat = Claude-only (hoy). Es **por-proyecto**:
prendes mlx en los workspaces que quieras. (El modelo bajado se comparte a nivel máquina — cache HF.)

## Manejo de errores

- `mlx-lm` no instalado / server no arranca / timeout de carga → `MlxUnavailable` → `decide` devuelve
  `RouteDecision("claude", None, degraded=True)` → el chat **cae a Claude** (no se rompe) y el handler
  **emite un aviso visible** ("modelo local no disponible, usando Claude"). Sin fallo silencioso.
- Respuesta del server malformada durante una respuesta local ya en curso → propaga como error del
  handler → envelope.

## Plan de tests (TDD)

**Backend (fakes; nada de mlx real):**
1. `mlx/config`: lee `[mlx]` (enabled/model/router_prompt); default del prompt; `None` si falta o
   `enabled=false`.
2. `router.parse_route` (puro): `"ROUTE_TO_CLAUDE"` → claude; texto normal → local + reply; tolerante
   a whitespace/última-línea.
3. `PromptRouter.route`: con `MlxClient` fake → arma los messages (system=router_prompt, user=text),
   devuelve la `RouteDecision` correcta según la respuesta fake.
4. `MlxServer.ensure_running`: con `spawn`/`http_get`/`find_port` fakes → spawnea con los args
   correctos (`-m mlx_lm.server --model X --port P`), hace health-poll hasta 200, devuelve la url;
   spawn que falla → `MlxUnavailable`.
5. `MlxClient.chat`: `http_post` fake → arma el body OpenAI y parsea `choices[0].message.content`.
6. `MlxRouter.decide`: apagado → `None`; prendido local → decisión local; `MlxUnavailable` → degrada
   a claude (route claude) + marca error.
7. Capability `chat.send`: con un `mlx_router` fake — route local emite `Routed("local")` + la
   respuesta sin tocar el driver; route claude emite `Routed("claude")` + llama `send_human`; sin
   router (None) → flujo actual intacto (tests de chat existentes verdes).

**Frontend:**
8. `chat/events` payload de `Routed`. `state/chat` `applyEvent` con `routed` taggea el próximo Msg de
   agente con `source`. `ChatView`/bubble renderiza el badge local/claude.

**Verificación en vivo (fuera del plan, requiere prerequisito):** instalar `ide-server[mlx]` + bajar
un modelo (~GBs), configurar `[mlx]`, y mandar en el chat una pregunta simple (→ local) y una de
código (→ Claude). Se hace aparte, con tu ok.

## Fuera de alcance (Rebanada 2 y 3)

- Panel de Settings "Modelos": descargar modelos, editar el prompt del router desde la UI, enable/
  disable. (Rebanada 2.)
- **RouteLLM** como router alternativo. (Rebanada 3.)
- Override manual del ruteo por mensaje; streaming token-a-token del mlx; usar el mlx para otras
  tareas (nombres/commits); múltiples modelos locales.

## Fidelidad de UI

Badge del turno con el idiom de los chips/badges existentes (como el badge de relay de orquestación):
**"local"** en un color distinto al ámbar, **"claude"** en ámbar `#e0863f`. Sin panel nuevo.
