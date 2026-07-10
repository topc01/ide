# Fundación UI — shadcn/ui tematizado a 1a · Design

Fecha: 2026-07-09 · Estado: **aprobado** · Tipo: refactor de fundación (capa UI).
Depende de: R0 (Fundación), R1 (Sesiones), R2-backend (Terminal, parkeado en `feat/r2-terminal`).

## Objetivo

Reemplazar el frontend hand-built (inline styles + CSS vars) por **shadcn/ui + Tailwind CSS**,
tematizado a la identidad **1a — Terminal/amber**. Se migra toda la UI existente (layout de 3
regiones + sesiones) y se construye el **frontend de la terminal de R2** sobre la base nueva,
para no dejar estilo mixto ni UI que se reemplace después. Backend intacto.

## Decisión de dirección visual (reescribe la regla #1 de CLAUDE.md)

- **Antes:** "Fidelidad de UI: se implementa contra el mockup (`docs/design/handoff/`), tokens
  exactos, nada de estética por defecto."
- **Ahora:** "**Identidad visual 1a (paleta ámbar/terminal) vía shadcn/ui + Tailwind.** Los
  componentes usan el look/pulido nativo de shadcn (radios, motion, foco/hover accesibles),
  **tematizados** a los tokens 1a. El mockup (`docs/design/handoff/`) es **referencia de layout
  e identidad**, no un objetivo pixel." (Decisión del dueño, 2026-07-09 — se actualiza CLAUDE.md.)

## Arquitectura

Cambio de **capa UI únicamente**. Se conserva todo lo no-visual: stores Zustand
(`useStore`, `useSessions`), transport (`WsClient`/`getWs`, `transport/*`), registro de módulos
del rail, envelope WS. El **backend de terminal de R2** viaja en esta rama (sale de
`feat/r2-terminal`), así el frontend de la terminal tiene su capacidad `terminal.*`.

- **Tailwind CSS** en el frontend Vite+React+TS (`tailwind.config`, `postcss`, directivas en un
  `index.css`).
- **shadcn/ui** inicializado (`components.json`); los componentes se copian a
  `ui/src/components/ui/` (código propio, no dependencia opaca). Usa Radix + `lucide-react`
  (ya lo tenemos) + `class-variance-authority`/`clsx`/`tailwind-merge`.
- **Tema oscuro-only** en `:root`/`.dark`, mapeando los tokens 1a al formato de shadcn.

### Mapeo del tema 1a → shadcn (CSS vars)

| shadcn var | valor 1a | origen |
|---|---|---|
| `--background` | `#161513` | App bg |
| `--foreground` | `#f0ece4` | Text primary |
| `--card` / `--popover` | `#1c1a17` | Panel bg |
| `--card-foreground` / `--popover-foreground` | `#f0ece4` | |
| `--primary` | `#e0863f` | Accent ámbar |
| `--primary-foreground` | `#161513` | On-accent |
| `--secondary` / `--muted` | `#211e1a` | Agent bubble / muted surface |
| `--muted-foreground` | `#75705f` | Text muted |
| `--accent` | `#2e2820` | Selected bg |
| `--accent-foreground` | `#f0ece4` | |
| `--border` / `--input` | `#332f28` | Border |
| `--ring` | `#e0863f` | Accent (foco) |
| `--radius` | `0.5rem` (default shadcn) | (look shadcn) |

Vars propias (fuera del set shadcn) para lo del dominio: `--terminal-bg:#0f0e0c`,
`--status-running:#7fb069`, `--status-idle:#7d7568`, `--status-done:#6b8fbf`,
`--role-pill-bg:#2e2820`, y los de diff (`--diff-add-*`/`--diff-del-*`) para R4. Tailwind
extiende `colors` desde estas vars. `titleBg:#131210` → `--title-bg`.

## Componentes

### shadcn (copiados a `components/ui/`)
Button, Dialog, Input, Label, Select, RadioGroup, Tabs, ScrollArea, Tooltip, Badge, Separator.

### Migración de la UI existente (mismo comportamiento, look shadcn + 1a)
| Componente actual | Se rehace con |
|---|---|
| `layout/ActivityRail` | botones + `Tooltip`; activo con `--primary` |
| `layout/TabStrip` | `Tabs` (pestaña Chat fija primero) |
| `layout/ContextPanel` / `MainPanel` | contenedores Tailwind (flex 3 regiones) |
| `modules/sessions/SessionsPanel` | `ScrollArea` + secciones; fila punteada "+ Agregar sesión" |
| `modules/sessions/SessionNodeRow` | **custom** (árbol recursivo, indent 16px, chevron, status dot) estilado con Tailwind; pill de rol con `Badge` |
| `modules/sessions/NewSessionModal` | `Dialog` + `Input`/`Label` + `Select` + `RadioGroup` + `Button`; picker de branches marca ocupadas |

