# Handoff: Agentic IDE — Parallel Multi-Repo Sessions

## Overview
An agentic IDE for running **parallel, multi-repo Claude Code sessions**. The
operator orchestrates many concurrent agent sessions across several git
repositories and worktrees at once. Layout is a three-region workspace:

1. **Sessions sidebar** (left) — repos in use, a **recursive tree of sessions**,
   and a workspace configuration ("Customizations") footer.
2. **Activity rail + context panel** (middle) — icon rail with 6 modules
   (Search, Changed files, Graphite branch-stack, Tasks, Terminal, Notion) and
   the panel that renders the active module.
3. **Main panel** (right) — a conversational **chat** with the agent by
   default; opening a file / task / branch / terminal / notion-page swaps it
   into a tab.

Two visual directions are delivered side by side on one canvas:
- **1a — "Terminal / amber"**: dense, terminal-inspired, warm amber accent,
  JetBrains Mono for code, Inter for UI, 6–10px radii.
- **1b — "Studio / indigo"**: softer, more spacious, indigo/violet accent,
  IBM Plex Mono for code, Manrope for UI, 9–18px radii.

Both directions are functionally identical; they differ only in styling. Pick
one to implement, or let the team choose — the spec below applies to both, with
per-direction tokens in **Design Tokens**.

## About the Design Files
`Claude Code Mockup.dc.html` is a **design reference created in HTML** — an
interactive prototype showing the intended look and behavior. It is authored in
a proprietary component format (`.dc.html`) that will not run in a normal app,
and it is **not production code to copy directly**.

Recreate these designs in the target codebase's environment (for a
cross-platform desktop IDE, React + Electron/Tauri is a natural fit) using its
established patterns, component library, and state management. Treat the HTML as
the source of truth for layout, spacing, color, typography, copy, and
interaction — not as code to lift. All sample data (repos, sessions, commits,
diffs, chat, pages) is placeholder to demonstrate the UI; wire real data
sources.

## Fidelity
**High-fidelity.** Colors, typography, spacing, radii, and interactions are
final and intended to be reproduced precisely. Each mockup is drawn at a fixed
**1440 × 860** frame with a title strip; that framing is just for the mock —
in the real app the layout fills the window and is resizable.

---

## Region 1 — Sessions sidebar (left, ~272px / 288px)
Vertical flex column, three stacked areas:

### 1.1 Repos (top, scrollable, max-height ≈ 168–180px)
- Header label "Repos". **Vertical** list (repos can grow).
- Each row: repo name + current branch chip (monospace accent). Hover bg.
- **Click a repo → opens a terminal** in that repo's root (`~/<repo>`) in the
  main panel, branch selector defaulting to the repo's branch.

### 1.2 Sessions tree (middle, flex:1, scrollable) — RECURSIVE
- Header row "Sesiones" + a **"+"** button that creates a **top-level session**
  (only top-level/root sessions are created from here).
- A **recursive tree** of sessions rendered as a flattened list with
  **indentation by depth** (16px per level). Any session at any depth can have
  children (no fixed generation limit).
- **Each session row**: expand chevron (only when the node has children;
  rotates 90° when open), status dot, editable name, optional **role pill**
  (accent chip), and an inline **"+"** button (right) that adds a **child** to
  that specific session. Below the row: the session's branch (monospace accent).
- When a node is **expanded**, its children render indented beneath it, followed
  by a dashed **"+ Agregar sesión hija"** row (at child depth) — a second
  affordance to add a child to that node. So a child can be created either from
  a node's inline "+" or from the dashed add-row under its subtree; conceptually
  the agent (parent session) or the user can add children.
- **Selection**: clicking a row selects it (`activeSessionId`), highlighted with
  a tinted background + accent border/left-border. Selection drives the Terminal
  module (§2.2).
- **Rename**: double-click the name → inline input; Enter/blur commit, Escape
  cancels, empty reverts. Works at any depth (recursive tree update).
- **Status dot colors**: running `#7fb069`, idle `#7d7568`, done `#6b8fbf`.
- Top-level rows get extra top margin (~12px) for visual grouping.

**Session model** (recursive node): `{ id, name, description?, role?,
kind: 'repo'|'dir', repoId?, dir, branch, status, expanded, terminals[],
children[] }`. A session lives **either in a repo** (`kind:'repo'`, has
`repoId`) **or in a plain directory** (`kind:'dir'`, `dir` is an arbitrary
path). A child created under a session gets a worktree-style dir
(`<parentDir-or-repo>/.wt/<slug>`) and a generated branch (`<slug>-wt`) by
default. `description` and `role` are optional.

### 1.3 Customizations footer (bottom, bordered top)
- Vertical list of 8 items (icon + label + optional count): Overview, Agents,
  Skills, Instructions, Hooks, MCP Servers (2), Plugins, Tools (12).
- Clicking **any** item opens the **Settings modal** (§Interactions) with that
  item selected.

---

## Region 2 — Activity rail + context panel (middle)

