# R6 (parcial) — Settings / Customizations · Design

Fecha: 2026-07-13 · Estado: **aprobado** · Rebanada: parte de R6 del `docs/design/ROADMAP.md`
(footer Customizations + modal de Settings, read-only). Depende de: R0–R3 + fundación shadcn.

## Objetivo

El **footer de Customizations** al pie del sidebar de sesiones (handoff `§1.3`): lista vertical
de **9 items** (los 8 del handoff — Overview, Agents, Skills, Instructions, Hooks, MCP Servers,
Plugins, Tools — **+ Roles**, el que motivó esta rebanada); clickear cualquiera abre el **modal
de Settings** (nav izq + panel derecho). Muestra
el **catálogo global** de customizations de Claude Code (roles, skills, MCP, tools, etc.),
marcando cuáles están **en uso** en el workspace actual. **Read-only en esta rebanada.**

## Decisiones cerradas (2026-07-13)

1. **Scope global (nivel usuario), no por-workspace.** El catálogo es compartido entre
   workspaces — así un buen rol creado en una sesión se reusa en otros workspaces. Calza con
   cómo Claude Code guarda sus customizations (`~/.claude/`). Se marca qué entradas están **en
   uso** en el workspace actual.
2. **Read-only v1.** Sin escritura ni toggles activos. Editar / promover roles a global =
   rebanada siguiente (ahí entran toggles y forms). Los toggles del mockup del handoff eran demo.
3. **Aditivo, no re-litiga R1.** El roster global de roles es solo para *mostrar*; la resolución
   de rol por-sesión (`resolve_role` sobre `.ide/config.toml`) queda intacta. Unificar la
   resolución con el catálogo global es follow-up.

## Fuentes de datos (globales)

| Item | Fuente | "En uso" = |
|---|---|---|
| **Roles** | PRESETS built-in (`roles.py`) + `~/.ide/config.toml` (`[roles]`, global — nuevo) | roles asignados a alguna sesión del workspace actual (`sessions.json`) |
| **Instructions** | `~/.claude/CLAUDE.md` | — |
| **MCP Servers** | `~/.claude.json` clave `mcpServers` | — |
| **Skills** | dirs bajo `~/.claude/skills/` | — |
| **Agents** | archivos bajo `~/.claude/agents/` | — |
| **Hooks** | `~/.claude/settings.json` clave `hooks` | — |
| **Tools** | set built-in conocido de Claude Code (lista estática en código) | tools de `allowed_tools` de roles en uso |
| **Plugins** | dirs/manifiestos bajo `~/.claude/plugins/` | — |
| **Overview** | resumen (conteos de los anteriores) | — |

Cada lector es **tolerante a ausencia**: fuente inexistente → lista vacía → empty state
("no configurado"). Nunca se rompe ni expone secretos (p.ej. tokens de MCP no se muestran).
El home base es `Path.home()`; se resuelve una sola vez.

## Arquitectura

Cambio en **capa de datos + UI**, aditivo. No toca chat/terminal/sesiones existentes.

### Backend
| Unidad | Qué hace |
|--------|----------|
| `customizations/readers.py` | Un lector por fuente: `read_roles(home, workspace_root)`, `read_mcp(home)`, `read_skills(home)`, `read_instructions(home)`, `read_hooks(home)`, `read_agents(home)`, `read_plugins(home)`, `read_tools(roles_in_use)`. Cada uno devuelve `list[Row]` (`{label, inUse}`), tolerante a ausencia. Puros/testeables (reciben `home` y paths por parámetro). |
| `customizations/overview.py` | Arma el resumen (conteos por item). |
| `capabilities/customizations.py` | Canal WS `customizations.list` → devuelve `{items: [{key, title, description, count, rows:[{label, inUse}]}]}` para los 8 items (orden del handoff: overview, agents, skills, instructions, hooks, mcp, plugins, tools — roles se agrega). Usa `home = Path.home()` y el `root` del workspace para el in-use de roles. Registro en `app.py`. |

