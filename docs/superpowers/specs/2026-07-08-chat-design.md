# R3 — Chat (Claude Code local) · Design

Fecha: 2026-07-08 · Reconciliado: 2026-07-12 · Estado: **aprobado** · Rebanada: R3 del
`docs/design/ROADMAP.md`. Depende de: R0 (Fundación), R1 (Sesiones), R2 (Terminal/PTY),
Fundación UI shadcn (`2026-07-09-ui-shadcn-design.md`).

## Objetivo

La vista de **Chat** (pestaña por default del panel principal): la conversación con
**Claude Code local**, manejada **programáticamente** y renderizada estructurada (burbujas,
chips de tool calls / edits, footer de tokens). Es el corazón del producto.

## Decisiones cerradas (2026-07-12)

1. **Driver = Claude Agent SDK de Python** (no la Messages API, no el PTY de R2). Ver
   §Auth y §Componentes. Fallback documentado: CLI `stream-json`.
2. **Arranque lazy.** El proceso `claude` de una sesión arranca al **abrir su chat**
   (`chat.start`), no al crearla. Ver §Modelo. Cero costo de proceso/tokens en sesiones
   que no abriste — clave para el modelo de muchas sesiones paralelas.
3. **UI shadcn + AI Elements.** La presentación del chat reusa **AI Elements**
   (componentes shadcn/Tailwind) tematizados a 1a, alimentados por **nuestro transcript
   parseado** (no la capa de datos del Vercel AI SDK). Ver §Componentes.

## Fidelidad de UI (prioridad)

Identidad **1a — Terminal/amber** vía shadcn/ui (regla #1 de CLAUDE.md, actualizada por la
fundación shadcn). **Sin labels de rol.** User a la derecha (burbuja accent `#e0863f`, texto
on-accent `#161513`); agente a la izquierda (burbuja `#211e1a`). Bajo cada mensaje del agente,
stack de **chips atenuados** (sin borde, bg `#1a1714`, tool name `#bd925f`, dot `#a5703c`):
**tool calls** (`Read`/`Grep`/`Bash`… + detalle mono como path o arg) y **edits** (ícono lápiz
+ `Edit` + path + `+added` verde `#9fcf87` / `-removed` rojo `#d89a89`). **Footer de tokens**
(reloj + `1,820 tokens`). Composer redondeado abajo (input + botón circular de envío, hover
`#eb954f`). El mockup 1a (`docs/design/handoff/`) es referencia de identidad, no objetivo pixel.

## Auth: Claude Code directo, sin API key

Manejamos el **Claude Code local**, que usa **tu login de Claude Code** (suscripción/OAuth),
**no** un `ANTHROPIC_API_KEY`.

- **Vía elegida: Claude Agent SDK de Python** (`claude-agent-sdk`, ex `claude_code_sdk`).
  Envuelve el binario `claude` local, hereda su auth de suscripción, y entrega mensajes ya
  estructurados (bloques de texto, `tool_use`, `tool_result`, `result` con usage), con
  callbacks de permisos, `resume` e interrupt. **El binding exacto (nombres de
  `query`/`ClaudeSDKClient`, opciones, callback de permisos) se verifica contra el repo
  oficial del SDK al implementar** — no se adivina en el plan.
- **Fallback**: spawnear `claude --output-format stream-json --input-format stream-json` y
  parsear el JSONL nosotros (estilo `transcript.js` de finnecto). Mismo login local.
- **No** usamos el SDK `anthropic` (Messages API) — ese requeriría key y no aplica acá.

## Modelo

- **1 sesión = 1 conversación** de Claude Code, en el `cwd` (worktree) de la sesión.
- **Arranque lazy:** crear la sesión (R1) sólo hace worktree + branch (`NullLauncher`). El
  proceso `claude` arranca la **primera vez que se abre el chat** de la sesión (`chat.start`),
  sembrado con `description` + preset del rol. `chat.attach` reengancha uno ya vivo.
- El **Chat muestra la conversación de la sesión activa** (`activeSessionId`). Cambiar de
  sesión en el sidebar cambia el chat (la pestaña Chat es fija).
- Coordinadora y sesión de trabajo se renderizan **igual** (la orquestación real — que la
  coordinadora comande hijas — es la rebanada "fide" posterior; ver Fuera de alcance).

## Permisos (configurable por sesión)

Cada sesión tiene un **modo de permisos**, con **default desde el preset del rol** y
**override por sesión**:

- **Skip permissions** (`--dangerously-skip-permissions` / equivalente del SDK): Claude
  ejecuta todo sin pedir. Toggle explícito por sesión.
- **Normal**: cuando Claude pide una tool fuera de lo auto-aprobado, el chat muestra
  **approve/deny inline** (el deny puede llevar un motivo que vuelve al agente).
- Los presets de rol read-only (Lector/Revisor) auto-aprueban lecturas y niegan escrituras.

## Streaming y steering

- **Streaming en vivo por WebSocket**: texto (deltas), tool calls, tool results y edits
  aparecen a medida que Claude trabaja; el footer de tokens se actualiza al cerrar cada
  mensaje del agente.
- **Composer**: envía un mensaje del usuario a la conversación de la sesión activa. Se puede
  encolar mientras Claude trabaja.
