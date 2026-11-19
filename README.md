# Agentic IDE (working name)

Un IDE **agéntico** que corre en el **navegador (localhost)** para orquestar **sesiones
paralelas de Claude Code** sobre múltiples repos y git worktrees, cada una aislada.
Backend en **Python (FastAPI)**, frontend en **React + Vite**, terminales por
**WebSocket → xterm.js**. Todo pasa por **Claude Code local** con tu suscripción (sin
`ANTHROPIC_API_KEY`).

## Primeros pasos

> Si eres Claude y te pidieron instalar o configurar el IDE: sigue estos pasos en orden y
> después lee la referencia completa con `ide docs`.

### 1. Requisitos

| Herramienta | Para qué | Cómo |
|---|---|---|
| [`claude`](https://docs.claude.com/en/docs/claude-code) | las sesiones | instalado y logueado con tu suscripción (`claude` → `/login`) |
| [`uv`](https://docs.astral.sh/uv/) | instalar y correr el server | `brew install uv` |
| Node + npm | buildear la UI | `brew install node` |
| `git` | worktrees | — |
| [`gh`](https://cli.github.com/) | revisiones de PR y la sección Revisiones | `brew install gh` y `gh auth login` |
| [`ripgrep`](https://github.com/BurntSushi/ripgrep) | el buscador (opcional) | `brew install ripgrep` |

### 2. Instalar el comando `ide`

```bash
git clone https://github.com/topc01/ide.git && cd ide
(cd ui && npm install)
(cd server && uv run ide build)     # buildea la UI y la empaqueta dentro del server
uv tool install ./server            # deja `ide` en el PATH
```

Para actualizar después: `git pull`, repetir `ide build` y correr
`uv tool install --reinstall ./server`. Un `ide run` que ya está corriendo se reinicia solo con
la versión nueva.

### 3. Armar el workspace

El **workspace** es una carpeta que contiene tus repos clonados (cada subcarpeta con `.git` es
un repo) y la carpeta `.ide/` del IDE, que es local y no se commitea:

```
~/trabajo/
├── repo-a/
├── repo-b/
└── .ide/          # la crea `ide init` (o `ide run` si falta)
```

```bash
cd ~/trabajo
ide init           # siembra .ide/config.toml, plantillas, permisos y prompts (nunca pisa ediciones)
```

Revisa `.ide/config.toml` (nombre, permisos por defecto, tope de sesiones, org de GitHub) y,
si un repo necesita preparación al crear un worktree (copiar `.env`, instalar dependencias),
crea su script en `.ide/scripts/<repo>/setup` (ejecutable). Todo está en `ide docs`, §4 y §8.

### 4. Levantar

```bash
cd ~/trabajo && ide run      # abre http://127.0.0.1:8787
```

**Confianza de carpeta:** Claude Code pide confirmar cada carpeta nueva. Si una sesión muestra
**⚠ confiar carpeta**, entra a su terminal y acepta (el IDE nunca la acepta por ti).

### 5. Primer desarrollo

- En la sidebar principal, la **★** es la sesión principal: un `claude` desde el que despachas
  el resto.
- Pídele a la principal que cree una sesión por ticket (o hazlo tú desde una terminal:
  `ide session new --id <nombre> --prompt "…"`). Cada sesión suma los repos que necesita con
  `ide repo add <repo>`: un worktree por repo, en una rama propia.
- `ide --help` lista los comandos; `ide docs` explica cada uno.

Si algo falla, mira **«Problemas comunes»** en `ide docs` (§10).

## Documentación

- **`ide docs`** (`server/ide_server/REFERENCE.md`) — referencia completa para agentes y
  humanos: layout de `.ide/`, `config.toml`, permisos, plantillas, scripts, CLI, estados y errores.
- `docs/design/` — identidad visual, roadmap y referencias de diseño.

## Desarrollar el IDE

```bash
cd server && uv run ide run --cwd <workspace> --no-browser   # backend + frontend servido
cd ui && npm run dev                                          # Vite en :5173 con hot-reload
```

En dev abre `:5173` (Vite); el WebSocket del frontend siempre pega a `:8787`. Las reglas para
programar el IDE están en `CLAUDE.md`.

```bash
cd server && uv run pytest -q     # tests backend
cd ui && npm test                 # tests frontend (vitest)
```