El in-use de roles: leer `sessions.json` del workspace, juntar los `role` asignados, marcar
esos en el roster global. Tools en uso = unión de `allowed_tools`/tools de los roles en uso.

### Frontend (shadcn/1a)
| Unidad | Qué hace |
|--------|----------|
| `modules/settings/CustomizationsFooter` | Lista vertical de 8 items (ícono + label + count opcional) al pie del `SessionsPanel`, borde superior. Click en un item → abre el modal con ese item seleccionado. |
| `modules/settings/SettingsModal` | shadcn `Dialog` (~760×540, nav izq 212px + panel derecho). Nav lista los items (activo resaltado); panel derecho muestra title/description + filas, cada fila con badge **"en uso"** cuando corresponde. Empty state por item sin datos. Cierra con `×`/backdrop. |
| `state/settings` | store: `items`, `open: boolean`, `selectedKey`, acciones `openSettings(key)`, `closeSettings`, `setData(items)`. |
| `transport/settingsChannel` | `fetchCustomizations(ws) -> Promise<items>` sobre `customizations.list`. |

## Flujo de datos

Montar `CustomizationsFooter` → `fetchCustomizations` (una vez) → store `items` → render del
footer con counts. Click en item → `openSettings(key)` → `SettingsModal` muestra ese item.
No hay escritura: el modal es de solo lectura.

## Manejo de errores

Sin fallos silenciosos: si `customizations.list` falla, el footer muestra los 8 items con count
0 / estado vacío (no datos viejos como vivos); un envelope `error` del transport se puede
loguear. Cada lector nunca lanza por ausencia de archivo (devuelve vacío); un archivo corrupto
se degrada a vacío para ese item, no tumba el resto.

## Testing

- **Backend (pytest):** cada lector con fixtures — `read_roles` combina PRESETS + `~/.ide/config.toml`
  y marca in-use cruzando un `sessions.json` de fixture; `read_mcp`/`read_instructions`/etc.
  parsean un `home` de fixture (tmp_path) y devuelven vacío cuando el archivo no existe. La
  capability arma los 8 items. (Todos reciben `home`/paths por parámetro — sin tocar el `~` real.)
- **Frontend (vitest/RTL):** footer renderiza 8 items con counts; click abre el modal en ese
  item; nav cambia de item; panel muestra filas + badge "en uso"; empty state; cerrar. Store
  y transport mockeado.

## Criterios de aceptación (hecho)

1. Footer de 9 items (los 8 del handoff + Roles) al pie del sidebar de sesiones, con counts
   reales donde hay datos.
2. Click en un item abre el modal de Settings en ese item (nav izq + panel derecho, 1a/shadcn).
3. Roles muestra el roster global (PRESETS + `~/.ide/config.toml`) con badge "en uso" para los
   asignados a sesiones del workspace actual.
4. Los demás items muestran su dato global real (donde la fuente existe) o empty state limpio.
5. Read-only: nada escribe; ningún secreto expuesto; tolerante a fuentes ausentes/corruptas.
6. Tests back + front verdes; `tsc` + build limpios.

## Fuera de alcance

- **Edición/escritura** de cualquier item (toggles activos, forms).
- **Promover** un rol de sesión al catálogo global.
- Unificar la resolución de roles per-workspace con el catálogo global.
- Datos de `~/.claude` caros/frágiles de leer (se muestran vacíos v1).
- Módulos Tasks/Notion de R6 (rebanadas aparte).

## Notas de ejecución

- Rama nueva `feat/settings-customizations` (sale de `main`).
- Los lectores reciben `home: Path` por parámetro (default `Path.home()` en la capability) para
  ser testeables con `tmp_path` sin tocar el `~/.claude` real de la máquina.
- Orden/íconos de los 8 items: seguir el handoff `§1.3` (Overview, Agents, Skills, Instructions,
  Hooks, MCP Servers, Plugins, Tools) + Roles.