- **Interrumpir**: botón de stop → interrumpe la corrida actual (deja la sesión lista para el
  próximo mensaje).

## Parseo (referencia finnecto)

El mapeo de eventos del Agent SDK → elementos del chat (mensajes, tool calls, edits, tokens)
se basa en la lógica de `transcript.js` de finnecto. Un mensaje del agente = texto + N chips +
footer. Con el Agent SDK los eventos ya vienen estructurados, así que el parser es un mapeo
directo evento→elemento (no hay que tokenizar JSONL crudo salvo en el fallback CLI).

## Persistencia / resume

La conversación **persiste** y se **reengancha** al reabrir el IDE (`resume` del SDK), leyendo
el transcript de la sesión. El historial se re-renderiza.

## Componentes (unidades)

### Backend
| Unidad | Qué hace |
|--------|----------|
| `claude_driver.py` | Wrapper del Claude Agent SDK: arranca/reengancha el `claude` local en el cwd con modelo+prompt del rol y modo de permisos; traduce el stream a eventos normalizados (`text_delta`, `tool_use`, `tool_result`, `edit`, `usage`, `permission_request`). Fallback CLI stream-json detrás de la misma interfaz. |
| `capabilities/claude_session.py` | Canales `chat.start` (arranca lazy), `chat.attach` (resume), `chat.send`, `chat.interrupt`, `chat.permission`; emite eventos de streaming por WS (`chat.event.<sid>`). |
| `permissions.py` | Resuelve modo (skip vs normal) por sesión (default del rol); rutea `permission_request` → approve/deny del cliente. |

### Frontend (shadcn + AI Elements, tematizado a 1a)
| Unidad | Qué hace |
|--------|----------|
| `main/ChatView` | Pestaña Chat: render de la conversación de la sesión activa; auto-scroll; estado "arrancando…" en el arranque en frío. |
| `chat/*` (AI Elements) | Presentación reusando AI Elements (Conversation/Message/Tool/Reasoning) tematizada a 1a, alimentada por el transcript parseado; burbujas user/agente, chips de tool call / edit (+/-), footer de tokens. |
| `chat/Composer` | Input + botón de envío; stop para interrumpir. |
| `chat/PermissionPrompt` | Approve/deny inline cuando llega un `permission_request`. |
| `transport/chatChannel` | Suscripción al stream de eventos de la conversación por WS (patrón de `terminalChannel`). |

## Flujo de datos

Abrir el chat de una sesión → `chat.start` (o `chat.attach` si ya vivía) → eventos de streaming
por WS → `ChatView` los acumula y renderiza. Composer → `chat.send`. `permission_request` →
`PermissionPrompt` → `chat.permission({allow|deny, reason?})`. Stop → `chat.interrupt`. Reabrir
IDE → `resume` re-renderiza el historial.

## Manejo de errores

- `claude` no instalado / no logueado → `error` tipado y claro ("Claude Code no está
  logueado — corré `claude login`"), renderizado; **nunca silencioso**.
- Corrida que falla → se muestra el error en el chat, la sesión queda usable.
- WS caído → el chat marca "desconectado" y reengancha por resume al volver.

## Testing

- **Backend (pytest)**: el driver traduce un stream de ejemplo del Agent SDK a los eventos
  normalizados (text/tool_use/edit/usage); un `permission_request` en modo normal espera la
  decisión; en skip se auto-aprueba. (Se mockea el SDK / el binario `claude`.)
- **Frontend (vitest/RTL)**: render de burbujas user/agente sin labels; chips de tool call y
  edit con `+/-`; footer de tokens; `PermissionPrompt` approve/deny; composer limpia al enviar;
  estado "arrancando…". Tests asertan comportamiento/roles/texto, no estilos computados.

## Criterios de aceptación (R3 hecho)

1. Al **abrir el chat** de una sesión, su conversación de Claude Code arranca (lazy) y aparece.
2. Envío un mensaje y veo la respuesta **en streaming**, con chips de tool calls/edits y
   footer de tokens, fiel a 1a (shadcn/AI Elements).
3. El modo de permisos funciona: **skip** ejecuta sin pedir; **normal** muestra approve/deny
   inline, configurable por sesión (default por rol).
4. Interrumpir corta la corrida; la conversación persiste y se reengancha por `resume` al
   reabrir.
5. Sin API key: funciona con el login de Claude Code (Agent SDK).
6. Tests de back y front pasan; `tsc` y build limpios.

## Fuera de alcance

- **Orquestación de la coordinadora** (que comande hijas — "fide"/el King) — es su propia
  rebanada posterior; R3 sólo renderiza conversaciones uniformemente.
- Diffs (R4), graphite (R5), tasks/notion/settings (R6).

## Notas de ejecución

- Rama nueva `feat/r3-chat` (sale de `main`, que ya incluye R0–R2 + fundación shadcn + React 19).
- Nueva dep backend: `claude-agent-sdk` (verificar nombre/versión exactos del paquete al
  implementar). Frontend: AI Elements (vendorizar los componentes de presentación necesarios,
  como shadcn — no depender de la capa de datos del Vercel AI SDK).
- El binding exacto del Agent SDK se fija con un WebFetch al repo oficial en la primera tarea
  del plan, antes de escribir el driver.
