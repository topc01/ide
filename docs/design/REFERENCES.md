# Referencias

Punteros a las fuentes de verdad para implementar. Tres bloques: **diseño**,
**dominio (finnecto como referencia)**, e **integración con Claude Code**.

---

## 1. Diseño

Fuente de verdad: `docs/design/handoff/HANDOFF.md` (+ `mockup.dc.html`). Implementamos la
**dirección visual 1a — Terminal / amber**. Tokens extraídos del handoff:

### Tipografía
- UI: **Inter**. Código: **JetBrains Mono**.
- Tamaños: UI 11–13px (labels 9–11px, uppercase, con tracking); código 10.5–12.5px;
  headings principales 18–27px.

### Colores (1a)
| Rol | Hex |
|-----|-----|
| App bg | `#161513` |
| Panel bg | `#1c1a17` |
| Title bg | `#131210` |
| Terminal body | `#0f0e0c` |
| Agent bubble | `#211e1a` |
| Border | `#332f28` / `#2a2721` |
| Text primary | `#f0ece4` |
| Text secondary | `#cfc9bd` |
| Text muted | `#75705f` / `#9c9488` |
| **Accent (amber)** | `#e0863f` |
| Send hover | `#eb954f` |
| On-accent text | `#161513` |
| Selected session bg / border | `#2e2820` / `#e0863f` |
| Role pill | `#e0863f` sobre `#2e2820` |
| Chip atenuado (bg / tool name / dot) | `#1a1714` / `#bd925f` / `#a5703c` |
| Diff add (bg / text / marca `+`) | `rgba(127,176,105,.14)` / `#9fcf87` / `#7fb069` |
| Diff del (bg / text / marca `-`) | `rgba(201,106,78,.14)` / `#d89a89` / `#c96a4e` |
| Status dot: running / idle / done | `#7fb069` / `#7d7568` / `#6b8fbf` |

### Escala compartida
- **Radii**: 6–10px.
- **Spacing**: 4/6/8/10/12/14/16/20/24px.
- Botones del rail: 30–32px; íconos 14–16px, stroke 2px.
- Sidebar: ~272–288px. Panel de contexto: ~264–272px.
- Modal Settings: 760×540 (nav izq 212px). Modal nueva-sesión: ~440–460px.
- Indentación del árbol de sesiones: **16px por nivel**.

### Íconos
Sin assets de imagen. Todo SVG stroke (estilo feather/lucide): search, document/diff,
stacked-layers (graphite), checklist (tasks), console (terminal), book (notion),
git-branch, pencil (edit), clock (tokens), paper-plane (send), plus. En la UI usaremos
**lucide-react**.

---

## 2. Dominio — finnecto-ide como referencia

Repo de referencia: `finnecto-ide` (rama `v2`, privado). **No se copia código Node**; se estudia
la lógica y se reescribe en Python. Su capa de dominio está desacoplada de la TUI (solo
importa built-ins de Node), así que se lee como una librería.

| Necesidad del IDE | Módulo finnecto a estudiar |
|-------------------|----------------------------|
| Sesiones + árbol recursivo | `src/sessions.js`, `src/developments.js` |
| Worktrees (`.wt/<slug>`, branch `<slug>-wt`) | `src/worktrees.js` |
| Operaciones git (branches, +/- líneas, commits) | `src/git.js` |
| Graphite / branch-stack | `src/graphite.js` |
| Terminales (PTY) | `src/term.js` (usa `node-pty`) |
| Parseo del transcript de Claude (tool calls, edits, tokens) | `src/transcript.js` |
| Orquestación de sesiones ("el King") | `src/orq.js`, `src/conductor.js` |
| DB clonada / docker / puertos (rebanadas futuras) | `src/db.js`, `src/compose.js`, `src/ports.js` |

Modelo de sesión (nodo recursivo), del handoff:
`{ id, name, description?, role?, kind: 'repo'|'dir', repoId?, dir, branch, status,
expanded, terminals[], children[] }`.

---

## 3. Integración con Claude Code (local)

**Decisión**: manejamos el **Claude Code CLI local** desde Python. **No** Managed Agents
(esa API hostea el sandbox en infra de Anthropic; nosotros necesitamos worktrees, DB,
docker y puertos **locales**).

Dos canales:
- **Chat (programático)** → sesión de Claude Code en streaming (mensajes, tool calls,
  edits, tokens) que alimenta la vista de chat. Se implementa en **R3**.
- **Terminales (interactivo)** → PTY local (equivalente Python de `node-pty`, p.ej.
  `ptyprocess`/`pty`) por WebSocket → `xterm.js`. Se implementa en **R2**.

> ⚠️ **Verificar bindings al implementar.** El SDK de Python para manejar Claude Code
> local (Claude Agent SDK / Claude Code SDK) evoluciona; los nombres exactos de
> funciones/clases se confirman contra la documentación oficial **en el momento de
> escribir R2/R3**, no desde memoria. En R0 solo dejamos la **interfaz** (un plugin de
> capacidad "claude-session") sin atarnos a un binding concreto.

Modelos Claude por defecto para cualquier llamada directa a la API (si hiciera falta):
`claude-opus-4-8`. Pero el grueso del trabajo lo hace **Claude Code**, no llamadas
directas a la Messages API.
