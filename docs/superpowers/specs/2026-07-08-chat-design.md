# R3 — Chat (Claude Code local) · Design

Fecha: 2026-07-08 · Estado: **en revisión** · Rebanada: R3 del `docs/design/ROADMAP.md`.
Depende de: R0 (Fundación), R1 (Sesiones).

## Objetivo

La vista de **Chat** (pestaña por default del panel principal): la conversación con
**Claude Code local**, manejada **programáticamente** y renderizada estructurada (burbujas,
chips de tool calls / edits, footer de tokens). Es el corazón del producto.

## Fidelidad de UI (prioridad)

Contra el mockup 1a (§3.2). **Sin labels de rol.** User a la derecha (burbuja accent
`#e0863f`, texto on-accent `#161513`); agente a la izquierda (burbuja `#211e1a`). Bajo cada
mensaje del agente, stack de **chips atenuados** (sin borde, bg `#1a1714`, tool name
`#bd925f`, dot `#a5703c`): **tool calls** (`Read`/`Grep`/`Bash`… + detalle mono como path o
arg) y **edits** (ícono lápiz + `Edit` + path + `+added` verde `#9fcf87` / `-removed` rojo
`#d89a89`). **Footer de tokens** (reloj + `1,820 tokens`). Composer redondeado abajo (input
+ botón circular de envío, hover `#eb954f`).

## Auth: Claude Code directo, sin API key

Manejamos el **Claude Code local**, que usa **tu login de Claude Code** (suscripción/OAuth),
**no** un `ANTHROPIC_API_KEY`.

- **Vía preferida**: Claude Agent SDK de Python — lanza el binario `claude` local y hereda su
  auth. (Binding exacto a verificar contra docs oficiales al implementar; ver `REFERENCES.md`.)
- **Fallback**: spawnear `claude --output-format stream-json --input-format stream-json`,
  que también usa el login local.
- **No** usamos el `anthropic` SDK (Messages API) — ese sí requeriría key y no aplica acá.

## Modelo

- **1 sesión = 1 conversación** de Claude Code. La conversación **se auto-arranca al crear la
  sesión** (R1), sembrada con `description` + preset del rol, en el `cwd` de la sesión.
- El **Chat muestra la conversación de la sesión activa** (`activeSessionId`). Cambiar de
  sesión en el sidebar cambia el chat (la pestaña Chat es fija).
- Coordinadora y sesión de trabajo se renderizan **igual** (la orquestación real — que la
  coordinadora spawnee/comande hijas vía tools — es una rebanada posterior; ver Fuera de
  alcance).

## Permisos (configurable por sesión)

Cada sesión tiene un **modo de permisos**, con **default desde el preset del rol** y
**override por sesión**:

- **Skip permissions** (`--dangerously-skip-permissions`): Claude ejecuta todo sin pedir.
  Toggle explícito por sesión.
- **Normal**: cuando Claude pide una tool fuera de lo auto-aprobado, el chat muestra
  **approve/deny inline** (y el deny puede llevar un motivo que vuelve al agente).
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

El mapeo de eventos de Claude Code → elementos del chat (mensajes, tool calls, edits, tokens)
se basa en `transcript.js` de finnecto. Un mensaje del agente = texto + N chips + footer.

## Persistencia / resume

La conversación **persiste** y se **reengancha** al reabrir el IDE (`claude --resume` /
equivalente del SDK), leyendo el transcript de la sesión. El historial se re-renderiza.

## Componentes (unidades)

### Backend
| Unidad | Qué hace |
|--------|----------|
| `capabilities/claude_session.py` | `chat.start`/`chat.attach` (arranca/reengancha Claude Code en el cwd con modelo+prompt del rol y modo de permisos), `chat.send`, `chat.interrupt`; emite eventos de streaming. |
| `claude_driver.py` | Wrapper del Claude Agent SDK (o CLI stream-json): traduce el stream de Claude Code a eventos normalizados (`text_delta`, `tool_use`, `tool_result`, `edit`, `usage`, `permission_request`). |
| `permissions.py` | Resuelve modo de permisos (skip vs normal) por sesión; rutea `permission_request` → approve/deny del cliente. |

### Frontend
| Unidad | Qué hace |
|--------|----------|
| `main/ChatView` | Pestaña Chat: render de la conversación de la sesión activa; auto-scroll. |
| `chat/MessageBubble` + `ActionChip` | Burbujas (user/agente) y chips de tool call / edit + footer de tokens (estilo 1a). |
| `chat/Composer` | Input + botón de envío; stop para interrumpir. |
| `chat/PermissionPrompt` | Approve/deny inline cuando llega un `permission_request`. |
| `transport/chatChannel` | Suscripción al stream de eventos de la conversación por WS. |

## Flujo de datos

Crear sesión (R1) → `chat.start` arranca Claude Code → eventos de streaming por WS →
`ChatView` los acumula y renderiza. Composer → `chat.send`. `permission_request` →
`PermissionPrompt` → `chat.permission({allow|deny, reason?})`. Stop → `chat.interrupt`.

## Manejo de errores

- `claude` no instalado / no logueado → `error` tipado y claro ("Claude Code no está
  logueado — corré `claude login`"), renderizado; **nunca silencioso**.
- Corrida que falla → se muestra el error en el chat, la sesión queda usable.
- WS caído → el chat marca "desconectado" y reengancha por resume al volver.

## Testing

- **Backend (pytest)**: el driver traduce un stream de ejemplo de Claude Code a los eventos
  normalizados (text/tool_use/edit/usage); un `permission_request` en modo normal espera la
  decisión; en skip se auto-aprueba. (Se mockea el binario `claude`.)
- **Frontend (vitest/RTL)**: render de burbujas user/agente sin labels; chips de tool call y
  edit con `+/-`; footer de tokens; `PermissionPrompt` approve/deny; composer limpia al enviar.

## Criterios de aceptación (R3 hecho)

1. Al crear/activar una sesión, su conversación de Claude Code aparece en el Chat.
2. Envío un mensaje y veo la respuesta **en streaming**, con chips de tool calls/edits y
   footer de tokens, fiel al mockup 1a.
3. El modo de permisos funciona: **skip** ejecuta sin pedir; **normal** muestra approve/deny
   inline, configurable por sesión (default por rol).
4. Interrumpir corta la corrida; la conversación persiste y se reengancha al reabrir.
5. Sin API key: funciona con el login de Claude Code.
6. Tests de back y front pasan.

## Fuera de alcance

- **Orquestación de la coordinadora** (que spawnee/comande hijas vía tools, "el King") — es
  su propia rebanada posterior; R3 solo renderiza conversaciones uniformemente.
- Diffs (R4), graphite (R5), tasks/notion/settings (R6).
