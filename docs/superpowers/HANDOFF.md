# Handoff — estado del proyecto (Agentic IDE)

> Última actualización: 2026-07-17. Documento vivo para retomar en otra sesión sin recontexto.

## Dónde estamos

**R6 Settings/Customizations: COMPLETO y mergeado a `main`.**

Rebanadas cerradas end-to-end: **R0** (fundación), **R1** (sesiones), **R2** (terminal),
**R3** (chat), **UI shadcn/1a** (identidad ámbar/terminal), **R6** (settings/customizations).

## Qué se construyó en R6 (último trabajo)

Footer de 9 items de customizations al pie del sidebar de sesiones + modal read-only con el
catálogo **global** de Claude Code (`~/.claude/*`, `~/.ide/config.toml`, PRESETS de roles),
marcando lo que está **en uso** en el workspace actual.

- **Backend** (`server/ide_server/customizations/`): lectores puros inyectables (`home: Path`)
  para roles, mcp, instructions, hooks, skills, agents, plugins, tools; `build_items` arma los
  9 items normalizados `{key, title, description, count, rows:[{label, inUse}]}`. Capability
  `customizations.list` registrada en `app.py`.
- **Frontend** (`ui/src/`): transport `transport/settingsChannel.ts` + store `state/settings.ts`
  (Zustand); `modules/settings/SettingsModal.tsx` (nav izq + panel der + badge "en uso");
  `modules/settings/CustomizationsFooter.tsx` (fetch al montar → 9 items clickeables) integrado
  en `modules/sessions/SessionsPanel.tsx`; modal montado en `App.tsx`.
- **Orden fijo de los 9 items**: `overview, roles, agents, skills, instructions, hooks, mcp,
  plugins, tools`.

Plan: `docs/superpowers/plans/2026-07-13-settings-customizations.md` (8 tareas, todas hechas).
Spec: `docs/superpowers/specs/2026-07-13-settings-customizations-design.md`.

## Verificación (verde al mergear)

- Backend: `cd server && uv run pytest -q` → **95 passed**.
- Frontend: `cd ui && npm test` → **80 passed (30 files)**; `npx tsc --noEmit` limpio; `npm run build` ok.
- E2E en vivo verificado con Playwright: footer con counts reales (Overview 8, Roles 4,
  Agents 15, Skills 2, Hooks 3, Plugins 3, Tools 12), modal de Roles con badge "en uso" en
  `lector` y `arquitecto` (roles asignados a sesiones del workspace demo `~/ide-demo`).

## Cómo correr

```bash
# backend + workspace demo (tiene .ide/ con sesiones sembradas)
cd server && uv run ide --cwd ~/ide-demo --no-browser
# frontend
cd ui && npm run dev   # http://localhost:5173  (backend en :8787)
```

## Próximos pasos (sin especificar aún — requieren brainstorming/spec antes de codear)

- **R4 — diffs / changed files** (ítem del rail "Changed files", hoy stub).
- **R5 — graphite / tasks / notion** (ítems del rail, hoy stubs "próximamente").
- Deuda menor: el `<aside>` de `SessionsPanel` es `overflow-auto` + footer `mt-auto`; con
  muchas sesiones el footer scrollea con el contenido (aceptable por ahora, no bloqueante).
- Chunk del build > 500 kB (warning de Vite, no error) — code-split si molesta.

## Reglas del repo (recordatorio)

- TDD estricto, un commit por tarea, conventional commits **en español**.
- Sin fallos silenciosos: errores viajan como envelope `{type:"error",...}`; el front muestra
  "desconectado", no datos viejos como vivos.
- UI: identidad **1a ámbar/terminal** vía shadcn/Tailwind, tokens en `docs/design/REFERENCES.md`.
- Claude Code local (login/suscripción), **sin `ANTHROPIC_API_KEY`**, no Managed Agents.
- Ver `CLAUDE.md` para las reglas completas y decisiones ya tomadas (no re-litigar).