### 2.1 Icon rail (40px / 44px) — 6 modules, toggles the panel
1. **Search** (magnifier) · 2. **Changed files** (document) · 3. **Graphite**
(stacked layers) · 4. **Tasks** (checklist) · 5. **Terminal** (console) ·
6. **Notion** (book). Active button = accent + tinted bg; all have hover bg.

### 2.2 Panel (≈ 264px / 272px) — renders the active module
- **Search**: text input + a "Recientes" file list (click opens the file diff).
- **Changed files**: list of changed files with `+added` / `-removed`; click
  opens the file diff in the main panel.
- **Graphite (branch stack)**: header + a **linear** (not tree) list of
  branches, each with a ringed dot, name, an "actual" tag on the current branch,
  and a **magnifier** icon. Click a branch row → **expands inline** to its
  commits (hash + message); click a commit → **expands inline** to its changed
  files (path + `+/-`). Click the **magnifier** (stopPropagation) → opens the
  **Branch detail** view in the main panel.
- **Tasks**: list of task cards (title + `.md` filename + status); click renders
  the task markdown in the main panel.
- **Terminal**: header + a **context card for the currently selected session**
  (session name + working directory) + the list of that session's terminals
  (e.g. `zsh`, `npm run dev`, `vitest --watch`; a colored dot marks running
  processes). Click a terminal → opens it in the main panel, scoped to the
  session's dir + branch.
- **Notion**: header + **"Nueva"** button (creates a page and opens it) + a list
  of pages (title + first-line preview). Click a page → opens it as an
  **editable** tab in the main panel.

---

## Region 3 — Main panel (right, flex:1)

### 3.1 Tab strip
Pinned non-closable **"Chat"** tab first, then dynamically opened tabs
(file / task / branch / terminal / page), each closable with `×`. Active tab is
accent-underlined (1a) or pill-highlighted (1b). Closing the active tab falls
back to the previous tab, or Chat.

### 3.2 Chat view (default) — agent conversation
- **No role labels.** User messages are right-aligned on an accent bubble; agent
  messages are left-aligned on a neutral bubble.
- Each **agent message** can render, below its text, a stack of low-emphasis
  **action chips** (no border, subtle bg, dimmed accent): **tool calls**
  (`Read`, `Grep`, `Bash`, … + a monospace detail such as a path or arg) and
  **edits** (pencil icon + `Edit` + file path + `+added` green / `-removed`
  red). A **token count** footer (clock icon + `1,820 tokens`) closes each agent
  message. These action chips are intentionally lighter in weight than the
  message text.
- Bottom: rounded composer (text input + circular send button).

### 3.3 Terminal view (from a repo, or a session terminal)
- Header: working directory (monospace muted) + a **branch selector** chip
  (git-branch icon + branch + caret). Clicking opens a dropdown with a **search
  input** ("Buscar branch…") and the repo's filtered branches; selecting updates
  the terminal's branch.
- Body: monospace terminal output on near-black bg (path in accent, commands in
  primary text, output muted, success green), ending in a `$` prompt with a
  blinking accent cursor block.

### 3.4 Branch detail view (from the Graphite magnifier)
Git-branch icon + branch name, a description paragraph, then a "Commits" section
where each commit is a card (hash accent + message) listing its changed files
with `+/-` counts.

### 3.5 File diff view (from Changed files / Search)
Filename header + monospaced diff lines: added on a green-tinted bg (green
text), removed on a red-tinted bg (red text), context transparent.

### 3.6 Task view (from Tasks)
Rendered markdown-style: title + sections (uppercase accent heading + em-dash
bullets).

### 3.7 Notion page view (from the Notion module)
An **editable** document: large title `<input>` + a full-height body
`<textarea>`. Edits update the page live (and the tab label tracks the title).

---

## Interactions & Behavior
- **Repo click** → open/focus a terminal tab for `~/<repo>` at the repo branch.
- **Session select** → set `activeSessionId`, highlight, repopulate Terminal
  module with that session's dir + terminals.
- **Session expand/collapse** → recursive; chevron only shown when the node has
  children.
- **Add session**: top "+" creates a root session (modal, no parent). A row's
  inline "+" or the dashed "+ Agregar sesión hija" creates a child under that
  node (modal, parent = that node). Any depth allowed.
- **New-session modal**: fields — **Nombre**; **Descripción** (optional
  textarea); **Ubicación** toggle **Repositorio | Directorio** → repo `<select>`
  or a directory-path `<input>`; **Rol** (optional `<select>`: Sin rol, Revisor,
  Arquitecto, Diseñador, Lector); **Branch** (optional). Cancel / "Crear sesión".
  Closes on `×` or backdrop click (inner panel stops propagation).
- **Rename** → double-click name → inline input (Enter/blur commit, Esc cancel).
- **Module switch** → icon rail sets the active panel.
- **Open file/task/branch/terminal/page** → push a de-duped tab (stable id per
  type) and activate it. **Close tab** → remove; if active, activate previous or
  Chat.