### Frontend de terminal (R2, nuevo sobre la base shadcn)
| Componente | Qué hace |
|---|---|
| `modules/terminal/TerminalPanel` | card de contexto de la sesión activa + `Button` "Abrir terminal" → `openTerminal` + `openTab` |
| `main/TerminalTab` | `xterm.js` (`@xterm/xterm` + addon-fit) montado, conectado al canal WS de la terminal (`terminalChannel` de R2); input/resize/salida; body `--terminal-bg` |
| `transport/terminalChannel` | open/write/resize/subscribe (base64) sobre `getWs()` (igual que el plan de R2) |
| registro del módulo `terminal` real | reemplaza el stub del rail |

**Lo que sigue custom** (shadcn no lo cubre): árbol de sesiones, status dots, terminal xterm.

## Flujo de datos / estado

Sin cambios: los componentes leen de `useStore`/`useSessions` y llaman al transport igual que
hoy. Solo cambia el markup/estilo. `applyTheme` (que seteaba CSS vars por JS) se reemplaza por
el tema estático en `index.css` (Tailwind/shadcn); se conserva un test de que las vars 1a
existen en el tema.

## Manejo de errores

Sin cambios (viven en el transport: `WsClient` rechaza en frame `error`; `getRepos`/`fetchTree`
degradan). Los estados "desconectado"/error se muestran igual, ahora con componentes shadcn.

## Testing

- **vitest + RTL** como hoy: store real, transport mockeado; los tests asertan
  **comportamiento/roles/texto** (getByRole/getByText/getByLabelText), **no** estilos
  computados — Tailwind no requiere setup en vitest (las clases son strings). Radix/Dialog
  funcionan en jsdom (portales testeables).
- `tsc --noEmit` limpio; `npm run build` (Tailwind + Vite) limpio.
- Cada migración de componente mantiene sus tests verdes (ajustando selectores si un rol/aria
  cambia por usar el primitivo shadcn, nunca aflojando una aserción para que pase).

## Criterios de aceptación (hecho)

1. Tailwind + shadcn instalados; tema 1a (paleta ámbar/terminal) aplicado; dark-only.
2. Toda la UI existente (layout 3 regiones, activity rail, tabs, SessionsPanel/árbol/rename,
   NewSessionModal + picker) rehecha con shadcn + 1a, con sus tests verdes.
3. Frontend de terminal funcionando sobre la base shadcn (abrir terminal → xterm interactiva).
4. `tsc` limpio, `npm run build` limpio, suites back+front verdes.
5. Identidad 1a preservada (accent `#e0863f`, fondos oscuros, terminal `#0f0e0c`).
6. Regla #1 de CLAUDE.md actualizada.

## Fuera de alcance

Chat con Claude (R3), diffs (R4), graphite (R5), tasks/notion (R6). El árbol de sesiones no
cambia su modelo; el branch-switcher avanzado sigue como extensión.

## Nota para R3 (chat) — AI Elements

`elements.ai-sdk.dev` (**AI Elements**) es una librería de componentes de chat **shadcn/Tailwind**
(Conversation, Message, Reasoning, Code, Tool, InlineCitation, PromptInput). Al adoptar shadcn,
sus componentes **de presentación** son reusables directo. El matiz: están cableados al modelo de
datos del **Vercel AI SDK** (streaming), y nosotros parseamos el **transcript de Claude Code** (no
la Messages API). Jugada para R3: reusar la **presentación** de AI Elements alimentada con nuestro
transcript parseado, saltándose su capa de datos del AI SDK. No se instala ahora (YAGNI, no hay
chat todavía) — queda anotado para el spec de R3.

## Notas de ejecución

- Rama `feat/ui-shadcn` (sale de `feat/r2-terminal`, incluye el backend de terminal de R2).
- Requisitos: Node 18+. Nuevas deps: `tailwindcss`/`postcss`/`autoprefixer`, `class-variance-authority`,
  `clsx`, `tailwind-merge`, `@radix-ui/*` (los que traiga shadcn), `@xterm/xterm`/`@xterm/addon-fit`.