- **Graphite**: branch row expand → commits; commit expand → files; magnifier →
  Branch detail tab (stopPropagation so it doesn't toggle the row).
- **Terminal branch picker**: toggles open, search filters the repo's branches,
  selecting sets the terminal's branch and closes.
- **Notion**: "Nueva" adds a page (opens editable); editing title/body updates
  live.
- **Settings modal**: opens on any Customizations item; left nav lists all 8
  (selected highlighted), right pane shows the item's title/description/rows
  (each row a labeled item with a toggle switch). Closes on `×` / backdrop.
- **Send message**: clears the composer (demo — no real send).
- **Hover**: every interactive row/button/tab/chip has a hover state.
- **Blinking cursor**: `@keyframes blink` (step-end, ~1.1s) on the terminal
  prompt block.

## State Management (per workspace)
- `activeSessionId` — selected session (any depth).
- `sessions[]` — recursive tree (see Session model above).
- `editingSessionId`, `editingValue` — inline rename.
- `activeSidebarPanel` — `search | changes | graphite | tasks | terminal | notion`.
- `openTabs[]` (`{ id, type, label, refId?, dir?, branch?, repoId? }`,
  `type ∈ file | task | branch | terminal | page`), `activeTabId` (`'chat'` or id).
- `selectedBranches` (terminalTabId → branch), `branchPickerOpen`, `branchQuery`.
- `expandedBranches` (branchName→bool), `expandedCommits` (hash→bool).
- `pages[]` (`{ id, title, content }`).
- `newSessionOpen`, `newSessionForm` (`{ name, description, role, kind, repoId,
  dir, parentId|null, branch }`).
- `helperModalKey` (Customizations item, `null`=closed), `chatDraft`.

Real data sources: git repos & branches, worktree/session registry (recursive),
per-branch commit log + per-commit changed files, working-tree diff, task
markdown files, a docs/pages store, terminal PTY streams, and the agent chat
transport (messages carrying tool calls, edits, and per-message token usage).

## Design Tokens

### 1a — Terminal / amber
Fonts: UI `Inter`, code `JetBrains Mono`. App `#161513`, panel `#1c1a17`, title
`#131210`, terminal body `#0f0e0c`, agent bubble `#211e1a`. Borders `#332f28` /
`#2a2721`. Text primary `#f0ece4`, secondary `#cfc9bd`, muted `#75705f`/`#9c9488`.
Accent (amber) `#e0863f`; send-hover `#eb954f`; on-accent text `#161513`.
Selected session bg `#2e2820`, border `#e0863f`. Role pill `#e0863f` on `#2e2820`.
Toned-down chip: bg `#1a1714`, tool name `#bd925f`, dot `#a5703c`.
Diff add `rgba(127,176,105,.14)`/`#9fcf87`, del `rgba(201,106,78,.14)`/`#d89a89`,
`+`#7fb069 `-`#c96a4e. Radii 6–10px.

### 1b — Studio / indigo
Fonts: UI `Manrope`, code `IBM Plex Mono`. App `#181924`, panel `#1e1f2c`, title
`#14151f`, card `#232435`, terminal body `#12131c`, agent bubble `#20212f`.
Borders `#33344a` / `#2a2b3d`. Text primary `#eef0fb`, secondary
`#c3c5e0`/`#d6d7ec`, muted `#7274a0`/`#9294b3`. Accent (indigo) `#8b7bf0`;
send-hover `#9d8ff5`; on-accent text `#14151f`. Selected session bg `#2c2d44`,
border `#8b7bf0`. Role pill `#8b7bf0` on `#2c2d44`. Toned-down chip: bg `#1b1c28`,
tool name `#8079b8`, dot `#6a63a0`. Diff add `rgba(95,208,160,.14)`/`#8fe0bd`,
del `rgba(224,112,138,.14)`/`#e0a3b6`, `+`#5fd0a0 `-`#e0708a. Radii 9–18px.

### Shared scale
Type: UI 11–13px (labels 9–11px uppercase, tracked); code 10.5–12.5px; main
headings 18–27px. Spacing 4/6/8/10/12/14/16/20/24px. Icon-rail buttons 30–32px;
icons 14–16px, 2px stroke. Settings modal 760×540 (left nav 212px); new-session
modal ~440–460px wide. Session indentation 16px/level.

## Assets
- **No image assets.** All icons are inline stroke SVGs (feather-style): search,
  document/diff, stacked-layers (graphite), checklist (tasks), console
  (terminal), book (notion), git-branch, pencil (edit), clock (tokens),
  paper-plane (send), plus/`+`, and a generic circle used as the Customizations
  glyph. Reproduce with the codebase's icon set (lucide/feather); substitute
  meaningful icons for the Customizations list (home, code, bulb, book, bolt,
  server, plug, wrench).
- **Fonts** from Google Fonts: Inter, JetBrains Mono, Manrope, IBM Plex Mono.

## Files
- `Claude Code Mockup.dc.html` — the interactive prototype (directions 1a & 1b
  on one canvas). Open it to see live behavior; read its markup for exact
  structure and its logic class for the exact state model, the recursive
  session-tree helpers (`mapTree`, flatten/`walkTree`), and sample data.
