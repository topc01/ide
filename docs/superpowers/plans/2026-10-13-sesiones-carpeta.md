# Sesiones-carpeta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el núcleo de sesiones (árbol en `sessions.json`) por sesiones-carpeta en `.ide/sessions/<id>/` donde corre un `claude` interactivo, con repos como worktrees, scripts por repo, despacho por plantilla, cola `max_running`, revisiones de PR con polling y un sidebar simplificado.

**Architecture:** El disco es la fuente de verdad (`sessions_fs` puro lee/escribe el layout); el server es el único dueño de procesos (`Supervisor` sobre el `PtyManager` existente); un watcher (`watchfiles`) y un poller de PRs (`gh`) empujan `sessions.changed` por WS. El CLI `ide session|repo|script` hace disco in-process y procesos vía HTTP al server. La UI reemplaza el sidebar y, si `chat` no está en `[ui] modules`, el área principal pasa a vista por sesión (terminal `claude` + doc + scripts).

**Tech Stack:** Python 3.14 / FastAPI / `watchfiles` (ya instalado vía `uvicorn[standard]`) / `tomli-w` / `httpx` / argparse; React 19 + Vite + TS + zustand + shadcn/radix-ui (Tailwind 3) + xterm.

**Spec:** `docs/superpowers/specs/2026-10-13-sesiones-carpeta-design.md`

## Global Constraints

- Sin `ANTHROPIC_API_KEY`: las sesiones son el binario `claude` local (login de suscripción).
- Todo error del backend viaja como `{type:"error",payload:{code,message}}`; la UI muestra "desconectado", nunca datos viejos como vivos.
- `.ide/` es local, no se commitea. `ide init` siembra archivos **solo si no existen**.
- Kinds: `main | ticket | review`. Permisos: `analyze | full | default`. Una sola `main`.
- Status ticket: `analyzing · blocked · questions · ready · in-progress · done`; review: `reviewing · commented · approved · changes-requested`. Derivados (no se escriben a archivo): `queued` (proceso), `stale | merged | closed` (poller).
- `config.toml`: `[sessions] default_permissions = "analyze"`, `max_running` (omitido = sin tope), `claude_command = "claude"`; `[reviews] poll_interval = 300` (0 = off); `[ui] modules = ["sessions", "terminal"]`.
- Scripts: `.ide/scripts/<repo>/<name>` ejecutables; reservados `setup` y `archive`. Env: `IDE_SESSION_ID`, `IDE_REPO`, `IDE_ROOT_REPO`, `IDE_WORKSPACE`, `IDE_PORT` (bloque de 10 desde 8100, por sesión+repo).
- Worktrees reales en `.ide/worktrees/<id>/<repo>`; symlink relativo `sessions/<id>/<repo> -> ../../worktrees/<id>/<repo>`. Branch default = `<id>`.
- Identidad visual 1a vía shadcn tematizado; copy en español.
- TDD; commits convencionales en español, uno por tarea, terminando con `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Tests: `cd server && uv run pytest -q` (baseline 336 verdes) · `cd ui && npm test` (baseline 194 verdes).

## Review Focus

1. **Ids de ticket con mayúsculas** (`FIN-123` de Notion) → se normalizan a slug (`fin-123`) en vez de rechazarse; el CLI imprime el id final. Test en Task 1 y Task 8.
2. **`ide repo add` desde dentro de un worktree** (cwd resuelto `.ide/worktrees/<id>/repo`, sin `IDE_SESSION_ID`) → igual resuelve la sesión. Test en Task 12.
3. **Carpeta basura en `sessions/`** (sin `.session.toml`, o `TICKET.md` con frontmatter roto) → aparece con `error`, no se oculta ni rompe el listado. Test en Task 2.
4. **Cambiar de sesión en la UI y volver** → la salida de la terminal `claude` no se pierde (las terminales visitadas quedan montadas) y no se duplican listeners. Test en Task 17.
5. **`rm` de una sesión con proceso vivo y repos sucios** → se niega antes de tocar nada (ningún repo a medio borrar); con `--force` mata el proceso antes de quitar worktrees. Test en Task 8 y Task 11.

---

### Task 0: Spike de supuestos de `claude` (sin código que quede)

**Files:**
- Create: `docs/superpowers/spikes/2026-10-13-claude-cli-spike.md`

- [ ] **Step 1: Armar un workspace de prueba**

```bash
SP=$(mktemp -d) && mkdir -p $SP/.ide/sessions/s1 $SP/.ide/permissions
printf '# Mapa\nEl repo foo hace X. Palabra clave: PINGÜINO.\n' > $SP/.ide/sessions/CLAUDE.md
cat > $SP/.ide/permissions/analyze.json <<'EOF'
{"permissions": {"allow": ["Read", "Bash(echo:*)", "Edit(**/TICKET.md)", "Write(**/TICKET.md)"], "deny": ["Bash(rm:*)"]}}
EOF
echo $SP
```

- [ ] **Step 2: Verificar herencia de CLAUDE.md y `--settings` desde carpeta no-git**

```bash
cd $SP/.ide/sessions/s1 && claude --settings $SP/.ide/permissions/analyze.json -p "¿Cuál es la palabra clave de tu CLAUDE.md? Después ejecuta: echo hola, y crea TICKET.md con 'x'."
```
Expected: menciona PINGÜINO; `echo` y `TICKET.md` sin pedir permiso (en `-p` lo no permitido falla). Anotar resultado.

- [ ] **Step 3: Verificar `--continue` por cwd y el encoding de `~/.claude/projects`**

```bash
cd $SP/.ide/sessions/s1 && claude -p "Recuerda el número 4711." >/dev/null && claude --continue -p "¿Qué número te pide recordar?"
ls ~/.claude/projects | grep -i "$(basename $SP)"
```
Expected: responde 4711; el dir de proyecto es la ruta con todo lo no-alfanumérico reemplazado por `-` (ej. `/private/var/.../.ide/sessions/s1` → `-private-var-...--ide-sessions-s1`). Anotar la regla exacta (si difiere de `re.sub(r"[^A-Za-z0-9]", "-", str(path))`, ajustar `encode_project_dir` en Task 6).

- [ ] **Step 4: Verificar Notion y bypass**

```bash
cd $SP/.ide/sessions/s1 && claude -p "Lista tus herramientas MCP cuyo nombre contenga Notion (solo nombres)."
cd $SP/.ide/sessions/s1 && claude --permission-mode bypassPermissions -p "Ejecuta: echo bypass-ok"
```
Expected: aparecen `mcp__claude_ai_Notion__*` (anotar los nombres exactos de fetch/search/query para la semilla de `analyze.json` en Task 3); `bypass-ok` sin diálogo. Si bypass pide aceptación interactiva la primera vez, anotarlo (se acepta una vez a mano).

- [ ] **Step 5: Escribir el resultado y commitear**

Escribir `docs/superpowers/spikes/2026-10-13-claude-cli-spike.md` con una sección por supuesto: comando, salida resumida, ✅/❌, y ajuste requerido. **Fallback ya decidido si `--settings` no aplica:** el supervisor copia el perfil a `sessions/<id>/.claude/settings.json` (raíz de proyecto = cwd no-git) en vez de pasar `--settings`; anotarlo para Task 6.

```bash
git add docs/superpowers/spikes/2026-10-13-claude-cli-spike.md
git commit -m "docs(spike): supuestos de claude CLI para sesiones-carpeta

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 1: `sessions_fs` — errores, ids, frontmatter, plantillas

**Files:**
- Create: `server/ide_server/sessions_fs.py`
- Test: `server/tests/test_sessions_fs_basics.py`

**Interfaces:**
- Produces: `SessionError(code: str, message: str)` (atributo `.code`); `KINDS`, `PERMISSIONS`; `normalize_id(raw: str) -> str` (slug + valida, lanza `SessionError("invalid_id")`); `new_id(exists: Callable[[str], bool]) -> str` (`s-xxxxx`); `parse_frontmatter(text) -> tuple[dict[str,str], str]` (lanza `SessionError("bad_frontmatter")`); `write_frontmatter(meta: dict, body: str) -> str`; `render_template(text, variables: dict) -> str` (lanza `SessionError("missing_vars")`).

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_sessions_fs_basics.py
import pytest
from ide_server.sessions_fs import (
    SessionError, normalize_id, new_id, parse_frontmatter, write_frontmatter, render_template,
)


def test_normalize_id_slugs_ticket_ids():
    assert normalize_id("FIN-123") == "fin-123"
    assert normalize_id("  Mi Ticket #7 ") == "mi-ticket-7"


@pytest.mark.parametrize("raw", ["", "---", "templates", "x" * 64])
def test_normalize_id_rejects(raw):
    with pytest.raises(SessionError) as e:
        normalize_id(raw)
    assert e.value.code == "invalid_id"


def test_new_id_skips_existing():
    seen = []
    sid = new_id(lambda s: (seen.append(s), len(seen) < 3)[1])
    assert sid.startswith("s-") and len(sid) == 7 and len(seen) == 3


def test_frontmatter_roundtrip_with_urls():
    text = write_frontmatter({"status": "ready", "notion_url": "https://n.so/a:b"}, "## Scope\n")
    meta, body = parse_frontmatter(text)
    assert meta == {"status": "ready", "notion_url": "https://n.so/a:b"}
    assert body == "## Scope\n"


def test_frontmatter_absent_returns_empty():
    assert parse_frontmatter("hola") == ({}, "hola")


def test_frontmatter_newlines_in_values_are_flattened():
    meta, _ = parse_frontmatter(write_frontmatter({"title": "a\nb"}, ""))
    assert meta["title"] == "a b"


@pytest.mark.parametrize("text", ["---\nstatus: x\n", "---\nsin dos puntos\n---\n"])
def test_frontmatter_broken(text):
    with pytest.raises(SessionError) as e:
        parse_frontmatter(text)
    assert e.value.code == "bad_frontmatter"


def test_render_template_ok_and_missing():
    assert render_template("T {{id}}: {{ title }}", {"id": "x", "title": "y"}) == "T x: y"
    with pytest.raises(SessionError) as e:
        render_template("{{a}} {{b}}", {"a": 1})
    assert e.value.code == "missing_vars" and "b" in str(e.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_sessions_fs_basics.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ide_server.sessions_fs'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/sessions_fs.py
from __future__ import annotations
import re
import secrets
import string
from typing import Callable
from ide_server.sessions_store import slugify

KINDS = ("main", "ticket", "review")
PERMISSIONS = ("analyze", "full", "default")
RESERVED = {"templates"}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class SessionError(Exception):
    """Error de dominio de sesiones-carpeta (viaja como envelope con .code)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_id(raw: str) -> str:
    sid = slugify(raw)
    if sid in RESERVED or not _ID_RE.match(sid):
        raise SessionError("invalid_id",
                           f"id inválido: {raw!r} (letras, dígitos y '-', máx. 63)")
    return sid


def new_id(exists: Callable[[str], bool]) -> str:
    alphabet = string.ascii_lowercase + string.digits
    for _ in range(100):
        sid = "s-" + "".join(secrets.choice(alphabet) for _ in range(5))
        if not exists(sid):
            return sid
    raise SessionError("id_exhausted", "no se pudo generar un id libre")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        raise SessionError("bad_frontmatter", "frontmatter sin cierre '---'")
    meta: dict[str, str] = {}
    for n, line in enumerate(text[4:end].splitlines(), start=2):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            raise SessionError("bad_frontmatter", f"línea {n} inválida: {line!r}")
        meta[key.strip()] = value.strip()
    return meta, text[end + 4:].lstrip("\n")


def write_frontmatter(meta: dict, body: str) -> str:
    lines = [f"{k}: {' '.join(str(v).split())}" for k, v in meta.items() if v is not None]
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def render_template(text: str, variables: dict) -> str:
    missing = sorted({m.group(1) for m in _VAR_RE.finditer(text)} - set(variables))
    if missing:
        raise SessionError("missing_vars", "faltan variables: " + ", ".join(missing))
    return _VAR_RE.sub(lambda m: str(variables[m.group(1)]), text)
```

Nota: `"---"` como id → `slugify` da `""` → inválido. `"x"*64` → 64 chars → inválido.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_sessions_fs_basics.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/sessions_fs.py server/tests/test_sessions_fs_basics.py
git commit -m "feat(sesiones): sessions_fs básico (ids, frontmatter, plantillas)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `sessions_fs` — crear/leer/listar sesiones + config

**Files:**
- Modify: `server/ide_server/sessions_fs.py`
- Modify: `server/ide_server/config.py`
- Test: `server/tests/test_sessions_fs_layout.py`, `server/tests/test_config_sessions.py`

**Interfaces:**
- Consumes: Task 1.
- Produces (sessions_fs): `sessions_dir(root) -> Path`; `session_path(root, sid) -> Path`; `state_file(kind) -> str | None` (`TICKET.md`/`REVIEW.md`); `read_toml(path) -> dict`; `write_toml(path, data)`; `update_session_toml(root, sid, fn: Callable[[dict], None]) -> dict`; `find_main(root) -> str | None`; `create_session_dir(root, *, sid, kind, permissions, prompt, meta=None, now=None) -> Path` (lanza `session_exists`, `main_exists`, `invalid_kind`, `invalid_permissions`); `read_session(root, sid) -> dict`; `list_sessions(root) -> list[dict]`.
- Session dict: `{"id","kind","path","created","permissions","title","status","meta":{...},"repos":[{"name","state":"ok"|"missing","branch","port","setup"}],"prUrl","reviewedSha","error"}`.
- Produces (config): `sessions_config(root) -> {"default_permissions","max_running","claude_command"}` (ValueError si permisos inválidos); `reviews_config(root) -> {"poll_interval": int}`; `ui_modules(root) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_config_sessions.py
import pytest
from ide_server.config import sessions_config, reviews_config, ui_modules


def _cfg(tmp_path, text=""):
    (tmp_path / ".ide").mkdir(exist_ok=True)
    (tmp_path / ".ide" / "config.toml").write_text(text)
    return tmp_path


def test_defaults(tmp_path):
    root = _cfg(tmp_path)
    assert sessions_config(root) == {"default_permissions": "analyze", "max_running": None,
                                     "claude_command": "claude"}
    assert reviews_config(root) == {"poll_interval": 300}
    assert ui_modules(root) == ["sessions", "terminal"]


def test_overrides(tmp_path):
    root = _cfg(tmp_path, '[sessions]\ndefault_permissions = "full"\nmax_running = 3\n'
                          '[reviews]\npoll_interval = 0\n[ui]\nmodules = ["sessions", "chat"]\n')
    assert sessions_config(root)["default_permissions"] == "full"
    assert sessions_config(root)["max_running"] == 3
    assert reviews_config(root)["poll_interval"] == 0
    assert ui_modules(root) == ["sessions", "chat"]


def test_bad_permissions(tmp_path):
    root = _cfg(tmp_path, '[sessions]\ndefault_permissions = "yolo"\n')
    with pytest.raises(ValueError, match="default_permissions"):
        sessions_config(root)
```

```python
# server/tests/test_sessions_fs_layout.py
import pytest
from datetime import datetime
from ide_server.sessions_fs import (
    SessionError, create_session_dir, read_session, list_sessions, session_path,
    update_session_toml, find_main, read_toml,
)

T0 = datetime(2026, 10, 13, 10, 0, 0)
T1 = datetime(2026, 10, 13, 11, 0, 0)


def test_create_ticket_seeds_files(tmp_path):
    p = create_session_dir(tmp_path, sid="fin-1", kind="ticket", permissions="analyze",
                           prompt="haz X", meta={"title": "Exportar", "notion_url": "https://n"},
                           now=T0)
    assert p == session_path(tmp_path, "fin-1")
    assert read_toml(p / ".session.toml") == {"kind": "ticket", "permissions": "analyze",
                                              "created": "2026-10-13T10:00:00"}
    assert (p / "PROMPT.md").read_text() == "haz X"
    s = read_session(tmp_path, "fin-1")
    assert s["status"] == "analyzing" and s["title"] == "Exportar"
    assert s["meta"] == {"notion_url": "https://n"} and s["error"] is None


def test_review_seeds_reviewing(tmp_path):
    create_session_dir(tmp_path, sid="pr-a-1", kind="review", permissions="analyze", prompt="")
    assert read_session(tmp_path, "pr-a-1")["status"] == "reviewing"


def test_main_has_no_state_file_and_is_unique(tmp_path):
    p = create_session_dir(tmp_path, sid="s-aaaaa", kind="main", permissions="full", prompt="")
    assert not (p / "TICKET.md").exists()
    assert find_main(tmp_path) == "s-aaaaa"
    with pytest.raises(SessionError) as e:
        create_session_dir(tmp_path, sid="s-bbbbb", kind="main", permissions="full", prompt="")
    assert e.value.code == "main_exists" and "s-aaaaa" in str(e.value)


def test_duplicate_and_invalid(tmp_path):
    create_session_dir(tmp_path, sid="a", kind="ticket", permissions="analyze", prompt="")
    with pytest.raises(SessionError) as e:
        create_session_dir(tmp_path, sid="a", kind="ticket", permissions="analyze", prompt="")
    assert e.value.code == "session_exists"
    for kw, code in [({"kind": "otro"}, "invalid_kind"), ({"permissions": "x"}, "invalid_permissions")]:
        args = {"sid": "b", "kind": "ticket", "permissions": "analyze", "prompt": "", **kw}
        with pytest.raises(SessionError) as e:
            create_session_dir(tmp_path, **args)
        assert e.value.code == code
    assert not session_path(tmp_path, "b").exists()


def test_list_orders_main_first_then_created(tmp_path):
    create_session_dir(tmp_path, sid="t2", kind="ticket", permissions="analyze", prompt="", now=T1)
    create_session_dir(tmp_path, sid="t1", kind="ticket", permissions="analyze", prompt="", now=T0)
    create_session_dir(tmp_path, sid="m", kind="main", permissions="analyze", prompt="", now=T1)
    (session_path(tmp_path, "t1").parent / "templates").mkdir()
    assert [s["id"] for s in list_sessions(tmp_path)] == ["m", "t1", "t2"]


def test_garbage_dirs_surface_with_error(tmp_path):            # Review Focus 3
    create_session_dir(tmp_path, sid="ok", kind="ticket", permissions="analyze", prompt="")
    (session_path(tmp_path, "basura")).mkdir()
    rota = create_session_dir(tmp_path, sid="rota", kind="ticket", permissions="analyze", prompt="")
    (rota / "TICKET.md").write_text("---\nstatus ready\n---\n")
    toml_mal = create_session_dir(tmp_path, sid="tm", kind="ticket", permissions="analyze", prompt="")
    (toml_mal / ".session.toml").write_text("kind = ")
    by_id = {s["id"]: s for s in list_sessions(tmp_path)}
    assert by_id["ok"]["error"] is None
    assert "falta .session.toml" in by_id["basura"]["error"]
    assert "TICKET.md" in by_id["rota"]["error"]
    assert ".session.toml inválido" in by_id["tm"]["error"]


def test_repos_from_symlinks(tmp_path):
    p = create_session_dir(tmp_path, sid="t", kind="ticket", permissions="analyze", prompt="")
    real = tmp_path / "wt"; real.mkdir()
    (p / "repo-a").symlink_to(real)
    (p / "repo-b").symlink_to(tmp_path / "no-existe")
    update_session_toml(tmp_path, "t", lambda d: d.setdefault("ports", {}).update({"repo-a": 8100}))
    repos = read_session(tmp_path, "t")["repos"]
    assert repos == [
        {"name": "repo-a", "state": "ok", "branch": None, "port": 8100, "setup": None},
        {"name": "repo-b", "state": "missing", "branch": None, "port": None, "setup": None},
    ]
```

(`branch` es `None` en `repo-a` porque el dir no es git; con un worktree real devuelve la branch.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest tests/test_config_sessions.py tests/test_sessions_fs_layout.py -q`
Expected: FAIL con `ImportError` (`sessions_config`, `create_session_dir`).

- [ ] **Step 3: Implement config accessors** (agregar al final de `server/ide_server/config.py`)

```python
SESSION_DEFAULTS = {"default_permissions": "analyze", "max_running": None,
                    "claude_command": "claude"}


def sessions_config(root: Path) -> dict:
    cfg = {**SESSION_DEFAULTS, **load_workspace_config(root).get("sessions", {})}
    if cfg["default_permissions"] not in ("analyze", "full", "default"):
        raise ValueError(f"[sessions] default_permissions inválido: "
                         f"{cfg['default_permissions']!r} (analyze | full | default)")
    return cfg


def reviews_config(root: Path) -> dict:
    return {"poll_interval": 300, **load_workspace_config(root).get("reviews", {})}


def ui_modules(root: Path) -> list[str]:
    return list(load_workspace_config(root).get("ui", {}).get("modules", ["sessions", "terminal"]))
```

- [ ] **Step 4: Implement layout functions** (agregar a `server/ide_server/sessions_fs.py`)

```python
import shutil
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path
import tomli_w


def sessions_dir(root: Path) -> Path:
    return root / ".ide" / "sessions"


def session_path(root: Path, sid: str) -> Path:
    return sessions_dir(root) / sid


def state_file(kind: str | None) -> str | None:
    return {"ticket": "TICKET.md", "review": "REVIEW.md"}.get(kind or "")


def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def write_toml(path: Path, data: dict) -> None:
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def update_session_toml(root: Path, sid: str, fn: Callable[[dict], None]) -> dict:
    path = session_path(root, sid) / ".session.toml"
    data = read_toml(path)
    fn(data)
    write_toml(path, data)
    return data


def find_main(root: Path) -> str | None:
    d = sessions_dir(root)
    if not d.is_dir():
        return None
    for p in sorted(d.iterdir()):
        try:
            if read_toml(p / ".session.toml").get("kind") == "main":
                return p.name
        except (OSError, tomllib.TOMLDecodeError):
            continue
    return None


def create_session_dir(root: Path, *, sid: str, kind: str, permissions: str, prompt: str,
                       meta: dict | None = None, now: datetime | None = None) -> Path:
    if kind not in KINDS:
        raise SessionError("invalid_kind", f"kind inválido: {kind!r}")
    if permissions not in PERMISSIONS:
        raise SessionError("invalid_permissions",
                           f"permisos inválidos: {permissions!r} (analyze | full | default)")
    path = session_path(root, sid)
    if path.exists():
        raise SessionError("session_exists", f"ya existe la sesión {sid}")
    if kind == "main" and (m := find_main(root)):
        raise SessionError("main_exists", f"ya existe la principal {m}; usa `ide session open {m}`")
    path.mkdir(parents=True)
    try:
        write_toml(path / ".session.toml", {
            "kind": kind, "permissions": permissions,
            "created": (now or datetime.now()).isoformat(timespec="seconds")})
        (path / "PROMPT.md").write_text(prompt, encoding="utf-8")
        sf = state_file(kind)
        if sf:
            first = "analyzing" if kind == "ticket" else "reviewing"
            (path / sf).write_text(write_frontmatter({"status": first, **(meta or {})}, ""),
                                   encoding="utf-8")
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise
    return path


def _branch(path: Path) -> str | None:
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def read_session(root: Path, sid: str) -> dict:
    path = session_path(root, sid)
    info: dict = {"id": sid, "kind": None, "path": str(path), "created": "", "permissions": None,
                  "title": None, "status": None, "meta": {}, "repos": [], "prUrl": None,
                  "reviewedSha": None, "error": None}
    try:
        data = read_toml(path / ".session.toml")
    except FileNotFoundError:
        info["error"] = "falta .session.toml"
        return info
    except tomllib.TOMLDecodeError as exc:
        info["error"] = f".session.toml inválido: {exc}"
        return info
    info.update(kind=data.get("kind"), permissions=data.get("permissions"),
                created=str(data.get("created", "")), prUrl=data.get("pr_url"),
                reviewedSha=data.get("reviewed_sha"))
    ports, setup = data.get("ports", {}), data.get("setup", {})
    for link in sorted(p for p in path.iterdir() if p.is_symlink()):
        ok = link.exists()
        info["repos"].append({"name": link.name, "state": "ok" if ok else "missing",
                              "branch": _branch(link) if ok else None,
                              "port": ports.get(link.name), "setup": setup.get(link.name)})
    sf = state_file(info["kind"])
    if sf and (path / sf).is_file():
        try:
            meta, _ = parse_frontmatter((path / sf).read_text(encoding="utf-8"))
            info["status"] = meta.pop("status", None)
            info["title"] = meta.pop("title", None)
            info["meta"] = meta
        except SessionError as exc:
            info["error"] = f"{sf}: {exc}"
    return info


def list_sessions(root: Path) -> list[dict]:
    d = sessions_dir(root)
    if not d.is_dir():
        return []
    items = [read_session(root, p.name) for p in d.iterdir()
             if p.is_dir() and not p.is_symlink() and p.name not in RESERVED
             and not p.name.startswith(".")]
    return sorted(items, key=lambda s: (s["kind"] != "main", s["created"], s["id"]))
```

Nota: `_branch` sobre un dir no-git dentro de `tmp_path` puede encontrar un repo padre; en el test `tmp_path` no es repo, así que da `None`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && uv run pytest tests/test_config_sessions.py tests/test_sessions_fs_layout.py tests/test_sessions_fs_basics.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/ide_server/sessions_fs.py server/ide_server/config.py server/tests/test_sessions_fs_layout.py server/tests/test_config_sessions.py
git commit -m "feat(sesiones): crear/leer/listar sesiones-carpeta + config [sessions]/[reviews]/[ui]

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Semillas de `ide init`

**Files:**
- Create: `server/ide_server/seeds.py`
- Modify: `server/ide_server/sessions_fs.py` (agregar `seed_workspace`)
- Modify: `server/ide_server/cli.py:15-22` (`init_workspace`)
- Test: `server/tests/test_seed_workspace.py`

**Interfaces:**
- Consumes: Task 2 (`sessions_dir`), `workspace.discover_repos`.
- Produces: `seed_workspace(root) -> list[Path]` (rutas creadas; nunca pisa). Archivos: `.ide/sessions/CLAUDE.md`, `.ide/sessions/templates/{main,ticket,review}.md`, `.ide/permissions/{analyze,full}.json`, dirs `.ide/scripts/`, `.ide/worktrees/`. `init_workspace` ya no crea `tasks/`; el `config.toml` nuevo incluye `[sessions]`, `[reviews]`, `[ui]`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_seed_workspace.py
import json, subprocess
from ide_server.sessions_fs import seed_workspace, render_template
from ide_server.cli import init_workspace
from ide_server.config import sessions_config, ui_modules


def _repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)


def test_seed_creates_files_with_repo_map(tmp_path):
    _repo(tmp_path / "repo-a"); _repo(tmp_path / "repo-b")
    seed_workspace(tmp_path)
    ide = tmp_path / ".ide"
    claude_md = (ide / "sessions" / "CLAUDE.md").read_text()
    assert "repo-a" in claude_md and "repo-b" in claude_md and "ide repo add" in claude_md
    for name in ("main", "ticket", "review"):
        assert (ide / "sessions" / "templates" / f"{name}.md").is_file()
    analyze = json.loads((ide / "permissions" / "analyze.json").read_text())
    assert "Bash(ide repo add:*)" in analyze["permissions"]["allow"]
    assert json.loads((ide / "permissions" / "full.json").read_text())
    assert (ide / "scripts").is_dir() and (ide / "worktrees").is_dir()


def test_seed_never_overwrites(tmp_path):
    seed_workspace(tmp_path)
    md = tmp_path / ".ide" / "sessions" / "CLAUDE.md"
    md.write_text("mío")
    created = seed_workspace(tmp_path)
    assert md.read_text() == "mío" and created == []


def test_ticket_template_renders_with_dispatch_vars(tmp_path):
    seed_workspace(tmp_path)
    tpl = (tmp_path / ".ide" / "sessions" / "templates" / "ticket.md").read_text()
    out = render_template(tpl, {"id": "fin-1", "title": "T", "notion_url": "u", "body": "b"})
    assert "fin-1" in out and "TICKET.md" in out


def test_init_workspace_seeds_and_config(tmp_path):
    init_workspace(tmp_path)
    assert (tmp_path / ".ide" / "sessions" / "CLAUDE.md").is_file()
    assert not (tmp_path / ".ide" / "tasks").exists()
    assert sessions_config(tmp_path)["default_permissions"] == "analyze"
    assert ui_modules(tmp_path) == ["sessions", "terminal"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_seed_workspace.py -q`
Expected: FAIL con `ImportError: cannot import name 'seed_workspace'`

- [ ] **Step 3: Write `seeds.py`**

Usar los nombres exactos de tools de Notion que anotó el spike (Task 0, Step 4); los de abajo son los esperados.

```python
# server/ide_server/seeds.py
"""Contenido sembrado por `ide init` (solo si no existe; el usuario lo edita)."""
from __future__ import annotations

CONFIG_TOML = """\
name = "{name}"

[sessions]
default_permissions = "analyze"   # analyze | full | default
# max_running = 5                 # tope de `claude` corriendo a la vez (omitido = sin tope)
claude_command = "claude"

[reviews]
poll_interval = 300               # segundos; 0 = sin polling de PRs

[ui]
modules = ["sessions", "terminal"]
"""


def claude_md(repos: list[str]) -> str:
    lines = "\n".join(f"- `{r}`: (describe qué hace este repo)" for r in repos) or "- (sin repos)"
    return f"""\
# Workspace

Estás en una sesión del IDE (`.ide/sessions/<id>/`). Los repos del workspace:

{lines}

## Herramientas del IDE (por Bash)

- `ide repo add <repo> [--branch b]`: agrega el repo a tu sesión como worktree (corre su `setup`).
- `ide repo rm <repo>`: lo quita.
- `ide script <nombre> [<repo>]`: corre un script del repo (`run`, `test`, …).
- `ide session ls [--json]`: lista sesiones y su estado.
- `ide session new --id <id> --template ticket --var title=… --var notion_url=… --var body=…`:
  (solo la principal) lanza una sesión por ticket.
- `ide session new --review <pr-url>`: (solo la principal) lanza una revisión de PR.

## Convención de estado

Las sesiones de ticket mantienen `TICKET.md` (frontmatter `status`:
analyzing | blocked | questions | ready | in-progress | done). Las de revisión, `REVIEW.md`
(reviewing | commented | approved | changes-requested). Solo cambia `status` y el cuerpo.
"""


TEMPLATE_MAIN = """\
Eres la sesión principal de este workspace.

1. Lee mi backlog en Notion: <URL de la base de tickets> (asignados a mí, no Done).
2. Ejecuta `ide session ls --json` y omite los tickets que ya tienen sesión (id = id del ticket).
3. Por cada ticket nuevo:
   `ide session new --id <ticket-id> --template ticket --var title="…" --var notion_url="…" --var body="…"`
4. PRs donde me pidieron review: `gh search prs --review-requested=@me --state=open --json url`.
   Por cada uno sin sesión: `ide session new --review <url>`.
5. Resume lo que lanzaste. Para ver el estado de todo: lee `../*/TICKET.md` y `../*/REVIEW.md`.
"""

TEMPLATE_TICKET = """\
Eres la sesión del ticket {{id}}: "{{title}}" ({{notion_url}}).

{{body}}

Tu trabajo AHORA es analizar, no implementar:
1. Lee ../CLAUDE.md (mapa de repos) y el ticket en Notion.
2. Determina scope y qué repos toca. Por cada uno: `ide repo add <repo>`.
3. Escribe TICKET.md: Scope, Repos, Plan, Bloqueantes, Dudas.
   Cambia `status` a blocked | questions | ready.
4. Detente y espera instrucciones.
"""

TEMPLATE_REVIEW = """\
Eres la revisión del PR {{pr_url}} ("{{title}}", de {{author}}) en el repo {{repo}}.
El worktree `{{repo}}/` está en el head del PR (detached).

1. Revisa el diff contra la base (`gh pr diff {{pr_url}}`, y lee el código alrededor).
2. Escribe REVIEW.md con hallazgos por severidad (bloqueante / importante / menor / nit).
3. Cambia `status` a commented | approved | changes-requested según tu veredicto.
4. NO publiques nada en GitHub sin que te lo pida.
"""

PERM_ANALYZE = {"permissions": {
    "allow": [
        "Read", "Grep", "Glob",
        "Bash(git log:*)", "Bash(git diff:*)", "Bash(git show:*)", "Bash(git status:*)",
        "Bash(ide repo add:*)", "Bash(ide script:*)", "Bash(ide session ls:*)",
        "Bash(ide session new:*)",
        "Bash(gh pr view:*)", "Bash(gh pr diff:*)", "Bash(gh search prs:*)",
        "Edit(**/TICKET.md)", "Write(**/TICKET.md)", "Edit(**/REVIEW.md)", "Write(**/REVIEW.md)",
        "mcp__claude_ai_Notion__notion-fetch", "mcp__claude_ai_Notion__notion-search",
        "mcp__claude_ai_Notion__notion-query-data-sources",
    ],
    "deny": [],
}}

PERM_FULL = {"permissions": {"defaultMode": "bypassPermissions"}}
```

- [ ] **Step 4: Add `seed_workspace` and update `init_workspace`**

En `server/ide_server/sessions_fs.py`:

```python
import json


def seed_workspace(root: Path) -> list[Path]:
    from ide_server import seeds
    from ide_server.workspace import discover_repos
    ide = root / ".ide"
    for d in (ide / "scripts", ide / "worktrees", sessions_dir(root) / "templates",
              ide / "permissions"):
        d.mkdir(parents=True, exist_ok=True)
    files = {
        sessions_dir(root) / "CLAUDE.md": seeds.claude_md([r["id"] for r in discover_repos(root)]),
        sessions_dir(root) / "templates" / "main.md": seeds.TEMPLATE_MAIN,
        sessions_dir(root) / "templates" / "ticket.md": seeds.TEMPLATE_TICKET,
        sessions_dir(root) / "templates" / "review.md": seeds.TEMPLATE_REVIEW,
        ide / "permissions" / "analyze.json": json.dumps(seeds.PERM_ANALYZE, indent=2) + "\n",
        ide / "permissions" / "full.json": json.dumps(seeds.PERM_FULL, indent=2) + "\n",
    }
    created = []
    for path, content in files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(path)
    return created
```

En `server/ide_server/cli.py`, reemplazar `init_workspace`:

```python
def init_workspace(cwd: Path) -> Path:
    from ide_server import seeds
    from ide_server.sessions_fs import seed_workspace
    ide = cwd / ".ide"
    ide.mkdir(parents=True, exist_ok=True)
    cfg = ide / "config.toml"
    if not cfg.exists():
        cfg.write_text(seeds.CONFIG_TOML.format(name=cwd.name))
    seed_workspace(cwd)
    return ide
```

- [ ] **Step 5: Run tests**

Run: `cd server && uv run pytest tests/test_seed_workspace.py tests/test_cli.py -q`
Expected: PASS. Si algún test existente asume `.ide/tasks/` creado por `init`, el módulo tasks crea su dir al guardar (verificar con `grep -n "mkdir" server/ide_server/tasks/store.py`); si no lo crea, agregar `dir.mkdir(parents=True, exist_ok=True)` en su función de guardado.

- [ ] **Step 6: Commit**

```bash
git add server/ide_server/seeds.py server/ide_server/sessions_fs.py server/ide_server/cli.py server/tests/test_seed_workspace.py
git commit -m "feat(sesiones): ide init siembra CLAUDE.md, plantillas y perfiles de permisos

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `repos_fs` — worktrees + symlinks + puertos

**Files:**
- Create: `server/ide_server/repos_fs.py`
- Test: `server/tests/test_repos_fs.py`

**Interfaces:**
- Consumes: `worktrees.add_worktree/remove_worktree/has_uncommitted_changes/BranchOccupied`, `workspace.discover_repos`, Task 2.
- Produces: `PORT_BASE = 8100`, `PORT_STEP = 10`; `worktree_path(root, sid, repo) -> Path`; `allocate_port(root) -> int`; `require_session(root, sid) -> Path` (lanza `unknown_session`); `add_repo(root, sid, repo, *, branch=None, detach_at=None, out=None) -> dict` `{"name","branch","path","port"}` (lanza `unknown_repo`, `repo_exists`, `BranchOccupied`); `rm_repo(root, sid, repo, *, force=False, out=None) -> None` (lanza `uncommitted_changes`, `repo_not_in_session`). En esta tarea `out` se acepta pero no se usa (lo usa Task 5 para scripts).

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_repos_fs.py
import os, subprocess
import pytest
from ide_server.repos_fs import add_repo, rm_repo, worktree_path, allocate_port
from ide_server.sessions_fs import create_session_dir, read_session, session_path, SessionError
from ide_server.worktrees import BranchOccupied


def _git(*a, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True,
                   capture_output=True)


def _ws(tmp_path):
    for name in ("repo-a", "repo-b"):
        r = tmp_path / name; r.mkdir()
        _git("init", "-q", "-b", "main", cwd=r); _git("commit", "-q", "--allow-empty", "-m", "x", cwd=r)
    for sid in ("t1", "t2"):
        create_session_dir(tmp_path, sid=sid, kind="ticket", permissions="analyze", prompt="")
    return tmp_path


def test_add_repo_creates_worktree_symlink_and_port(tmp_path):
    root = _ws(tmp_path)
    info = add_repo(root, "t1", "repo-a")
    wt = worktree_path(root, "t1", "repo-a")
    link = session_path(root, "t1") / "repo-a"
    assert info == {"name": "repo-a", "branch": "t1", "path": str(wt), "port": 8100}
    assert link.is_symlink() and os.readlink(link) == "../../worktrees/t1/repo-a"
    assert read_session(root, "t1")["repos"][0]["branch"] == "t1"


def test_ports_are_distinct_and_reused_after_rm(tmp_path):        # Review Focus (puertos)
    root = _ws(tmp_path)
    assert add_repo(root, "t1", "repo-a")["port"] == 8100
    assert add_repo(root, "t2", "repo-a")["port"] == 8110
    rm_repo(root, "t1", "repo-a")
    assert allocate_port(root) == 8100


def test_add_repo_errors(tmp_path):
    root = _ws(tmp_path)
    with pytest.raises(SessionError) as e:
        add_repo(root, "t1", "nope")
    assert e.value.code == "unknown_repo"
    with pytest.raises(SessionError) as e:
        add_repo(root, "zz", "repo-a")
    assert e.value.code == "unknown_session"
    add_repo(root, "t1", "repo-a")
    with pytest.raises(SessionError) as e:
        add_repo(root, "t1", "repo-a")
    assert e.value.code == "repo_exists"
    with pytest.raises(BranchOccupied):
        add_repo(root, "t2", "repo-a", branch="t1")
    assert not (session_path(root, "t2") / "repo-a").exists()


def test_add_repo_detached(tmp_path):
    root = _ws(tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root / "repo-a",
                         capture_output=True, text=True).stdout.strip()
    info = add_repo(root, "t1", "repo-a", detach_at=sha)
    assert info["branch"] is None
    assert read_session(root, "t1")["repos"][0]["branch"] == "HEAD"


def test_rm_repo_refuses_dirty_then_force(tmp_path):
    root = _ws(tmp_path)
    add_repo(root, "t1", "repo-a")
    (worktree_path(root, "t1", "repo-a") / "x.txt").write_text("sucio")
    with pytest.raises(SessionError) as e:
        rm_repo(root, "t1", "repo-a")
    assert e.value.code == "uncommitted_changes"
    rm_repo(root, "t1", "repo-a", force=True)
    assert not (session_path(root, "t1") / "repo-a").exists()
    assert not worktree_path(root, "t1", "repo-a").exists()
    assert read_session(root, "t1")["repos"] == []


def test_rm_repo_with_missing_worktree_prunes(tmp_path):
    import shutil
    root = _ws(tmp_path)
    add_repo(root, "t1", "repo-a")
    shutil.rmtree(worktree_path(root, "t1", "repo-a"))
    rm_repo(root, "t1", "repo-a")
    assert not (session_path(root, "t1") / "repo-a").is_symlink()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_repos_fs.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ide_server.repos_fs'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/repos_fs.py
from __future__ import annotations
import os
import subprocess
import tomllib
from pathlib import Path
from typing import TextIO
from ide_server.sessions_fs import (
    SessionError, session_path, sessions_dir, read_toml, update_session_toml,
)
from ide_server.workspace import discover_repos
from ide_server.worktrees import add_worktree, remove_worktree, has_uncommitted_changes

PORT_BASE = 8100
PORT_STEP = 10


def worktree_path(root: Path, sid: str, repo: str) -> Path:
    return root / ".ide" / "worktrees" / sid / repo


def require_session(root: Path, sid: str) -> Path:
    path = session_path(root, sid)
    if not (path / ".session.toml").is_file():
        raise SessionError("unknown_session", f"no existe la sesión {sid}")
    return path


def _repo_root(root: Path, repo: str) -> Path:
    names = [r["id"] for r in discover_repos(root)]
    if repo not in names:
        raise SessionError("unknown_repo",
                           f"repo desconocido: {repo} (repos: {', '.join(names) or 'ninguno'})")
    return root / repo


def _used_ports(root: Path) -> set[int]:
    used: set[int] = set()
    d = sessions_dir(root)
    if not d.is_dir():
        return used
    for p in d.iterdir():
        try:
            used.update(int(v) for v in read_toml(p / ".session.toml").get("ports", {}).values())
        except (OSError, tomllib.TOMLDecodeError, ValueError):
            continue
    return used


def allocate_port(root: Path) -> int:
    used, port = _used_ports(root), PORT_BASE
    while port in used:
        port += PORT_STEP
    return port


def add_repo(root: Path, sid: str, repo: str, *, branch: str | None = None,
             detach_at: str | None = None, out: TextIO | None = None) -> dict:
    spath = require_session(root, sid)
    repo_path = _repo_root(root, repo)
    link, wt = spath / repo, worktree_path(root, sid, repo)
    if link.is_symlink() or wt.exists():
        raise SessionError("repo_exists", f"{repo} ya está en la sesión {sid}")
    wt.parent.mkdir(parents=True, exist_ok=True)
    if detach_at:
        add_worktree(repo_path, wt, detach_at, access="ro", base=detach_at)
        branch_name = None
    else:
        branch_name = branch or sid
        add_worktree(repo_path, wt, branch_name, access="rw")
    try:
        link.symlink_to(os.path.relpath(wt, link.parent))
        port = allocate_port(root)
        update_session_toml(root, sid, lambda d: d.setdefault("ports", {}).update({repo: port}))
    except Exception:
        link.unlink(missing_ok=True)
        remove_worktree(repo_path, wt, force=True)
        raise
    return {"name": repo, "branch": branch_name, "path": str(wt), "port": port}


def rm_repo(root: Path, sid: str, repo: str, *, force: bool = False,
            out: TextIO | None = None) -> None:
    spath = require_session(root, sid)
    link, wt = spath / repo, worktree_path(root, sid, repo)
    if not link.is_symlink() and not wt.exists():
        raise SessionError("repo_not_in_session", f"{repo} no está en la sesión {sid}")
    repo_path = root / repo
    if wt.exists():
        if not force and has_uncommitted_changes(wt):
            raise SessionError("uncommitted_changes",
                               f"{repo} en {sid} tiene cambios sin commitear (usa --force)")
        remove_worktree(repo_path, wt, force=force)
    else:
        subprocess.run(["git", "-C", str(repo_path), "worktree", "prune"], capture_output=True)
    link.unlink(missing_ok=True)

    def _drop(d: dict) -> None:
        d.get("ports", {}).pop(repo, None)
        d.get("setup", {}).pop(repo, None)
    update_session_toml(root, sid, _drop)
    try:
        wt.parent.rmdir()
    except OSError:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_repos_fs.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/repos_fs.py server/tests/test_repos_fs.py
git commit -m "feat(sesiones): repos_fs (worktree + symlink + bloque de puertos por sesión)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `scripts` + `setup`/`archive` automáticos

**Files:**
- Create: `server/ide_server/scripts.py`
- Modify: `server/ide_server/repos_fs.py` (`add_repo` corre `setup`; `rm_repo` corre `archive`)
- Test: `server/tests/test_scripts.py`

**Interfaces:**
- Consumes: Task 4.
- Produces: `scripts_dir(root, repo) -> Path`; `list_scripts(root, repo) -> list[{"name": str, "executable": bool}]`; `has_script(root, repo, name) -> bool`; `script_argv(root, repo, name) -> list[str]` (lanza `script_not_found`, `script_not_executable` con el `chmod +x` sugerido); `script_env(root, sid, repo, base_env=None) -> dict[str,str]`; `run_script(root, sid, repo, name, *, out=sys.stdout, base_env=None) -> int` (si `name == "setup"`, registra `[setup] <repo> = "ok"|"failed"` en `.session.toml`). `add_repo` lanza `SessionError("setup_failed")` tras dejar el worktree; `rm_repo` con `archive` fallido lanza `archive_failed` salvo `force`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_scripts.py
import io, os, subprocess
import pytest
from ide_server.scripts import list_scripts, script_env, run_script, script_argv
from ide_server.repos_fs import add_repo, rm_repo, worktree_path
from ide_server.sessions_fs import create_session_dir, read_session, SessionError


def _git(*a, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True,
                   capture_output=True)


def _ws(tmp_path):
    r = tmp_path / "repo-a"; r.mkdir()
    _git("init", "-q", "-b", "main", cwd=r); _git("commit", "-q", "--allow-empty", "-m", "x", cwd=r)
    create_session_dir(tmp_path, sid="t1", kind="ticket", permissions="analyze", prompt="")
    (tmp_path / ".ide" / "scripts" / "repo-a").mkdir(parents=True)
    return tmp_path


def _script(root, name, body, executable=True):
    p = root / ".ide" / "scripts" / "repo-a" / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    if executable:
        p.chmod(0o755)
    return p


def test_list_scripts_flags_non_executable(tmp_path):
    root = _ws(tmp_path)
    _script(root, "run", "echo run"); _script(root, "test", "echo t", executable=False)
    assert list_scripts(root, "repo-a") == [{"name": "run", "executable": True},
                                            {"name": "test", "executable": False}]
    with pytest.raises(SessionError) as e:
        script_argv(root, "repo-a", "test")
    assert e.value.code == "script_not_executable" and "chmod +x" in str(e.value)
    with pytest.raises(SessionError) as e:
        script_argv(root, "repo-a", "nope")
    assert e.value.code == "script_not_found"


def test_setup_runs_on_add_with_env_in_worktree(tmp_path):
    root = _ws(tmp_path)
    _script(root, "setup", 'echo "$IDE_SESSION_ID $IDE_REPO $IDE_PORT $IDE_ROOT_REPO" > env.txt; pwd')
    out = io.StringIO()
    add_repo(root, "t1", "repo-a", out=out)
    wt = worktree_path(root, "t1", "repo-a")
    assert (wt / "env.txt").read_text().split() == ["t1", "repo-a", "8100", str(root / "repo-a")]
    assert str(wt.resolve()) in out.getvalue()
    assert read_session(root, "t1")["repos"][0]["setup"] == "ok"


def test_setup_failure_keeps_worktree_and_marks(tmp_path):
    root = _ws(tmp_path)
    _script(root, "setup", "echo boom; exit 3")
    with pytest.raises(SessionError) as e:
        add_repo(root, "t1", "repo-a", out=io.StringIO())
    assert e.value.code == "setup_failed" and "exit 3" in str(e.value)
    assert worktree_path(root, "t1", "repo-a").exists()
    assert read_session(root, "t1")["repos"][0]["setup"] == "failed"
    _script(root, "setup", "true")
    assert run_script(root, "t1", "repo-a", "setup", out=io.StringIO()) == 0
    assert read_session(root, "t1")["repos"][0]["setup"] == "ok"


def test_archive_runs_on_rm_and_blocks_on_failure(tmp_path):
    root = _ws(tmp_path)
    add_repo(root, "t1", "repo-a", out=io.StringIO())
    marker = tmp_path / "archived"
    _script(root, "archive", f"touch {marker}; exit 1")
    with pytest.raises(SessionError) as e:
        rm_repo(root, "t1", "repo-a", out=io.StringIO())
    assert e.value.code == "archive_failed" and marker.exists()
    rm_repo(root, "t1", "repo-a", force=True, out=io.StringIO())
    assert not worktree_path(root, "t1", "repo-a").exists()


def test_script_env_without_port(tmp_path):
    root = _ws(tmp_path)
    env = script_env(root, "t1", "repo-a", base_env={"PATH": "/bin"})
    assert env["IDE_WORKSPACE"] == str(root) and "IDE_PORT" not in env and env["PATH"] == "/bin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_scripts.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ide_server.scripts'`

- [ ] **Step 3: Write `scripts.py`**

```python
# server/ide_server/scripts.py
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
from typing import TextIO
from ide_server.sessions_fs import SessionError, session_path, read_toml, update_session_toml


def scripts_dir(root: Path, repo: str) -> Path:
    return root / ".ide" / "scripts" / repo


def list_scripts(root: Path, repo: str) -> list[dict]:
    d = scripts_dir(root, repo)
    if not d.is_dir():
        return []
    return [{"name": p.name, "executable": os.access(p, os.X_OK)}
            for p in sorted(d.iterdir()) if p.is_file() and not p.name.startswith(".")]


def has_script(root: Path, repo: str, name: str) -> bool:
    return (scripts_dir(root, repo) / name).is_file()


def script_argv(root: Path, repo: str, name: str) -> list[str]:
    path = scripts_dir(root, repo) / name
    if not path.is_file():
        raise SessionError("script_not_found", f"no existe el script {repo}/{name} ({path})")
    if not os.access(path, os.X_OK):
        raise SessionError("script_not_executable",
                           f"{repo}/{name} no es ejecutable: chmod +x {path}")
    return [str(path)]


def script_env(root: Path, sid: str, repo: str, base_env: dict | None = None) -> dict[str, str]:
    data = read_toml(session_path(root, sid) / ".session.toml")
    env = dict(os.environ if base_env is None else base_env)
    env.update(IDE_SESSION_ID=sid, IDE_REPO=repo, IDE_ROOT_REPO=str(root / repo),
               IDE_WORKSPACE=str(root))
    port = data.get("ports", {}).get(repo)
    if port is not None:
        env["IDE_PORT"] = str(port)
    return env


def run_script(root: Path, sid: str, repo: str, name: str, *, out: TextIO | None = None,
               base_env: dict | None = None) -> int:
    from ide_server.repos_fs import worktree_path
    out = out or sys.stdout
    try:
        argv = script_argv(root, repo, name)
        proc = subprocess.Popen(argv, cwd=worktree_path(root, sid, repo),
                                env=script_env(root, sid, repo, base_env),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            out.write(line)
        code = proc.wait()
    except SessionError:
        code = -1
        if name == "setup":
            _record_setup(root, sid, repo, "failed")
        raise
    if name == "setup":
        _record_setup(root, sid, repo, "ok" if code == 0 else "failed")
    return code


def _record_setup(root: Path, sid: str, repo: str, state: str) -> None:
    update_session_toml(root, sid, lambda d: d.setdefault("setup", {}).update({repo: state}))
```

- [ ] **Step 4: Hook into `repos_fs`**

En `add_repo`, antes del `return`:

```python
    from ide_server.scripts import has_script, run_script
    if has_script(root, repo, "setup"):
        code = run_script(root, sid, repo, "setup", out=out)
        if code != 0:
            raise SessionError("setup_failed",
                               f"setup de {repo} falló (exit {code}); reintenta con "
                               f"`ide script setup {repo}`")
```

En `rm_repo`, justo después de `repo_path = root / repo`:

```python
    from ide_server.scripts import has_script, run_script
    if wt.exists() and has_script(root, repo, "archive"):
        code = run_script(root, sid, repo, "archive", out=out)
        if code != 0 and not force:
            raise SessionError("archive_failed",
                               f"archive de {repo} falló (exit {code}); usa --force para quitarlo igual")
```

- [ ] **Step 5: Run tests**

Run: `cd server && uv run pytest tests/test_scripts.py tests/test_repos_fs.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/ide_server/scripts.py server/ide_server/repos_fs.py server/tests/test_scripts.py
git commit -m "feat(sesiones): scripts por repo (setup/archive automáticos, env IDE_*)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `Supervisor` (procesos `claude`, cola `max_running`)

**Files:**
- Create: `server/ide_server/supervisor.py`
- Test: `server/tests/test_supervisor.py`

**Interfaces:**
- Consumes: Task 2 (`session_path`, `read_toml`, `SessionError`).
- Produces:
  - `encode_project_dir(path: Path) -> str`; `has_history(path: Path, home: Path) -> bool`.
  - `build_argv(root, sid, *, command: str, resume: bool) -> list[str]`.
  - `SpawnFn = Callable[[Path, list[str], dict[str, str], Callable[[], None]], str]` — `(cwd, argv, env, on_exit) -> terminal_id`; `KillFn = Callable[[str], None]`.
  - `class Supervisor(root, *, spawn, kill, server_url, command="claude", max_running=None, home=None, on_change=None, which=shutil.which)`: `start(sid, *, resume: bool | None = None) -> str` ("running"|"queued"), `stop(sid) -> None`, `state(sid) -> str` ("running"|"queued"|"stopped"), `snapshot() -> dict[str, dict]` (`{sid: {"process", "terminalId", "launchError"}}` solo para sesiones con algo que reportar).
  - Si se usó el fallback del spike (sin `--settings`), `build_argv` no agrega `--settings` y `Supervisor._launch` copia `.ide/permissions/<p>.json` a `sessions/<id>/.claude/settings.json`; ajustar el test `test_argv_by_permissions` en consecuencia.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_supervisor.py
import pytest
from pathlib import Path
from ide_server.supervisor import Supervisor, build_argv, encode_project_dir, has_history
from ide_server.sessions_fs import create_session_dir, SessionError


class FakePty:
    def __init__(self):
        self.spawned, self.killed, self.exits, self.n = [], [], {}, 0

    def spawn(self, cwd, argv, env, on_exit):
        self.n += 1
        tid = f"t{self.n}"
        self.spawned.append((tid, cwd, argv, env))
        self.exits[tid] = on_exit
        return tid

    def kill(self, tid):
        self.killed.append(tid)


def _mk(tmp_path, *sids, perm="analyze"):
    for sid in sids:
        create_session_dir(tmp_path, sid=sid, kind="ticket", permissions=perm, prompt=f"haz {sid}")
    return tmp_path


def _sup(root, pty, **kw):
    return Supervisor(root, spawn=pty.spawn, kill=pty.kill, server_url="http://127.0.0.1:9",
                      home=root / "home", which=lambda c: "/usr/bin/" + c, **kw)


def test_argv_by_permissions(tmp_path):
    root = _mk(tmp_path, "a")
    create_session_dir(root, sid="f", kind="ticket", permissions="full", prompt="")
    create_session_dir(root, sid="d", kind="ticket", permissions="default", prompt="p")
    perm = root / ".ide" / "permissions"
    assert build_argv(root, "a", command="claude", resume=False) == [
        "claude", "--settings", str(perm / "analyze.json"), "haz a"]
    assert build_argv(root, "f", command="claude --verbose", resume=True) == [
        "claude", "--verbose", "--settings", str(perm / "full.json"),
        "--permission-mode", "bypassPermissions", "--continue"]
    assert build_argv(root, "d", command="claude", resume=False) == ["claude", "p"]


def test_history_detection(tmp_path):
    p = tmp_path / ".ide" / "sessions" / "a"
    assert encode_project_dir(Path("/x/.ide/s_1")) == "-x--ide-s-1"
    proj = tmp_path / "home" / ".claude" / "projects" / encode_project_dir(p.resolve())
    assert not has_history(p, tmp_path / "home")
    proj.mkdir(parents=True); (proj / "abc.jsonl").write_text("{}")
    assert has_history(p, tmp_path / "home")


def test_start_spawns_with_env_and_exit_marks_stopped(tmp_path):
    root, pty, changes = _mk(tmp_path, "a"), FakePty(), []
    sup = _sup(root, pty, on_change=lambda: changes.append(1))
    assert sup.start("a") == "running"
    tid, cwd, argv, env = pty.spawned[0]
    assert cwd == root / ".ide" / "sessions" / "a" and argv[-1] == "haz a"
    assert env["IDE_SESSION_ID"] == "a" and env["IDE_URL"] == "http://127.0.0.1:9"
    assert env["IDE_WORKSPACE"] == str(root)
    assert sup.snapshot() == {"a": {"process": "running", "terminalId": tid, "launchError": None}}
    pty.exits[tid]()
    assert sup.state("a") == "stopped" and changes


def test_start_twice_is_idempotent_and_unknown_raises(tmp_path):
    root, pty = _mk(tmp_path, "a"), FakePty()
    sup = _sup(root, pty)
    sup.start("a"); sup.start("a")
    assert len(pty.spawned) == 1
    with pytest.raises(SessionError) as e:
        sup.start("nope")
    assert e.value.code == "unknown_session"


def test_queue_fifo_with_max_running(tmp_path):
    root, pty = _mk(tmp_path, "a", "b", "c"), FakePty()
    sup = _sup(root, pty, max_running=1)
    assert [sup.start(s) for s in ("a", "b", "c")] == ["running", "queued", "queued"]
    pty.exits["t1"]()
    assert sup.state("b") == "running" and sup.state("c") == "queued"
    sup.stop("c")
    assert sup.state("c") == "stopped"
    sup.stop("b")
    assert pty.killed == ["t2"] and sup.state("b") == "stopped"


def test_stale_exit_callback_ignored_after_restart(tmp_path):
    root, pty = _mk(tmp_path, "a"), FakePty()
    sup = _sup(root, pty)
    sup.start("a"); sup.stop("a"); sup.start("a")
    pty.exits["t1"]()                              # salida tardía del proceso viejo
    assert sup.state("a") == "running"


def test_missing_claude_binary(tmp_path):
    root, pty = _mk(tmp_path, "a"), FakePty()
    sup = Supervisor(root, spawn=pty.spawn, kill=pty.kill, server_url="u", which=lambda c: None)
    with pytest.raises(SessionError) as e:
        sup.start("a")
    assert e.value.code == "claude_missing" and pty.spawned == []


def test_queued_launch_error_is_reported(tmp_path):
    root, pty = _mk(tmp_path, "a", "b"), FakePty()
    found = {"ok": True}
    sup = Supervisor(root, spawn=pty.spawn, kill=pty.kill, server_url="u", max_running=1,
                     home=root / "home", which=lambda c: "/x" if found["ok"] else None)
    sup.start("a"); sup.start("b")
    found["ok"] = False
    pty.exits["t1"]()
    snap = sup.snapshot()["b"]
    assert snap["process"] == "stopped" and snap["terminalId"] is None
    assert "claude" in snap["launchError"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_supervisor.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ide_server.supervisor'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/supervisor.py
from __future__ import annotations
import os
import re
import shlex
import shutil
from pathlib import Path
from typing import Callable
from ide_server.sessions_fs import SessionError, session_path, read_toml

SpawnFn = Callable[[Path, list[str], dict[str, str], Callable[[], None]], str]
KillFn = Callable[[str], None]


def encode_project_dir(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def has_history(path: Path, home: Path) -> bool:
    d = home / ".claude" / "projects" / encode_project_dir(path.resolve())
    return d.is_dir() and any(d.glob("*.jsonl"))


def build_argv(root: Path, sid: str, *, command: str, resume: bool) -> list[str]:
    path = session_path(root, sid)
    perm = read_toml(path / ".session.toml").get("permissions", "default")
    argv = shlex.split(command)
    if perm in ("analyze", "full"):
        argv += ["--settings", str(root / ".ide" / "permissions" / f"{perm}.json")]
    if perm == "full":
        argv += ["--permission-mode", "bypassPermissions"]
    if resume:
        argv.append("--continue")
    else:
        prompt_file = path / "PROMPT.md"
        prompt = prompt_file.read_text(encoding="utf-8").strip() if prompt_file.is_file() else ""
        if prompt:
            argv.append(prompt)
    return argv


class Supervisor:
    """Dueño único de los procesos `claude` de las sesiones-carpeta."""

    def __init__(self, root: Path, *, spawn: SpawnFn, kill: KillFn, server_url: str,
                 command: str = "claude", max_running: int | None = None,
                 home: Path | None = None, on_change: Callable[[], None] | None = None,
                 which: Callable[[str], str | None] = shutil.which) -> None:
        self._root, self._spawn, self._kill = root, spawn, kill
        self._url, self._command, self._max = server_url, command, max_running
        self._home = home or Path.home()
        self._on_change = on_change or (lambda: None)
        self._which = which
        self._running: dict[str, str] = {}
        self._queue: list[tuple[str, bool]] = []
        self._errors: dict[str, str] = {}

    def state(self, sid: str) -> str:
        if sid in self._running:
            return "running"
        if any(q == sid for q, _ in self._queue):
            return "queued"
        return "stopped"

    def snapshot(self) -> dict[str, dict]:
        sids = set(self._running) | {q for q, _ in self._queue} | set(self._errors)
        return {sid: {"process": self.state(sid), "terminalId": self._running.get(sid),
                      "launchError": self._errors.get(sid)} for sid in sids}

    def start(self, sid: str, *, resume: bool | None = None) -> str:
        path = session_path(self._root, sid)
        if not (path / ".session.toml").is_file():
            raise SessionError("unknown_session", f"no existe la sesión {sid}")
        if self.state(sid) != "stopped":
            return self.state(sid)
        if resume is None:
            resume = has_history(path, self._home)
        if self._max is not None and len(self._running) >= self._max:
            self._queue.append((sid, resume))
            self._on_change()
            return "queued"
        self._launch(sid, resume)
        self._on_change()
        return "running"

    def stop(self, sid: str) -> None:
        self._queue = [(q, r) for q, r in self._queue if q != sid]
        tid = self._running.pop(sid, None)
        if tid is not None:
            self._kill(tid)
            self._drain()
        self._on_change()

    def _launch(self, sid: str, resume: bool) -> None:
        argv = build_argv(self._root, sid, command=self._command, resume=resume)
        if self._which(argv[0]) is None:
            raise SessionError("claude_missing",
                               f"no se encontró `{argv[0]}` en el PATH (¿instalaste claude?)")
        env = {**os.environ, "IDE_SESSION_ID": sid, "IDE_URL": self._url,
               "IDE_WORKSPACE": str(self._root)}
        holder: dict[str, str] = {}
        tid = self._spawn(session_path(self._root, sid), argv, env,
                          lambda: self._on_exit(sid, holder.get("tid")))
        holder["tid"] = tid
        self._running[sid] = tid
        self._errors.pop(sid, None)

    def _on_exit(self, sid: str, tid: str | None) -> None:
        if tid is None or self._running.get(sid) != tid:
            return
        del self._running[sid]
        self._drain()
        self._on_change()

    def _drain(self) -> None:
        while self._queue and (self._max is None or len(self._running) < self._max):
            sid, resume = self._queue.pop(0)
            try:
                self._launch(sid, resume)
            except SessionError as exc:
                self._errors[sid] = str(exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_supervisor.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/supervisor.py server/tests/test_supervisor.py
git commit -m "feat(sesiones): supervisor de procesos claude con cola max_running

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: PTY con env + hooks de procesos en `terminals`

**Files:**
- Modify: `server/ide_server/pty_manager.py:17-29` (`spawn` acepta `env`)
- Modify: `server/ide_server/capabilities/terminals.py` (extraer `_attach`, devolver hooks)
- Test: `server/tests/test_terminal_hooks.py`

**Interfaces:**
- Consumes: Task 6 (`SpawnFn`/`KillFn` shape).
- Produces: `PtyManager.spawn(cwd, argv, env: dict | None = None) -> str`; `terminals.register(...)` ahora **devuelve** `TerminalHooks` con `spawn(cwd, argv, env, on_exit, session_id=None) -> str` y `kill(tid) -> None`. Los procesos así lanzados aparecen en `terminal.list` y streamean por `terminal.data.<tid>` / `terminal.exit.<tid>` igual que los de `terminal.open`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_terminal_hooks.py
import asyncio
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import terminals as term_cap


class Rec:
    def __init__(self): self.events = []
    async def broadcast(self, channel, payload): self.events.append((channel, payload))


@pytest.mark.asyncio
async def test_hooks_spawn_with_env_streams_and_calls_on_exit(tmp_path):
    rec, exited = Rec(), asyncio.Event()
    hooks = term_cap.register(Registry(), tmp_path, rec)
    tid = hooks.spawn(tmp_path, ["sh", "-c", 'echo "v=$FOO"'], {"FOO": "bar", "PATH": "/bin:/usr/bin"},
                      exited.set, session_id="s1")
    await asyncio.wait_for(exited.wait(), 5)
    import base64
    data = b"".join(base64.b64decode(p["data"]) for c, p in rec.events if c == f"terminal.data.{tid}")
    assert b"v=bar" in data
    assert (f"terminal.exit.{tid}", {}) in rec.events


@pytest.mark.asyncio
async def test_hooks_kill(tmp_path):
    hooks = term_cap.register(Registry(), tmp_path, Rec())
    exits = []
    tid = hooks.spawn(tmp_path, ["sleep", "30"], {"PATH": "/bin:/usr/bin"}, lambda: exits.append(1))
    hooks.kill(tid)                              # reap sincrónico: no cuelga ni deja zombie
    await asyncio.sleep(0.1)
    assert exits == []                           # un kill explícito no dispara on_exit
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_terminal_hooks.py -q`
Expected: FAIL con `AttributeError: 'NoneType' object has no attribute 'spawn'`

- [ ] **Step 3: PtyManager env**

En `pty_manager.py`, cambiar la firma y el exec:

```python
    def spawn(self, cwd: Path, argv: list[str], env: dict[str, str] | None = None) -> str:
        tid = uuid.uuid4().hex[:12]
        pid, fd = pty.fork()
        if pid == 0:                            # hijo: stdio ya es el slave pty
            try:
                os.chdir(str(cwd))
            except OSError:
                pass
            try:
                if env is None:
                    os.execvp(argv[0], argv)
                else:
                    os.execvpe(argv[0], argv, env)
            except OSError:
                os._exit(127)                   # execvp falló (comando inexistente)
        self._terms[tid] = {"pid": pid, "fd": fd}
        return tid
```

- [ ] **Step 4: Terminals hooks**

Reescribir el cuerpo de `capabilities/terminals.py` así (mismos canales; `open_` usa `_attach`):

```python
from __future__ import annotations
import asyncio
import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from ide_server.plugins import Registry
from ide_server.pty_manager import PtyManager
from ide_server.workspace import resolve_cwd


@dataclass
class TerminalHooks:
    spawn: Callable[..., str]
    kill: Callable[[str], None]


def register(registry: Registry, root: Path, manager, pty: PtyManager | None = None) -> TerminalHooks:
    pty = pty or PtyManager()
    terms: dict[str, dict] = {}                 # tid -> {sessionId, cmd, cwd}

    def _attach(tid: str, on_exit: Callable[[], None] | None = None) -> None:
        loop = asyncio.get_running_loop()
        fd = pty.fd(tid)

        def _on_readable() -> None:
            data = pty.read(tid, timeout=0.0)
            if data:
                loop.create_task(manager.broadcast(
                    f"terminal.data.{tid}", {"data": base64.b64encode(data).decode()}))
            if not pty.is_alive(tid):
                try:
                    loop.remove_reader(fd)
                except (OSError, ValueError):
                    pass
                loop.create_task(manager.broadcast(f"terminal.exit.{tid}", {}))
                if on_exit is not None:
                    on_exit()

        loop.add_reader(fd, _on_readable)

    def spawn_process(cwd: Path, argv: list[str], env: dict[str, str],
                      on_exit: Callable[[], None], session_id: str | None = None) -> str:
        tid = pty.spawn(cwd, argv, env=env)
        terms[tid] = {"sessionId": session_id, "cmd": argv, "cwd": str(cwd)}
        _attach(tid, on_exit)
        return tid

    def kill_process(tid: str) -> None:
        try:
            asyncio.get_running_loop().remove_reader(pty.fd(tid))
        except (OSError, ValueError, KeyError, RuntimeError):
            pass
        pty.close(tid)
        terms.pop(tid, None)

    async def open_(payload: dict) -> dict:
        cwd = resolve_cwd(root, payload)
        cmd = payload.get("cmd") or [os.environ.get("SHELL", "/bin/zsh")]
        tid = pty.spawn(cwd, cmd)
        terms[tid] = {"sessionId": payload.get("sessionId"), "cmd": cmd, "cwd": str(cwd)}
        _attach(tid)
        return {"id": tid, "cwd": str(cwd)}

    async def list_(payload: dict) -> dict:
        sid = payload.get("sessionId")
        out = [{"id": tid, "cmd": t["cmd"], "alive": pty.is_alive(tid)}
               for tid, t in terms.items() if t["sessionId"] == sid]
        return {"terminals": out}

    async def write_(payload: dict) -> dict:
        pty.write(payload["id"], base64.b64decode(payload["data"]))
        return {"ok": True}

    async def resize_(payload: dict) -> dict:
        pty.resize(payload["id"], int(payload["cols"]), int(payload["rows"]))
        return {"ok": True}

    async def close_(payload: dict) -> dict:
        kill_process(payload["id"])
        return {"ok": True}

    registry.register("terminal.open", open_)
    registry.register("terminal.list", list_)
    registry.register("terminal.write", write_)
    registry.register("terminal.resize", resize_)
    registry.register("terminal.close", close_)

    register._pty = pty        # type: ignore[attr-defined]
    register._terms = terms    # type: ignore[attr-defined]
    register._manager = manager  # type: ignore[attr-defined]
    return TerminalHooks(spawn=spawn_process, kill=kill_process)
```

Nota: un `kill` del supervisor (`stop`) quita el reader antes de matar, así que `on_exit` **no** se dispara por un stop explícito; el supervisor ya actualiza su estado en `stop`.

- [ ] **Step 5: Run tests (nuevos + terminales existentes)**

Run: `cd server && uv run pytest tests/test_terminal_hooks.py tests/test_terminals_open.py tests/test_terminals_io.py tests/test_terminals_stream.py tests/test_pty_manager.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add server/ide_server/pty_manager.py server/ide_server/capabilities/terminals.py server/tests/test_terminal_hooks.py
git commit -m "feat(terminal): PTY con env y hooks spawn/kill para el supervisor

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `session_ops` — crear (plantilla/review), borrar, refrescar review

**Files:**
- Create: `server/ide_server/session_ops.py`
- Test: `server/tests/test_session_ops.py`

**Interfaces:**
- Consumes: Tasks 1–5, `config.sessions_config`.
- Produces:
  - `Runner = Callable[[list[str]], subprocess.CompletedProcess]` (default `_run` = `subprocess.run(..., capture_output=True, text=True)`).
  - `parse_pr_url(url) -> tuple[str, int]` (`(repo_name, number)`; lanza `bad_pr_url`).
  - `load_template(root, name) -> str` (lanza `unknown_template`).
  - `create_session(root, req: dict, *, runner=_run) -> dict` → `{"session": <session dict>, "log": str}`. `req`: `id?`, `main?`, `title?`, `template?`, `vars?`, `prompt?`, `permissions?`, `review?` (url).
  - `delete_session(root, sid, *, force=False, stop: Callable[[str], None] | None = None) -> None`.
  - `refresh_review(root, sid, *, runner=_run) -> dict` (session dict actualizado).

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_session_ops.py
import io, json, subprocess
import pytest
from ide_server.session_ops import create_session, delete_session, refresh_review, parse_pr_url
from ide_server.sessions_fs import seed_workspace, session_path, read_session, SessionError
from ide_server.repos_fs import add_repo, worktree_path


def _git(*a, cwd):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


def _ws(tmp_path):
    r = tmp_path / "repo-a"; r.mkdir()
    _git("init", "-q", "-b", "main", cwd=r); _git("commit", "-q", "--allow-empty", "-m", "x", cwd=r)
    seed_workspace(tmp_path)
    return tmp_path


def test_parse_pr_url():
    assert parse_pr_url("https://github.com/acme/repo-a/pull/482") == ("repo-a", 482)
    with pytest.raises(SessionError):
        parse_pr_url("https://gitlab.com/x")


def test_create_ticket_from_template_normalizes_id(tmp_path):        # Review Focus 1
    root = _ws(tmp_path)
    res = create_session(root, {"id": "FIN-123", "template": "ticket",
                                "vars": {"title": "Exportar", "notion_url": "https://n", "body": "b"}})
    s = res["session"]
    assert s["id"] == "fin-123" and s["kind"] == "ticket" and s["title"] == "Exportar"
    assert s["permissions"] == "analyze" and s["meta"]["notion_url"] == "https://n"
    assert "fin-123" in (session_path(root, "fin-123") / "PROMPT.md").read_text()


def test_create_missing_var_creates_nothing(tmp_path):
    root = _ws(tmp_path)
    with pytest.raises(SessionError) as e:
        create_session(root, {"id": "x", "template": "ticket", "vars": {"title": "t"}})
    assert e.value.code == "missing_vars" and not session_path(root, "x").exists()


def test_create_main_random_id_free_prompt(tmp_path):
    root = _ws(tmp_path)
    s = create_session(root, {"main": True, "prompt": "hola", "permissions": "full"})["session"]
    assert s["kind"] == "main" and s["id"].startswith("s-") and s["permissions"] == "full"


def _fake_gh(sha, *, fail=False):
    calls = []

    def runner(argv):
        calls.append(argv)
        if argv[0] == "gh":
            if fail:
                return subprocess.CompletedProcess(argv, 1, "", "HTTP 404")
            return subprocess.CompletedProcess(argv, 0, json.dumps(
                {"title": "Refactor auth", "author": {"login": "juan"}, "headRefOid": sha,
                 "state": "OPEN"}), "")
        if argv[:2] == ["git", "-C"] and "fetch" in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.run(argv, capture_output=True, text=True)
    return runner, calls


def test_create_review(tmp_path):
    root = _ws(tmp_path)
    sha = _git("rev-parse", "HEAD", cwd=root / "repo-a")
    runner, calls = _fake_gh(sha)
    s = create_session(root, {"review": "https://github.com/acme/repo-a/pull/482"},
                       runner=runner)["session"]
    assert s["id"] == "pr-repo-a-482" and s["kind"] == "review" and s["status"] == "reviewing"
    assert s["title"] == "Refactor auth" and s["meta"]["author"] == "@juan"
    assert s["reviewedSha"] == sha and s["repos"][0]["name"] == "repo-a"
    assert any(c[:1] == ["git"] and "pull/482/head" in c for c in calls)


def test_create_review_gh_failure_leaves_nothing(tmp_path):
    root = _ws(tmp_path)
    runner, _ = _fake_gh("x", fail=True)
    with pytest.raises(SessionError) as e:
        create_session(root, {"review": "https://github.com/acme/repo-a/pull/1"}, runner=runner)
    assert e.value.code == "gh_failed" and "404" in str(e.value)
    assert not session_path(root, "pr-repo-a-1").exists()


def test_create_review_unknown_repo(tmp_path):
    root = _ws(tmp_path)
    with pytest.raises(SessionError) as e:
        create_session(root, {"review": "https://github.com/acme/otro/pull/1"})
    assert e.value.code == "unknown_repo"


def test_delete_refuses_dirty_before_touching_anything(tmp_path):    # Review Focus 5
    root = _ws(tmp_path)
    create_session(root, {"id": "t", "prompt": ""})
    for name in ("repo-a",):
        add_repo(root, "t", name, out=io.StringIO())
    (worktree_path(root, "t", "repo-a") / "x").write_text("sucio")
    stopped = []
    with pytest.raises(SessionError) as e:
        delete_session(root, "t", stop=stopped.append)
    assert e.value.code == "uncommitted_changes" and stopped == []
    assert worktree_path(root, "t", "repo-a").exists()
    delete_session(root, "t", force=True, stop=stopped.append)
    assert stopped == ["t"] and not session_path(root, "t").exists()
    assert not worktree_path(root, "t", "repo-a").exists()


def test_refresh_review_moves_head(tmp_path):
    root = _ws(tmp_path)
    sha1 = _git("rev-parse", "HEAD", cwd=root / "repo-a")
    runner, _ = _fake_gh(sha1)
    create_session(root, {"review": "https://github.com/acme/repo-a/pull/9"}, runner=runner)
    _git("commit", "-q", "--allow-empty", "-m", "y", cwd=root / "repo-a")
    sha2 = _git("rev-parse", "HEAD", cwd=root / "repo-a")
    runner2, _ = _fake_gh(sha2)
    s = refresh_review(root, "pr-repo-a-9", runner=runner2)
    assert s["reviewedSha"] == sha2
    assert _git("rev-parse", "HEAD", cwd=worktree_path(root, "pr-repo-a-9", "repo-a")) == sha2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_session_ops.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ide_server.session_ops'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/session_ops.py
from __future__ import annotations
import io
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable
from ide_server.config import sessions_config
from ide_server.repos_fs import add_repo, rm_repo, worktree_path, require_session
from ide_server.sessions_fs import (
    SessionError, create_session_dir, new_id, normalize_id, read_session, render_template,
    session_path, sessions_dir, update_session_toml, read_toml,
)
from ide_server.workspace import discover_repos
from ide_server.worktrees import has_uncommitted_changes

Runner = Callable[[list[str]], subprocess.CompletedProcess]
_PR_RE = re.compile(r"^https://github\.com/[^/]+/([^/]+)/pull/(\d+)")


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]} no está instalado")


def parse_pr_url(url: str) -> tuple[str, int]:
    m = _PR_RE.match(url.strip())
    if not m:
        raise SessionError("bad_pr_url", f"URL de PR inválida: {url!r} "
                                         "(esperado https://github.com/<owner>/<repo>/pull/<n>)")
    return m.group(1), int(m.group(2))


def load_template(root: Path, name: str) -> str:
    path = sessions_dir(root) / "templates" / f"{name}.md"
    if not path.is_file():
        raise SessionError("unknown_template", f"no existe la plantilla {name} ({path})")
    return path.read_text(encoding="utf-8")


def _gh_pr(url: str, runner: Runner) -> dict:
    out = runner(["gh", "pr", "view", url, "--json", "title,author,headRefOid,state"])
    if out.returncode != 0:
        raise SessionError("gh_failed", f"gh pr view falló: {out.stderr.strip() or out.returncode}")
    return json.loads(out.stdout)


def _fetch_pr(root: Path, repo: str, number: int, runner: Runner) -> None:
    out = runner(["git", "-C", str(root / repo), "fetch", "origin", f"pull/{number}/head"])
    if out.returncode != 0:
        raise SessionError("fetch_failed", f"git fetch del PR falló: {out.stderr.strip()}")


def create_session(root: Path, req: dict, *, runner: Runner = _run) -> dict:
    permissions = req.get("permissions") or sessions_config(root)["default_permissions"]
    if req.get("review"):
        return _create_review(root, req["review"], permissions, runner)
    kind = "main" if req.get("main") else "ticket"
    sid = normalize_id(req["id"]) if req.get("id") else new_id(
        lambda s: session_path(root, s).exists())
    variables = {"id": sid, **(req.get("vars") or {})}
    prompt = (render_template(load_template(root, req["template"]), variables)
              if req.get("template") else req.get("prompt") or "")
    meta = None
    if kind == "ticket":
        meta = {"title": req.get("title") or variables.get("title"),
                "notion_url": variables.get("notion_url")}
    create_session_dir(root, sid=sid, kind=kind, permissions=permissions, prompt=prompt, meta=meta)
    return {"session": read_session(root, sid), "log": ""}


def _create_review(root: Path, url: str, permissions: str, runner: Runner) -> dict:
    repo, number = parse_pr_url(url)
    if repo not in {r["id"] for r in discover_repos(root)}:
        raise SessionError("unknown_repo", f"el PR es de {repo}, que no está en el workspace")
    sid = normalize_id(f"pr-{repo}-{number}")
    if session_path(root, sid).exists():
        raise SessionError("session_exists", f"ya existe la sesión {sid}")
    pr = _gh_pr(url, runner)
    author = "@" + pr["author"]["login"]
    prompt = render_template(load_template(root, "review"), {
        "id": sid, "title": pr["title"], "pr_url": url, "author": author, "repo": repo})
    create_session_dir(root, sid=sid, kind="review", permissions=permissions, prompt=prompt,
                       meta={"title": pr["title"], "author": author, "pr_url": url})
    log = io.StringIO()
    try:
        update_session_toml(root, sid, lambda d: d.update(pr_url=url, reviewed_sha=pr["headRefOid"]))
        _fetch_pr(root, repo, number, runner)
        try:
            add_repo(root, sid, repo, detach_at=pr["headRefOid"], out=log)
        except SessionError as exc:
            if exc.code != "setup_failed":
                raise
            log.write(f"\n{exc}\n")              # setup fallido: la sesión queda, marcada
    except Exception:
        wt = worktree_path(root, sid, repo)
        if wt.exists():
            subprocess.run(["git", "-C", str(root / repo), "worktree", "remove", "--force", str(wt)],
                           capture_output=True)
        shutil.rmtree(session_path(root, sid), ignore_errors=True)
        raise
    return {"session": read_session(root, sid), "log": log.getvalue()}


def delete_session(root: Path, sid: str, *, force: bool = False,
                   stop: Callable[[str], None] | None = None) -> None:
    spath = require_session(root, sid)
    repos = [p.name for p in spath.iterdir() if p.is_symlink()]
    if not force:
        dirty = [r for r in repos if worktree_path(root, sid, r).exists()
                 and has_uncommitted_changes(worktree_path(root, sid, r))]
        if dirty:
            raise SessionError("uncommitted_changes",
                               f"cambios sin commitear en {', '.join(dirty)} (usa --force)")
    if stop is not None:
        stop(sid)
    for repo in repos:
        rm_repo(root, sid, repo, force=force, out=io.StringIO())
    shutil.rmtree(spath)
    try:
        (root / ".ide" / "worktrees" / sid).rmdir()
    except OSError:
        pass


def refresh_review(root: Path, sid: str, *, runner: Runner = _run) -> dict:
    data = read_toml(require_session(root, sid) / ".session.toml")
    url = data.get("pr_url")
    if data.get("kind") != "review" or not url:
        raise SessionError("not_a_review", f"{sid} no es una revisión de PR")
    repo, number = parse_pr_url(url)
    wt = worktree_path(root, sid, repo)
    if has_uncommitted_changes(wt):
        raise SessionError("uncommitted_changes", f"{repo} en {sid} tiene cambios sin commitear")
    sha = _gh_pr(url, runner)["headRefOid"]
    _fetch_pr(root, repo, number, runner)
    out = runner(["git", "-C", str(wt), "checkout", "--detach", sha])
    if out.returncode != 0:
        raise SessionError("checkout_failed", f"checkout del head nuevo falló: {out.stderr.strip()}")
    update_session_toml(root, sid, lambda d: d.update(reviewed_sha=sha))
    return read_session(root, sid)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_session_ops.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/session_ops.py server/tests/test_session_ops.py
git commit -m "feat(sesiones): crear por plantilla/revisión de PR, borrar seguro y refrescar review

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `PrPoller`

**Files:**
- Create: `server/ide_server/pr_poller.py`
- Test: `server/tests/test_pr_poller.py`

**Interfaces:**
- Consumes: Task 2 (`list_sessions`).
- Produces: `GhRunner = Callable[[list[str]], Awaitable[tuple[int, str, str]]]`; `class PrPoller(root, *, interval: int, run_gh: GhRunner | None = None, on_change=None, clock=time.time, concurrency=4)`: `derived: dict[str, dict]` (`{"prState": "stale"|"merged"|"closed"|None, "pollError": str|None, "lastOk": str|None}`), `async poll_once() -> bool`, `next_delay() -> float`, `async run(stop: asyncio.Event) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_pr_poller.py
import asyncio, json
import pytest
from ide_server.pr_poller import PrPoller
from ide_server.sessions_fs import create_session_dir, update_session_toml


def _review(root, sid, url, sha):
    create_session_dir(root, sid=sid, kind="review", permissions="analyze", prompt="")
    update_session_toml(root, sid, lambda d: d.update(pr_url=url, reviewed_sha=sha))


def _gh(answers):
    async def run(args):
        url = args[2]
        a = answers[url]
        if isinstance(a, str):
            return 1, "", a
        return 0, json.dumps(a), ""
    return run


@pytest.mark.asyncio
async def test_poll_derives_states(tmp_path):
    _review(tmp_path, "r1", "u1", "aaa"); _review(tmp_path, "r2", "u2", "bbb")
    _review(tmp_path, "r3", "u3", "ccc")
    create_session_dir(tmp_path, sid="t", kind="ticket", permissions="analyze", prompt="")
    p = PrPoller(tmp_path, interval=60, clock=lambda: 0, run_gh=_gh({
        "u1": {"headRefOid": "aaa", "state": "OPEN"},
        "u2": {"headRefOid": "zzz", "state": "OPEN"},
        "u3": {"headRefOid": "ccc", "state": "MERGED"}}))
    assert await p.poll_once() is True
    assert p.derived["r1"]["prState"] is None
    assert p.derived["r2"]["prState"] == "stale"
    assert p.derived["r3"]["prState"] == "merged"
    assert "t" not in p.derived
    assert await p.poll_once() is False          # sin cambios → no notifica


@pytest.mark.asyncio
async def test_poll_error_keeps_last_state_marked_and_backs_off(tmp_path):
    _review(tmp_path, "r1", "u1", "aaa")
    answers = {"u1": {"headRefOid": "zzz", "state": "OPEN"}}
    p = PrPoller(tmp_path, interval=60, clock=lambda: 0, run_gh=_gh(answers))
    await p.poll_once()
    answers["u1"] = "HTTP 401: Bad credentials"
    await p.poll_once()
    d = p.derived["r1"]
    assert d["prState"] == "stale" and "401" in d["pollError"] and d["lastOk"]
    assert p.next_delay() == 120
    await p.poll_once()
    assert p.next_delay() == 240
    await p.poll_once()
    assert p.next_delay() == 240                  # tope 4× intervalo
    answers["u1"] = {"headRefOid": "zzz", "state": "OPEN"}
    await p.poll_once()
    assert p.next_delay() == 60 and p.derived["r1"]["pollError"] is None


@pytest.mark.asyncio
async def test_run_disabled_and_stops(tmp_path):
    p = PrPoller(tmp_path, interval=0, run_gh=_gh({}))
    await asyncio.wait_for(p.run(asyncio.Event()), 1)       # interval 0 → retorna ya
    stop = asyncio.Event(); calls = []
    p2 = PrPoller(tmp_path, interval=60, run_gh=_gh({}), on_change=lambda: calls.append(1))
    task = asyncio.create_task(p2.run(stop))
    await asyncio.sleep(0.05); stop.set()
    await asyncio.wait_for(task, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_pr_poller.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ide_server.pr_poller'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/pr_poller.py
from __future__ import annotations
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable
from ide_server.sessions_fs import list_sessions

GhRunner = Callable[[list[str]], Awaitable[tuple[int, str, str]]]


async def _default_gh(args: list[str]) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        return 127, "", "gh no está instalado"
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(), err.decode()


class PrPoller:
    def __init__(self, root: Path, *, interval: int, run_gh: GhRunner | None = None,
                 on_change: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.time, concurrency: int = 4) -> None:
        self._root, self._interval = root, interval
        self._gh = run_gh or _default_gh
        self._on_change = on_change or (lambda: None)
        self._clock = clock
        self._sem = asyncio.Semaphore(concurrency)
        self._failures = 0
        self.derived: dict[str, dict] = {}

    async def _poll(self, s: dict) -> tuple[str, dict]:
        prev = self.derived.get(s["id"], {"prState": None, "pollError": None, "lastOk": None})
        async with self._sem:
            code, out, err = await self._gh(["pr", "view", s["prUrl"], "--json", "headRefOid,state"])
        if code != 0:
            return s["id"], {**prev, "pollError": err.strip() or f"gh exit {code}"}
        data = json.loads(out)
        state = {"MERGED": "merged", "CLOSED": "closed"}.get(data.get("state", ""))
        if state is None and data.get("headRefOid") != s.get("reviewedSha"):
            state = "stale"
        ts = datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(timespec="seconds")
        return s["id"], {"prState": state, "pollError": None, "lastOk": ts}

    async def poll_once(self) -> bool:
        reviews = [s for s in list_sessions(self._root)
                   if s["kind"] == "review" and s.get("prUrl")]
        results = dict(await asyncio.gather(*(self._poll(s) for s in reviews)))
        self._failures = self._failures + 1 if any(r["pollError"] for r in results.values()) else 0

        def key(d: dict) -> dict:
            return {k: v for k, v in d.items() if k != "lastOk"}
        changed = {k: key(v) for k, v in results.items()} != \
                  {k: key(v) for k, v in self.derived.items()}
        self.derived = results
        return changed

    def next_delay(self) -> float:
        if self._failures == 0:
            return float(self._interval)
        return float(min(self._interval * 2 ** self._failures, 4 * self._interval))

    async def run(self, stop: asyncio.Event) -> None:
        if self._interval <= 0:
            return
        while not stop.is_set():
            if await self.poll_once():
                self._on_change()
            try:
                await asyncio.wait_for(stop.wait(), self.next_delay())
            except asyncio.TimeoutError:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_pr_poller.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/pr_poller.py server/tests/test_pr_poller.py
git commit -m "feat(revisiones): poller de PRs con gh (stale/merged/closed + backoff)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Watcher del disco

**Files:**
- Create: `server/ide_server/watcher.py`
- Test: `server/tests/test_watcher.py`

**Interfaces:**
- Produces: `relevant(root, path: str) -> bool` (solo `sessions/<archivo>`, `sessions/<id>/<archivo|symlink>`, `sessions/templates/*`, `scripts/**`; ignora lo de adentro de worktrees); `async watch_workspace(root, on_change: Callable[[], None], *, stop_event: asyncio.Event, debounce_ms=300) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_watcher.py
import asyncio
import pytest
from ide_server.watcher import relevant, watch_workspace


def test_relevant_filters_depth(tmp_path):
    s = tmp_path / ".ide" / "sessions"
    assert relevant(tmp_path, str(s / "a" / "TICKET.md"))
    assert relevant(tmp_path, str(s / "a"))
    assert relevant(tmp_path, str(tmp_path / ".ide" / "scripts" / "repo" / "run"))
    assert not relevant(tmp_path, str(s / "a" / "repo-a" / "src" / "x.py"))
    assert not relevant(tmp_path, str(tmp_path / ".ide" / "worktrees" / "a" / "f"))


@pytest.mark.asyncio
async def test_watch_reports_ticket_change(tmp_path):
    (tmp_path / ".ide" / "sessions" / "a").mkdir(parents=True)
    hits, stop = [], asyncio.Event()
    task = asyncio.create_task(watch_workspace(tmp_path, lambda: hits.append(1),
                                               stop_event=stop, debounce_ms=50))
    await asyncio.sleep(0.3)
    (tmp_path / ".ide" / "sessions" / "a" / "TICKET.md").write_text("---\nstatus: ready\n---\n")
    for _ in range(40):
        if hits:
            break
        await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(task, 3)
    assert hits
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_watcher.py -q`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/watcher.py
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Callable


def relevant(root: Path, path: str) -> bool:
    ide = (root / ".ide").resolve()
    try:
        rel = Path(path).resolve().relative_to(ide).parts
    except ValueError:
        try:
            rel = Path(path).relative_to(root / ".ide").parts
        except ValueError:
            return False
    if not rel:
        return False
    if rel[0] == "scripts":
        return True
    return rel[0] == "sessions" and len(rel) <= 3


async def watch_workspace(root: Path, on_change: Callable[[], None], *,
                          stop_event: asyncio.Event, debounce_ms: int = 300) -> None:
    from watchfiles import awatch
    paths = [root / ".ide" / "sessions", root / ".ide" / "scripts"]
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
    async for _ in awatch(*paths, debounce=debounce_ms, stop_event=stop_event,
                          watch_filter=lambda _c, path: relevant(root, path)):
        on_change()
```

Nota: `Path(path).resolve()` sobre un archivo dentro de un worktree (vía symlink) resuelve a `.ide/worktrees/...` → `rel[0] == "worktrees"` → irrelevante. El fallback sin `resolve` cubre archivos borrados.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_watcher.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add server/ide_server/watcher.py server/tests/test_watcher.py
git commit -m "feat(sesiones): watcher de .ide/sessions y .ide/scripts (filtra worktrees)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Capability `folder_sessions` + HTTP + wiring de la app

**Files:**
- Create: `server/ide_server/capabilities/folder_sessions.py`
- Modify: `server/ide_server/app.py` (registrar, HTTP, startup/shutdown, `server_url`)
- Modify: `server/ide_server/bus.py` (mapear `SessionError`)
- Modify: `server/ide_server/workspace.py` (`resolve_cwd`/`resolve_repo` entienden sesiones-carpeta)
- Modify: `server/ide_server/cli.py` (`_launch` pasa `server_url`)
- Modify: `server/tests/test_sessions_app.py` (reemplazar tests del árbol viejo)
- Test: `server/tests/test_folder_sessions_capability.py`

**Interfaces:**
- Consumes: Tasks 2–10, `TerminalHooks` (Task 7).
- Produces WS channels: `sessions.tree` → `{"sessions": [...], "workspaceRepos": [...], "scripts": {repo: [{name, executable}]}}` (cada sesión además con `process`, `terminalId`, `launchError`, y si es review `prState`, `pollError`, `lastOk`); `sessions.new` (req de Task 8) → `{"session", "log", "process"}`; `sessions.open {id}` → `{"process"}`; `sessions.stop {id}`; `sessions.rm {id, force?}`; `sessions.script {id, repo, name}` → `{"terminalId"}`; `sessions.doc {id}` → `{"name", "text"}`; `sessions.refreshReview {id}` → `{"session"}`; `sessions.repoRm {id, repo, force?}` → `{"ok"}` (acción "quitar" de un repo `missing`/no deseado); `ui.config` → `{"modules"}`. Evento: `sessions.changed` con el mismo payload que `sessions.tree`.
- HTTP: `POST /api/sessions` (body = req), `POST /api/sessions/{sid}/open`, `POST /api/sessions/{sid}/stop`, `GET /api/sessions` (= tree). Error → status 409 (`SessionError`, `BranchOccupied`) o 500, body `{"code","message"}`.
- `register(registry, root, manager, *, hooks, supervisor, poller) -> Callable[[], None]` (devuelve `notify`).
- `create_app(root, web_dir=None, *, server_url=None, claude_command=None)`.

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_folder_sessions_capability.py
import asyncio, io, subprocess
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import folder_sessions as cap
from ide_server.supervisor import Supervisor
from ide_server.pr_poller import PrPoller
from ide_server.sessions_fs import seed_workspace, session_path
from ide_server.repos_fs import add_repo, worktree_path


class Rec:
    def __init__(self): self.events = []
    async def broadcast(self, channel, payload): self.events.append((channel, payload))


class FakeHooks:
    def __init__(self): self.spawned, self.killed, self.n = [], [], 0
    def spawn(self, cwd, argv, env, on_exit, session_id=None):
        self.n += 1; self.spawned.append((cwd, argv, env)); return f"t{self.n}"
    def kill(self, tid): self.killed.append(tid)


def _ws(tmp_path):
    r = tmp_path / "repo-a"; r.mkdir()
    for a in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=r, check=True)
    seed_workspace(tmp_path)
    s = tmp_path / ".ide" / "scripts" / "repo-a"; s.mkdir(parents=True, exist_ok=True)
    (s / "run").write_text("#!/bin/sh\necho corriendo $IDE_PORT\n"); (s / "run").chmod(0o755)
    return tmp_path


def _reg(root):
    reg, rec, hooks = Registry(), Rec(), FakeHooks()
    sup = Supervisor(root, spawn=hooks.spawn, kill=hooks.kill, server_url="u",
                     home=root / "home", which=lambda c: "/x")
    poller = PrPoller(root, interval=0)
    notify = cap.register(reg, root, rec, hooks=hooks, supervisor=sup, poller=poller)
    return reg, rec, hooks, sup


@pytest.mark.asyncio
async def test_new_starts_and_tree_reports_process(tmp_path):
    reg, rec, hooks, _ = _reg(_ws(tmp_path))
    out = await reg.dispatch("sessions.new", {"id": "FIN-1", "template": "ticket",
                             "vars": {"title": "T", "notion_url": "n", "body": "b"}})
    assert out["session"]["id"] == "fin-1" and out["process"] == "running"
    tree = await reg.dispatch("sessions.tree", {})
    s = tree["sessions"][0]
    assert s["process"] == "running" and s["terminalId"] == "t1"
    assert tree["workspaceRepos"][0]["id"] == "repo-a"
    assert tree["scripts"]["repo-a"] == [{"name": "run", "executable": True}]
    await asyncio.sleep(0)
    assert any(c == "sessions.changed" for c, _ in rec.events)


@pytest.mark.asyncio
async def test_stop_open_rm(tmp_path):
    root = _ws(tmp_path)
    reg, _, hooks, sup = _reg(root)
    await reg.dispatch("sessions.new", {"id": "a", "prompt": "p"})
    await reg.dispatch("sessions.stop", {"id": "a"})
    assert hooks.killed == ["t1"] and sup.state("a") == "stopped"
    assert (await reg.dispatch("sessions.open", {"id": "a"}))["process"] == "running"
    add_repo(root, "a", "repo-a", out=io.StringIO())
    (worktree_path(root, "a", "repo-a") / "x").write_text("sucio")
    from ide_server.sessions_fs import SessionError
    with pytest.raises(SessionError):
        await reg.dispatch("sessions.rm", {"id": "a"})
    assert sup.state("a") == "running"                     # Review Focus 5: no tocó nada
    await reg.dispatch("sessions.rm", {"id": "a", "force": True})
    assert sup.state("a") == "stopped" and not session_path(root, "a").exists()


@pytest.mark.asyncio
async def test_script_spawns_in_worktree_with_env(tmp_path):
    root = _ws(tmp_path)
    reg, _, hooks, _ = _reg(root)
    await reg.dispatch("sessions.new", {"id": "a", "prompt": ""})
    add_repo(root, "a", "repo-a", out=io.StringIO())
    out = await reg.dispatch("sessions.script", {"id": "a", "repo": "repo-a", "name": "run"})
    cwd, argv, env = hooks.spawned[-1]
    assert out["terminalId"] == "t2" and cwd == worktree_path(root, "a", "repo-a")
    assert argv[0].endswith("/run") and env["IDE_PORT"] == "8100"


@pytest.mark.asyncio
async def test_repo_rm_missing(tmp_path):
    import shutil
    root = _ws(tmp_path)
    reg, *_ = _reg(root)
    await reg.dispatch("sessions.new", {"id": "a", "prompt": ""})
    add_repo(root, "a", "repo-a", out=io.StringIO())
    shutil.rmtree(worktree_path(root, "a", "repo-a"))
    tree = await reg.dispatch("sessions.tree", {})
    assert tree["sessions"][0]["repos"][0]["state"] == "missing"
    await reg.dispatch("sessions.repoRm", {"id": "a", "repo": "repo-a"})
    assert (await reg.dispatch("sessions.tree", {}))["sessions"][0]["repos"] == []


@pytest.mark.asyncio
async def test_doc_and_ui_config(tmp_path):
    reg, *_ = _reg(_ws(tmp_path))
    await reg.dispatch("sessions.new", {"id": "a", "title": "Hola"})
    doc = await reg.dispatch("sessions.doc", {"id": "a"})
    assert doc["name"] == "TICKET.md" and "status: analyzing" in doc["text"]
    assert (await reg.dispatch("ui.config", {}))["modules"] == ["sessions", "terminal"]
```

Reemplazar **todo** el contenido de `server/tests/test_sessions_app.py` por:

```python
import json, subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from ide_server.app import create_app
from ide_server.sessions_fs import seed_workspace


def _ws(tmp_path: Path) -> Path:
    repo = tmp_path / "repoA"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, check=True)
    seed_workspace(tmp_path)
    return tmp_path


def test_api_sessions_tree_empty(tmp_path):
    c = TestClient(create_app(_ws(tmp_path), claude_command="sleep 30"))
    body = c.get("/api/sessions").json()
    assert body["sessions"] == [] and body["workspaceRepos"][0]["id"] == "repoA"


def test_api_new_conflict_is_409(tmp_path):
    with TestClient(create_app(_ws(tmp_path), claude_command="sleep 30")) as c:
        assert c.post("/api/sessions", json={"id": "a", "prompt": ""}).status_code == 200
        r = c.post("/api/sessions", json={"id": "a", "prompt": ""})
        assert r.status_code == 409 and r.json()["code"] == "session_exists"
        assert c.post("/api/sessions/a/stop").status_code == 200


def test_ws_session_error_envelope(tmp_path):
    c = TestClient(create_app(_ws(tmp_path), claude_command="sleep 30"))
    with c.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "req", "id": "1", "channel": "sessions.open",
                                 "payload": {"id": "nope"}}))
        out = json.loads(ws.receive_text())
        assert out["type"] == "error" and out["payload"]["code"] == "unknown_session"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest tests/test_folder_sessions_capability.py tests/test_sessions_app.py -q`
Expected: FAIL (`ModuleNotFoundError: ...folder_sessions`; `create_app() got an unexpected keyword argument 'claude_command'`).

- [ ] **Step 3: Write the capability**

```python
# server/ide_server/capabilities/folder_sessions.py
from __future__ import annotations
import asyncio
import io
from pathlib import Path
from typing import Callable
from ide_server.config import ui_modules
from ide_server.plugins import Registry
from ide_server.pr_poller import PrPoller
from ide_server.repos_fs import require_session, rm_repo, worktree_path
from ide_server.scripts import list_scripts, script_argv, script_env
from ide_server.session_ops import create_session, delete_session, refresh_review
from ide_server.sessions_fs import list_sessions, read_toml, session_path, state_file, SessionError
from ide_server.supervisor import Supervisor
from ide_server.workspace import discover_repos


def register(registry: Registry, root: Path, manager, *, hooks, supervisor: Supervisor,
             poller: PrPoller) -> Callable[[], None]:

    def tree_payload() -> dict:
        snap = supervisor.snapshot()
        sessions = list_sessions(root)
        for s in sessions:
            p = snap.get(s["id"], {})
            s.update(process=p.get("process", "stopped"), terminalId=p.get("terminalId"),
                     launchError=p.get("launchError"))
            if s["kind"] == "review":
                s.update({"prState": None, "pollError": None, "lastOk": None,
                          **poller.derived.get(s["id"], {})})
        repos = discover_repos(root)
        return {"sessions": sessions, "workspaceRepos": repos,
                "scripts": {r["id"]: list_scripts(root, r["id"]) for r in repos}}

    def notify() -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(manager.broadcast("sessions.changed", tree_payload()))

    async def tree(_p: dict) -> dict:
        return tree_payload()

    async def new(p: dict) -> dict:
        res = create_session(root, p)
        process = supervisor.start(res["session"]["id"], resume=False)
        notify()
        return {**res, "process": process}

    async def open_(p: dict) -> dict:
        return {"process": supervisor.start(p["id"])}

    async def stop(p: dict) -> dict:
        supervisor.stop(p["id"])
        return {"ok": True}

    async def rm(p: dict) -> dict:
        delete_session(root, p["id"], force=bool(p.get("force")), stop=supervisor.stop)
        notify()
        return {"ok": True}

    async def script(p: dict) -> dict:
        require_session(root, p["id"])
        argv = script_argv(root, p["repo"], p["name"])
        tid = hooks.spawn(worktree_path(root, p["id"], p["repo"]), argv,
                          script_env(root, p["id"], p["repo"]), notify, session_id=p["id"])
        return {"terminalId": tid}

    async def doc(p: dict) -> dict:
        path = require_session(root, p["id"])
        name = state_file(read_toml(path / ".session.toml").get("kind"))
        if name is None:
            raise SessionError("no_doc", f"{p['id']} no tiene TICKET.md/REVIEW.md")
        f = path / name
        return {"name": name, "text": f.read_text(encoding="utf-8") if f.is_file() else ""}

    async def refresh(p: dict) -> dict:
        s = refresh_review(root, p["id"])
        await poller.poll_once()
        notify()
        return {"session": s}

    async def repo_rm(p: dict) -> dict:
        rm_repo(root, p["id"], p["repo"], force=bool(p.get("force")), out=io.StringIO())
        notify()
        return {"ok": True}

    async def ui_config(_p: dict) -> dict:
        return {"modules": ui_modules(root)}

    for channel, handler in {
        "sessions.tree": tree, "sessions.new": new, "sessions.open": open_,
        "sessions.stop": stop, "sessions.rm": rm, "sessions.script": script,
        "sessions.doc": doc, "sessions.refreshReview": refresh, "sessions.repoRm": repo_rm,
        "ui.config": ui_config,
    }.items():
        registry.register(channel, handler)
    return notify
```

- [ ] **Step 4: Bus — mapear `SessionError`**

En `server/ide_server/bus.py`, importar `from ide_server.sessions_fs import SessionError` y agregar **antes** del `except Exception`:

```python
    except SessionError as exc:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": exc.code, "message": str(exc)}})
```

- [ ] **Step 5: App wiring**

En `server/ide_server/app.py`:
- Quitar `from ide_server.capabilities import sessions as sessions_cap` y la línea `sessions_cap.register(registry, root)`.
- Importar:
```python
import asyncio
from fastapi.responses import JSONResponse
from ide_server.capabilities import folder_sessions as folder_cap
from ide_server.config import sessions_config, reviews_config
from ide_server.pr_poller import PrPoller
from ide_server.sessions_fs import SessionError
from ide_server.supervisor import Supervisor
from ide_server.watcher import watch_workspace
from ide_server.worktrees import BranchOccupied
```
- Firma: `def create_app(root: Path, web_dir: Path | None = None, *, server_url: str | None = None, claude_command: str | None = None) -> FastAPI:`
- Reemplazar `terminals_cap.register(registry, root, manager)` por:
```python
    hooks = terminals_cap.register(registry, root, manager)
    scfg = sessions_config(root)
    notify_box: dict = {"fn": lambda: None}
    supervisor = Supervisor(
        root, spawn=hooks.spawn, kill=hooks.kill,
        server_url=server_url or f"http://{settings.host}:{settings.port}",
        command=claude_command or scfg["claude_command"], max_running=scfg["max_running"],
        on_change=lambda: notify_box["fn"]())
    poller = PrPoller(root, interval=reviews_config(root)["poll_interval"],
                      on_change=lambda: notify_box["fn"]())
    notify_box["fn"] = folder_cap.register(registry, root, manager, hooks=hooks,
                                           supervisor=supervisor, poller=poller)
```
- Después de crear `app`, reemplazar el `@app.get("/api/sessions")` existente por:
```python
    stop_bg = asyncio.Event()

    @app.on_event("startup")
    async def _start_bg() -> None:
        app.state.bg = [
            asyncio.create_task(watch_workspace(root, lambda: notify_box["fn"](), stop_event=stop_bg)),
            asyncio.create_task(poller.run(stop_bg)),
        ]

    @app.on_event("shutdown")
    async def _stop_bg() -> None:
        stop_bg.set()
        for t in getattr(app.state, "bg", []):
            t.cancel()

    async def _http(channel: str, payload: dict):
        try:
            return await registry.dispatch(channel, payload)
        except (SessionError, BranchOccupied) as exc:
            code = getattr(exc, "code", "branch_occupied")
            return JSONResponse({"code": code, "message": str(exc)}, status_code=409)
        except Exception as exc:  # noqa: BLE001 — nunca silencioso
            return JSONResponse({"code": "handler_error", "message": str(exc)}, status_code=500)

    @app.get("/api/sessions")
    async def api_sessions():
        return await _http("sessions.tree", {})

    @app.post("/api/sessions")
    async def api_new(body: dict):
        return await _http("sessions.new", body)

    @app.post("/api/sessions/{sid}/open")
    async def api_open(sid: str):
        return await _http("sessions.open", {"id": sid})

    @app.post("/api/sessions/{sid}/stop")
    async def api_stop(sid: str):
        return await _http("sessions.stop", {"id": sid})
```

En `server/ide_server/cli.py` `_launch`: `serve(create_app(root, web_dir, server_url=url), host, port)`.

- [ ] **Step 6: `resolve_cwd`/`resolve_repo` entienden sesiones-carpeta**

En `server/ide_server/workspace.py`, al principio de ambas funciones (antes del `from ide_server.sessions_store import ...`):

```python
def _folder_session(root: Path, payload: dict) -> Path | None:
    sid = payload.get("sessionId")
    if not sid:
        return None
    path = root / ".ide" / "sessions" / sid
    return path if (path / ".session.toml").is_file() else None


def resolve_cwd(root: Path, payload: dict) -> Path:
    folder = _folder_session(root, payload)
    if folder is not None:
        repo = payload.get("repoId")
        return (folder / repo).resolve() if repo and (folder / repo).exists() else folder
    ...  # cuerpo existente sin cambios


def resolve_repo(root: Path, payload: dict) -> Path:
    folder = _folder_session(root, payload)
    if folder is not None:
        repos = [p.name for p in folder.iterdir() if p.is_symlink()]
        repo = payload.get("repoId") or (repos[0] if len(repos) == 1 else None)
        if repo is None:
            raise KeyError("la sesión tiene 0 o varios repos: indica repoId")
        return root / repo
    ...  # cuerpo existente sin cambios
```

- [ ] **Step 7: Run tests**

Run: `cd server && uv run pytest -q`
Expected: PASS completo. Tests viejos que importan `capabilities.sessions` directamente siguen pasando (el módulo no se borra, solo no se registra en la app).

- [ ] **Step 8: Commit**

```bash
git add server/ide_server/capabilities/folder_sessions.py server/ide_server/app.py server/ide_server/bus.py server/ide_server/workspace.py server/ide_server/cli.py server/tests/test_folder_sessions_capability.py server/tests/test_sessions_app.py
git commit -m "feat(sesiones): capability de sesiones-carpeta (WS + HTTP), watcher y poller en la app

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: CLI `ide session | repo | script`

**Files:**
- Create: `server/ide_server/cli_sessions.py`
- Modify: `server/ide_server/cli.py` (delegar + `HELP_TEXT`)
- Test: `server/tests/test_cli_sessions.py`

**Interfaces:**
- Consumes: Tasks 2–8, `instances.list_instances`, `workspace.find_workspace_root`.
- Desvío menor del spec: `ide session open` sobre una revisión `stale` no pregunta; el refresco del head se hace con el botón **Refrescar** de la UI (Task 17).
- Produces: `find_server_url(root, env, home) -> str | None`; `current_session(root, *, env, cwd, explicit=None) -> str`; `main(argv, *, cwd, env, home, http=httpx, out=sys.stdout, err=sys.stderr) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_cli_sessions.py
import io, json, subprocess
import pytest
from ide_server.cli_sessions import main, current_session, find_server_url
from ide_server.sessions_fs import seed_workspace, session_path, create_session_dir
from ide_server.repos_fs import worktree_path


def _ws(tmp_path):
    r = tmp_path / "repo-a"; r.mkdir()
    for a in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=r, check=True)
    seed_workspace(tmp_path)
    create_session_dir(tmp_path, sid="t1", kind="ticket", permissions="analyze", prompt="")
    return tmp_path


class FakeHttp:
    def __init__(self, status=200, body=None, fail=False):
        self.calls, self.status, self.body, self.fail = [], status, body or {}, fail

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        if self.fail:
            import httpx
            raise httpx.ConnectError("refused")
        return type("R", (), {"status_code": self.status, "json": lambda s: self.body})()

    get = lambda self, url, timeout=None: self.post(url)


def _run(root, argv, *, env=None, cwd=None, http=None):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, cwd=cwd or root, env=env or {}, home=root / "home", http=http or FakeHttp(),
                out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_current_session_resolution(tmp_path):                     # Review Focus 2
    root = _ws(tmp_path)
    assert current_session(root, env={"IDE_SESSION_ID": "t1"}, cwd=root) == "t1"
    assert current_session(root, env={}, cwd=session_path(root, "t1")) == "t1"
    wt = worktree_path(root, "t1", "repo-a"); wt.mkdir(parents=True)
    assert current_session(root, env={}, cwd=wt / "sub") == "t1"
    with pytest.raises(Exception) as e:
        current_session(root, env={}, cwd=root)
    assert "--session" in str(e.value)


def test_repo_add_from_session_env_and_branch_occupied(tmp_path):
    root = _ws(tmp_path)
    code, out, _ = _run(root, ["repo", "add", "repo-a"], env={"IDE_SESSION_ID": "t1"})
    assert code == 0 and "repo-a" in out and "8100" in out
    create_session_dir(root, sid="t2", kind="ticket", permissions="analyze", prompt="")
    code, _, err = _run(root, ["repo", "add", "repo-a", "--branch", "t1", "--session", "t2"])
    assert code == 1 and "--branch" in err


def test_repo_add_from_inside_worktree_without_env(tmp_path):
    root = _ws(tmp_path)
    _run(root, ["repo", "add", "repo-a", "--session", "t1"])
    code, out, _ = _run(root, ["script", "nope"], cwd=worktree_path(root, "t1", "repo-a"))
    assert code == 1                                            # resolvió t1; el script no existe


def test_script_infers_single_repo_and_returns_exit_code(tmp_path):
    root = _ws(tmp_path)
    _run(root, ["repo", "add", "repo-a", "--session", "t1"])
    s = root / ".ide" / "scripts" / "repo-a"; s.mkdir(parents=True, exist_ok=True)
    (s / "test").write_text("#!/bin/sh\necho ok-$IDE_REPO\nexit 4\n"); (s / "test").chmod(0o755)
    code, out, _ = _run(root, ["script", "test"], env={"IDE_SESSION_ID": "t1"})
    assert code == 4 and "ok-repo-a" in out


def test_session_new_needs_server(tmp_path):
    root = _ws(tmp_path)
    code, _, err = _run(root, ["session", "new", "--id", "x"])
    assert code == 1 and "ide run" in err


def test_session_new_posts_payload(tmp_path):
    root = _ws(tmp_path)
    http = FakeHttp(body={"session": {"id": "fin-1", "path": "/p"}, "process": "queued", "log": ""})
    pf = root / "p.md"; pf.write_text("prompt largo")
    code, out, _ = _run(root, ["session", "new", "--id", "FIN-1", "--template", "ticket",
                               "--var", "title=Hola mundo", "--var", "notion_url=u",
                               "--var", "body=b", "--permissions", "full"],
                        env={"IDE_URL": "http://h:1"}, http=http)
    assert code == 0 and out.split()[:2] == ["fin-1", "queued"]
    url, body = http.calls[0]
    assert url == "http://h:1/api/sessions"
    assert body == {"id": "FIN-1", "template": "ticket", "permissions": "full",
                    "vars": {"title": "Hola mundo", "notion_url": "u", "body": "b"}}
    _run(root, ["session", "new", "--main", "--prompt-file", str(pf)],
         env={"IDE_URL": "http://h:1"}, http=http)
    assert http.calls[1][1] == {"main": True, "prompt": "prompt largo"}


def test_session_new_server_error_is_reported(tmp_path):
    root = _ws(tmp_path)
    http = FakeHttp(status=409, body={"code": "session_exists", "message": "ya existe la sesión x"})
    code, _, err = _run(root, ["session", "new", "--id", "x"], env={"IDE_URL": "http://h:1"}, http=http)
    assert code == 1 and "ya existe" in err


def test_session_ls_json_without_server(tmp_path):
    root = _ws(tmp_path)
    code, out, _ = _run(root, ["session", "ls", "--json"], http=FakeHttp(fail=True))
    data = json.loads(out)
    assert code == 0 and data[0]["id"] == "t1" and data[0]["process"] == "?"


def test_session_rm(tmp_path):
    root = _ws(tmp_path)
    code, _, _ = _run(root, ["session", "rm", "t1"], http=FakeHttp(fail=True))
    assert code == 0 and not session_path(root, "t1").exists()


def test_find_server_url_from_instances(tmp_path, monkeypatch):
    root = _ws(tmp_path)
    from ide_server import cli_sessions
    monkeypatch.setattr(cli_sessions.instances, "list_instances",
                        lambda home: [{"workspace": "/otro", "url": "http://a"},
                                      {"workspace": str(root), "url": "http://b"}])
    assert find_server_url(root, {}, root) == "http://b"
    assert find_server_url(root, {"IDE_URL": "http://c"}, root) == "http://c"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_cli_sessions.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'ide_server.cli_sessions'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/ide_server/cli_sessions.py
"""Subcomandos `ide session|repo|script`. Disco in-process; procesos vía HTTP al server."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import TextIO
import httpx
from ide_server import instances
from ide_server.repos_fs import add_repo, rm_repo, require_session
from ide_server.scripts import run_script
from ide_server.session_ops import delete_session
from ide_server.sessions_fs import SessionError, list_sessions, sessions_dir
from ide_server.workspace import find_workspace_root
from ide_server.worktrees import BranchOccupied, WorktreeError

NO_SERVER = "No hay `ide run` activo para este workspace (levántalo con `ide run`)."


def find_server_url(root: Path, env: dict, home: Path) -> str | None:
    if env.get("IDE_URL"):
        return env["IDE_URL"]
    for inst in instances.list_instances(home):
        if inst.get("workspace") == str(root):
            return inst["url"]
    return None


def current_session(root: Path, *, env: dict, cwd: Path, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if env.get("IDE_SESSION_ID"):
        return env["IDE_SESSION_ID"]
    sdir, wdir = sessions_dir(root).resolve(), (root / ".ide" / "worktrees").resolve()
    for p in [cwd.resolve(), *cwd.resolve().parents]:
        if p.parent in (sdir, wdir):
            return p.name
    raise SessionError("no_session", "no estoy dentro de una sesión: usa --session <id>")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ide")
    sub = ap.add_subparsers(dest="group", required=True)
    s = sub.add_parser("session").add_subparsers(dest="cmd", required=True)
    new = s.add_parser("new")
    new.add_argument("--id"); new.add_argument("--main", action="store_true")
    new.add_argument("--title"); new.add_argument("--template")
    new.add_argument("--var", action="append", default=[])
    new.add_argument("--prompt"); new.add_argument("--prompt-file")
    new.add_argument("--permissions", choices=["analyze", "full", "default"])
    new.add_argument("--review")
    ls = s.add_parser("ls"); ls.add_argument("--json", action="store_true")
    for name in ("open", "stop"):
        s.add_parser(name).add_argument("id")
    rm = s.add_parser("rm"); rm.add_argument("id"); rm.add_argument("--force", action="store_true")
    r = sub.add_parser("repo").add_subparsers(dest="cmd", required=True)
    ra = r.add_parser("add"); ra.add_argument("repo"); ra.add_argument("--branch")
    ra.add_argument("--session")
    rr = r.add_parser("rm"); rr.add_argument("repo"); rr.add_argument("--force", action="store_true")
    rr.add_argument("--session")
    sc = sub.add_parser("script"); sc.add_argument("name"); sc.add_argument("repo", nargs="?")
    sc.add_argument("--session")
    return ap


def _new_payload(a) -> dict:
    body: dict = {}
    for key in ("id", "title", "template", "permissions", "review"):
        if getattr(a, key):
            body[key] = getattr(a, key)
    if a.main:
        body["main"] = True
    if a.var:
        body["vars"] = dict(v.split("=", 1) for v in a.var)
    if a.prompt_file:
        body["prompt"] = Path(a.prompt_file).read_text(encoding="utf-8")
    elif a.prompt:
        body["prompt"] = a.prompt
    return body


def _post(http, url: str | None, path: str, body: dict | None = None) -> dict:
    if url is None:
        raise SessionError("no_server", NO_SERVER)
    try:
        r = http.post(f"{url}{path}", json=body or {}, timeout=120)
    except httpx.HTTPError:
        raise SessionError("no_server", NO_SERVER)
    data = r.json()
    if r.status_code >= 400:
        raise SessionError(data.get("code", "server_error"), data.get("message", str(data)))
    return data


def main(argv: list[str], *, cwd: Path, env: dict, home: Path, http=httpx,
         out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> int:
    a = _parser().parse_args(argv)
    root = Path(env["IDE_WORKSPACE"]) if env.get("IDE_WORKSPACE") else find_workspace_root(cwd)
    if root is None:
        err.write("error: no hay workspace (.ide/) aquí ni arriba; ejecuta `ide init`\n")
        return 1
    url = find_server_url(root, env, home)
    try:
        if a.group == "session":
            return _session(a, root, url, http, out)
        sid = current_session(root, env=env, cwd=cwd, explicit=a.session)
        if a.group == "repo" and a.cmd == "add":
            info = add_repo(root, sid, a.repo, branch=a.branch, out=out)
            out.write(f"{info['name']}\t{info['branch'] or '(detached)'}\tIDE_PORT={info['port']}\t"
                      f"{info['path']}\n")
            return 0
        if a.group == "repo":
            rm_repo(root, sid, a.repo, force=a.force, out=out)
            return 0
        repo = a.repo
        if repo is None:
            repos = [p.name for p in require_session(root, sid).iterdir() if p.is_symlink()]
            if len(repos) != 1:
                raise SessionError("ambiguous_repo",
                                   f"la sesión tiene {len(repos)} repos: indica cuál ({', '.join(repos)})")
            repo = repos[0]
        return run_script(root, sid, repo, a.name, out=out)
    except BranchOccupied as exc:
        err.write(f"error: branch ocupada: {exc.branch}. Usa --branch <otra>\n")
    except (SessionError, WorktreeError) as exc:
        err.write(f"error: {exc}\n")
    return 1


def _session(a, root: Path, url: str | None, http, out: TextIO) -> int:
    if a.cmd == "new":
        data = _post(http, url, "/api/sessions", _new_payload(a))
        out.write(f"{data['session']['id']}\t{data['process']}\t{data['session']['path']}\n")
        if data.get("log"):
            out.write(data["log"])
        return 0
    if a.cmd in ("open", "stop"):
        data = _post(http, url, f"/api/sessions/{a.id}/{a.cmd}")
        out.write(f"{a.id}\t{data.get('process', 'stopped')}\n")
        return 0
    if a.cmd == "rm":
        try:
            _post(http, url, f"/api/sessions/{a.id}/stop")
        except SessionError as exc:
            if exc.code != "no_server":
                raise
        delete_session(root, a.id, force=a.force)
        return 0
    sessions = list_sessions(root)
    procs: dict[str, str] = {}
    if url is not None:
        try:
            tree = http.get(f"{url}/api/sessions", timeout=10).json()
            procs = {s["id"]: s.get("process", "?") for s in tree.get("sessions", [])}
        except (httpx.HTTPError, ValueError, AttributeError):
            procs = {}
    for s in sessions:
        s["process"] = procs.get(s["id"], "?")
    if a.json:
        out.write(json.dumps(sessions, ensure_ascii=False, indent=2) + "\n")
        return 0
    for s in sessions:
        repos = ",".join(r["name"] for r in s["repos"]) or "-"
        out.write(f"{s['id']}\t{s['kind']}\t{s['status'] or '-'}\t{s['process']}\t"
                  f"{s['title'] or ''}\t{repos}{'  ⚠ ' + s['error'] if s['error'] else ''}\n")
    return 0
```

Nota: en `test_session_ls_json_without_server` no hay `IDE_URL` ni instancia → `url is None` → `process = "?"`.

- [ ] **Step 4: Delegar desde `cli.main` y actualizar la ayuda**

Al principio de `main` en `server/ide_server/cli.py`, antes de construir el parser:

```python
    import sys as _sys
    raw = list(_sys.argv[1:] if argv is None else argv)
    if raw and raw[0] in ("session", "repo", "script"):
        from ide_server.cli_sessions import main as sessions_main
        return sessions_main(raw, cwd=Path.cwd(), env=dict(os.environ), home=Path.home())
```

En `HELP_TEXT`, agregar después del bloque `ide help`:

```
  ide session new [--id X] [--main] [--template t --var k=v …] [--prompt "…" | --prompt-file f]
                  [--permissions analyze|full|default] [--review <pr-url>]
        Crea una sesión-carpeta (.ide/sessions/<id>/) y lanza `claude` en ella (requiere `ide run`).
  ide session ls [--json] | open <id> | stop <id> | rm <id> [--force]
  ide repo add <repo> [--branch b] | ide repo rm <repo> [--force]
        Agrega/quita un repo (worktree) a la sesión actual; corre su script `setup`/`archive`.
  ide script <nombre> [<repo>]
        Corre .ide/scripts/<repo>/<nombre> en el worktree con env IDE_* (IDE_PORT, …).
```

Y reemplazar el párrafo "EL WORKSPACE (.ide/)" por: `Contiene: config.toml, sessions/ (una carpeta por sesión + CLAUDE.md + templates/), worktrees/, scripts/<repo>/, permissions/. .ide/ es local y no se commitea.` y el bloque "CÓMO UN AGENTE HACE HANDOFF" por: `Las sesiones son \`claude\` interactivos en .ide/sessions/<id>/. Se comunican con el IDE vía este CLI (ver .ide/sessions/CLAUDE.md). Estado en TICKET.md / REVIEW.md (frontmatter status).`

- [ ] **Step 5: Run tests**

Run: `cd server && uv run pytest tests/test_cli_sessions.py tests/test_cli.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/ide_server/cli_sessions.py server/ide_server/cli.py server/tests/test_cli_sessions.py
git commit -m "feat(cli): ide session/repo/script para sesiones-carpeta

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Frontend — transporte, store y detección de desconexión

**Files:**
- Create: `ui/src/transport/folderSessions.ts`
- Create: `ui/src/state/folders.ts`
- Modify: `ui/src/transport/ws.ts` (`onClose`)
- Modify: `ui/src/transport/terminalChannel.ts` (`subscribeTerminal` devuelve unsubscribe)
- Test: `ui/src/transport/folderSessions.test.ts`, `ui/src/state/folders.test.ts`, `ui/src/transport/ws.close.test.ts`

**Interfaces:**
- Produces (transport): tipos `Kind`, `Process`, `RepoInfo`, `FolderSession`, `ScriptInfo`, `SessionsTree`, `NewSessionReq`; funciones `fetchSessions(ws)`, `newSession(ws, req)`, `openSession(ws, id)`, `stopSession(ws, id)`, `rmSession(ws, id, force?)`, `runScript(ws, id, repo, name) -> {terminalId}`, `fetchDoc(ws, id) -> {name, text}`, `refreshReview(ws, id)`, `rmRepo(ws, id, repo, force?)`, `fetchUiConfig(ws) -> {modules}`, `onSessionsChanged(ws, cb) -> () => void`.
- Produces (store `useFolders`): `tree: SessionsTree`, `connected: boolean`, `activeId: string | null`, `groupBy: string`, `modal: null | "session" | "review"`, `uiModules: string[] | null`, `scriptTabs: Record<string, {terminalId: string; label: string}[]>`; acciones `setTree`, `setConnected`, `setActive(id)` (también hace `useSessions.getState().setActive(id)` para los módulos ocultos), `setGroupBy(id)` (persiste en `localStorage["ide.groupBy"]` con try/catch), `openModal`, `closeModal`, `setUiModules`, `addScriptTab(sid, tab)`, `closeScriptTab(sid, terminalId)`.
- `WsClient.onClose(cb: () => void): void`. `subscribeTerminal(...)` → `() => void`.

- [ ] **Step 1: Write the failing tests**

```ts
// ui/src/transport/folderSessions.test.ts
import { describe, it, expect, vi } from "vitest";
import { fetchSessions, newSession, runScript, onSessionsChanged, rmSession } from "./folderSessions";

function fakeWs() {
  const listeners: Record<string, (p: any) => void> = {};
  return {
    request: vi.fn().mockResolvedValue({ ok: true }),
    on: vi.fn((c: string, cb: any) => { listeners[c] = cb; }),
    off: vi.fn((c: string) => { delete listeners[c]; }),
    emit: (c: string, p: any) => listeners[c]?.(p),
  };
}

describe("folderSessions transport", () => {
  it("usa los canales sessions.*", async () => {
    const ws = fakeWs();
    await fetchSessions(ws as any);
    await newSession(ws as any, { id: "FIN-1", template: "ticket", vars: { title: "t" } });
    await runScript(ws as any, "a", "repo-a", "run");
    await rmSession(ws as any, "a", true);
    expect(ws.request.mock.calls.map((c) => c[0])).toEqual(
      ["sessions.tree", "sessions.new", "sessions.script", "sessions.rm"]);
    expect(ws.request.mock.calls[2][1]).toEqual({ id: "a", repo: "repo-a", name: "run" });
    expect(ws.request.mock.calls[3][1]).toEqual({ id: "a", force: true });
  });

  it("onSessionsChanged suscribe y desuscribe", () => {
    const ws = fakeWs(); const cb = vi.fn();
    const off = onSessionsChanged(ws as any, cb);
    ws.emit("sessions.changed", { sessions: [] });
    expect(cb).toHaveBeenCalledWith({ sessions: [] });
    off();
    expect(ws.off).toHaveBeenCalledWith("sessions.changed", expect.any(Function));
  });
});
```

```ts
// ui/src/state/folders.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { useFolders } from "./folders";
import { useSessions } from "./sessions";

describe("useFolders", () => {
  beforeEach(() => { localStorage.clear(); useFolders.setState({ groupBy: "none", activeId: null, scriptTabs: {} }); });

  it("setActive refleja en useSessions para los módulos ocultos", () => {
    useFolders.getState().setActive("fin-1");
    expect(useFolders.getState().activeId).toBe("fin-1");
    expect(useSessions.getState().activeSessionId).toBe("fin-1");
  });

  it("setGroupBy persiste en localStorage", () => {
    useFolders.getState().setGroupBy("status");
    expect(localStorage.getItem("ide.groupBy")).toBe("status");
  });

  it("script tabs por sesión", () => {
    const s = useFolders.getState();
    s.addScriptTab("a", { terminalId: "t9", label: "repo-a:run" });
    s.addScriptTab("a", { terminalId: "t9", label: "repo-a:run" });
    expect(useFolders.getState().scriptTabs.a).toHaveLength(1);
    useFolders.getState().closeScriptTab("a", "t9");
    expect(useFolders.getState().scriptTabs.a).toHaveLength(0);
  });
});
```

```ts
// ui/src/transport/ws.close.test.ts
import { describe, it, expect, vi } from "vitest";
import { WsClient } from "./ws";

class FakeSocket {
  static last: FakeSocket;
  onopen: any; onclose: any; onerror: any; onmessage: any;
  constructor() { FakeSocket.last = this; }
  send() {}
}

describe("WsClient.onClose", () => {
  it("avisa cuando el socket se cierra después de abrir", async () => {
    vi.stubGlobal("WebSocket", FakeSocket as any);
    const ws = new WsClient("ws://x");
    const cb = vi.fn();
    ws.onClose(cb);
    FakeSocket.last.onopen();
    await ws.ready();
    FakeSocket.last.onclose();
    expect(cb).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && npx vitest run src/transport/folderSessions.test.ts src/state/folders.test.ts src/transport/ws.close.test.ts`
Expected: FAIL (módulos inexistentes / `onClose is not a function`).

- [ ] **Step 3: Implement transport**

```ts
// ui/src/transport/folderSessions.ts
import type { WsClient } from "./ws";
import type { Repo } from "./envelope";

export type Kind = "main" | "ticket" | "review";
export type Process = "running" | "queued" | "stopped";
export interface RepoInfo {
  name: string; state: "ok" | "missing"; branch: string | null;
  port: number | null; setup: "ok" | "failed" | null;
}
export interface FolderSession {
  id: string; kind: Kind | null; path: string; created: string; permissions: string | null;
  title: string | null; status: string | null; meta: Record<string, string>; repos: RepoInfo[];
  error: string | null; process: Process; terminalId: string | null; launchError?: string | null;
  prUrl?: string | null; reviewedSha?: string | null;
  prState?: "stale" | "merged" | "closed" | null; pollError?: string | null; lastOk?: string | null;
}
export interface ScriptInfo { name: string; executable: boolean; }
export interface SessionsTree {
  sessions: FolderSession[]; workspaceRepos: Repo[]; scripts: Record<string, ScriptInfo[]>;
}
export interface NewSessionReq {
  id?: string; main?: boolean; title?: string; template?: string;
  vars?: Record<string, string>; prompt?: string;
  permissions?: "analyze" | "full" | "default"; review?: string;
}

export const fetchSessions = (ws: WsClient): Promise<SessionsTree> => ws.request("sessions.tree", {});
export const newSession = (ws: WsClient, req: NewSessionReq) => ws.request("sessions.new", req);
export const openSession = (ws: WsClient, id: string) => ws.request("sessions.open", { id });
export const stopSession = (ws: WsClient, id: string) => ws.request("sessions.stop", { id });
export const rmSession = (ws: WsClient, id: string, force = false) =>
  ws.request("sessions.rm", { id, force });
export const runScript = (ws: WsClient, id: string, repo: string, name: string):
  Promise<{ terminalId: string }> => ws.request("sessions.script", { id, repo, name });
export const fetchDoc = (ws: WsClient, id: string): Promise<{ name: string; text: string }> =>
  ws.request("sessions.doc", { id });
export const refreshReview = (ws: WsClient, id: string) => ws.request("sessions.refreshReview", { id });
export const rmRepo = (ws: WsClient, id: string, repo: string, force = false) =>
  ws.request("sessions.repoRm", { id, repo, force });
export const fetchUiConfig = (ws: WsClient): Promise<{ modules: string[] }> => ws.request("ui.config", {});

export function onSessionsChanged(ws: WsClient, cb: (t: SessionsTree) => void): () => void {
  const handler = (p: SessionsTree) => cb(p);
  ws.on("sessions.changed", handler);
  return () => ws.off("sessions.changed", handler);
}
```

- [ ] **Step 4: Implement store**

```ts
// ui/src/state/folders.ts
import { create } from "zustand";
import type { SessionsTree } from "../transport/folderSessions";
import { useSessions } from "./sessions";

export interface ScriptTab { terminalId: string; label: string; }
const GROUP_KEY = "ide.groupBy";

function readGroupBy(): string {
  try { return localStorage.getItem(GROUP_KEY) ?? "none"; } catch { return "none"; }
}

interface State {
  tree: SessionsTree; connected: boolean; activeId: string | null; groupBy: string;
  modal: null | "session" | "review"; uiModules: string[] | null;
  scriptTabs: Record<string, ScriptTab[]>;
  setTree: (t: SessionsTree) => void; setConnected: (c: boolean) => void;
  setActive: (id: string) => void; setGroupBy: (id: string) => void;
  openModal: (m: "session" | "review") => void; closeModal: () => void;
  setUiModules: (m: string[]) => void;
  addScriptTab: (sid: string, tab: ScriptTab) => void;
  closeScriptTab: (sid: string, terminalId: string) => void;
}

export const useFolders = create<State>((set) => ({
  tree: { sessions: [], workspaceRepos: [], scripts: {} }, connected: true, activeId: null,
  groupBy: readGroupBy(), modal: null, uiModules: null, scriptTabs: {},
  setTree: (tree) => set({ tree, connected: true }),
  setConnected: (connected) => set({ connected }),
  setActive: (activeId) => { useSessions.getState().setActive(activeId); set({ activeId }); },
  setGroupBy: (groupBy) => {
    try { localStorage.setItem(GROUP_KEY, groupBy); } catch { /* storage bloqueado: solo memoria */ }
    set({ groupBy });
  },
  openModal: (modal) => set({ modal }), closeModal: () => set({ modal: null }),
  setUiModules: (uiModules) => set({ uiModules }),
  addScriptTab: (sid, tab) => set((s) => {
    const tabs = s.scriptTabs[sid] ?? [];
    if (tabs.some((t) => t.terminalId === tab.terminalId)) return s;
    return { scriptTabs: { ...s.scriptTabs, [sid]: [...tabs, tab] } };
  }),
  closeScriptTab: (sid, terminalId) => set((s) => ({
    scriptTabs: { ...s.scriptTabs,
      [sid]: (s.scriptTabs[sid] ?? []).filter((t) => t.terminalId !== terminalId) } })),
}));
```

- [ ] **Step 5: `WsClient.onClose` y `subscribeTerminal` con unsubscribe**

En `ui/src/transport/ws.ts`: agregar `private closeListeners: (() => void)[] = [];`, y en el constructor reemplazar la asignación de `this.ws.onclose` dentro del Promise por:

```ts
      this.ws.onclose = () => {
        reject(new Error("WebSocket cerrado antes de abrir"));   // no-op si ya abrió
        this.closeListeners.forEach((cb) => cb());
      };
```

y el método:

```ts
  onClose(cb: () => void) { this.closeListeners.push(cb); }
```

En `ui/src/transport/terminalChannel.ts`, `subscribeTerminal` devuelve el desuscriptor:

```ts
export function subscribeTerminal(ws: WsClient, id: string,
  onData: (bytes: Uint8Array) => void, onExit: () => void): () => void {
  const dataCb = (p: any) => {
    const bin = atob(p.data);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    onData(bytes);
  };
  const exitCb = () => onExit();
  ws.on(`terminal.data.${id}`, dataCb);
  ws.on(`terminal.exit.${id}`, exitCb);
  return () => { ws.off(`terminal.data.${id}`, dataCb); ws.off(`terminal.exit.${id}`, exitCb); };
}
```

En `ui/src/main/TerminalTab.tsx`, usar el desuscriptor en el cleanup:

```ts
    const unsubscribe = subscribeTerminal(getWs(), id,
      (bytes) => term.write(bytes),
      () => term.write("\r\n[proceso terminado]\r\n"));
    term.onData((d) => writeTerminal(getWs(), id, d));
    return () => { unsubscribe(); term.dispose(); };
```

- [ ] **Step 6: Run tests**

Run: `cd ui && npm test`
Expected: PASS (si `terminalChannel.test.ts` espera que `subscribeTerminal` devuelva `undefined`, actualizar ese assert a `typeof === "function"`).

- [ ] **Step 7: Commit**

```bash
git add ui/src/transport/folderSessions.ts ui/src/state/folders.ts ui/src/transport/ws.ts ui/src/transport/terminalChannel.ts ui/src/main/TerminalTab.tsx ui/src/transport/*.test.ts ui/src/state/folders.test.ts
git commit -m "feat(ui): transporte y store de sesiones-carpeta + detección de desconexión

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Componente `Queue` (AI Elements) + registro de agrupadores

**Files:**
- Create: `ui/src/components/ai-elements/queue.tsx`
- Create: `ui/src/modules/sessions/groupers.ts`
- Test: `ui/src/modules/sessions/groupers.test.ts`, `ui/src/components/ai-elements/queue.test.tsx`

**Interfaces:**
- Produces (queue): `Queue`, `QueueSection({defaultOpen=true})`, `QueueSectionTrigger`, `QueueSectionLabel({label, count?, icon?})`, `QueueSectionContent`, `QueueList`, `QueueItem`, `QueueItemIndicator({completed?})`, `QueueItemContent({completed?})`, `QueueItemDescription({completed?})`, `QueueItemActions`, `QueueItemAction` — **misma API que AI Elements**, portado a mano porque el proyecto usa Tailwind 3 (el registry de AI Elements genera clases de Tailwind 4). Se documenta como desvío menor del spec ("vía registro shadcn").
- Produces (groupers): `interface Section {id; label; defaultOpen}`, `interface Grouper {id; label; sections: Section[]; sectionOf(s: FolderSession): string}`, `registerGrouper(g)`, `getGroupers()`, `getGrouper(id)` (fallback a `none`), `groupSessions(sessions, grouper) -> {section: Section; items: FolderSession[]}[]` (omite secciones vacías). Built-ins: `none` ("Sin agrupar"), `status` ("Por estado").

- [ ] **Step 1: Write the failing tests**

```ts
// ui/src/modules/sessions/groupers.test.ts
import { describe, it, expect } from "vitest";
import { getGrouper, groupSessions, getGroupers, registerGrouper } from "./groupers";
import type { FolderSession } from "../../transport/folderSessions";

const s = (id: string, status: string | null, process = "stopped"): FolderSession => ({
  id, kind: "ticket", path: "", created: id, permissions: "analyze", title: id, status, meta: {},
  repos: [], error: null, process: process as any, terminalId: null,
});

describe("groupers", () => {
  it("none agrupa todo en una sección", () => {
    const g = groupSessions([s("a", "ready"), s("b", null)], getGrouper("none"));
    expect(g).toHaveLength(1);
    expect(g[0].items.map((x) => x.id)).toEqual(["a", "b"]);
  });

  it("status reparte y omite vacías; Hechos cerrado por defecto", () => {
    const g = groupSessions([
      s("a", "analyzing", "running"), s("b", "blocked"), s("c", "analyzing", "queued"), s("d", "done"),
    ], getGrouper("status"));
    expect(g.map((x) => [x.section.id, x.items.map((i) => i.id)])).toEqual([
      ["active", ["a"]], ["attention", ["b"]], ["queued", ["c"]], ["done", ["d"]]]);
    expect(g[3].section.defaultOpen).toBe(false);
  });

  it("es extensible y getGrouper cae a none", () => {
    registerGrouper({ id: "x", label: "X", sections: [{ id: "all", label: "Todo", defaultOpen: true }],
      sectionOf: () => "all" });
    expect(getGroupers().map((g) => g.id)).toContain("x");
    expect(getGrouper("nope").id).toBe("none");
  });
});
```

```tsx
// ui/src/components/ai-elements/queue.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Queue, QueueSection, QueueSectionTrigger, QueueSectionLabel, QueueSectionContent,
  QueueList, QueueItem, QueueItemContent } from "./queue";

describe("Queue", () => {
  it("sección colapsable con label y contador", () => {
    render(
      <Queue>
        <QueueSection defaultOpen={false}>
          <QueueSectionTrigger><QueueSectionLabel label="Hechos" count={2} /></QueueSectionTrigger>
          <QueueSectionContent>
            <QueueList><QueueItem><QueueItemContent>T-1</QueueItemContent></QueueItem></QueueList>
          </QueueSectionContent>
        </QueueSection>
      </Queue>);
    expect(screen.getByText("Hechos")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.queryByText("T-1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Hechos/ }));
    expect(screen.getByText("T-1")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && npx vitest run src/modules/sessions/groupers.test.ts src/components/ai-elements/queue.test.tsx`
Expected: FAIL (módulos inexistentes).

- [ ] **Step 3: Implement Queue**

```tsx
// ui/src/components/ai-elements/queue.tsx
// Port de AI Elements `Queue` (https://elements.ai-sdk.dev/components/queue): misma API,
// clases adaptadas a Tailwind 3 + tokens 1a.
import * as React from "react";
import { Collapsible } from "radix-ui";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export const Queue = ({ className, ...p }: React.ComponentProps<"div">) =>
  <div className={cn("flex flex-col gap-1", className)} {...p} />;

export const QueueSection = ({ defaultOpen = true, className, ...p }:
  React.ComponentProps<typeof Collapsible.Root>) =>
  <Collapsible.Root defaultOpen={defaultOpen} className={cn("group/section", className)} {...p} />;

export const QueueSectionTrigger = ({ className, children, ...p }: React.ComponentProps<"button">) => (
  <Collapsible.Trigger asChild>
    <button type="button" className={cn(
      "flex w-full items-center gap-1 px-2.5 py-1 text-[10px] uppercase tracking-wide",
      "text-muted-foreground hover:text-foreground", className)} {...p}>
      <ChevronRight size={12} className="transition-transform group-data-[state=open]/section:rotate-90" />
      {children}
    </button>
  </Collapsible.Trigger>
);

export const QueueSectionLabel = ({ label, count, icon, className }:
  { label: string; count?: number; icon?: React.ReactNode; className?: string }) => (
  <span className={cn("flex flex-1 items-center gap-1.5", className)}>
    {icon}<span>{label}</span>
    {count !== undefined && <span className="ml-auto font-mono text-[10px] text-primary">{count}</span>}
  </span>
);

export const QueueSectionContent = (p: React.ComponentProps<typeof Collapsible.Content>) =>
  <Collapsible.Content {...p} />;

export const QueueList = ({ className, ...p }: React.ComponentProps<"ul">) =>
  <ul className={cn("flex flex-col", className)} {...p} />;

export const QueueItem = ({ className, ...p }: React.ComponentProps<"li">) =>
  <li className={cn("group/item flex flex-col", className)} {...p} />;

export const QueueItemIndicator = ({ completed = false, className, ...p }:
  React.ComponentProps<"span"> & { completed?: boolean }) =>
  <span className={cn("inline-block h-2 w-2 shrink-0 rounded-full border border-muted-foreground",
    completed && "border-primary bg-primary", className)} {...p} />;

export const QueueItemContent = ({ completed = false, className, ...p }:
  React.ComponentProps<"span"> & { completed?: boolean }) =>
  <span className={cn("truncate text-xs", completed && "line-through opacity-50", className)} {...p} />;

export const QueueItemDescription = ({ completed = false, className, ...p }:
  React.ComponentProps<"span"> & { completed?: boolean }) =>
  <span className={cn("truncate text-[11px] text-muted-foreground", completed && "opacity-50", className)} {...p} />;

export const QueueItemActions = ({ className, ...p }: React.ComponentProps<"div">) =>
  <div className={cn("ml-auto flex items-center gap-0.5 opacity-0 group-hover/item:opacity-100", className)} {...p} />;

export const QueueItemAction = ({ className, ...p }:
  Omit<React.ComponentProps<typeof Button>, "variant" | "size">) =>
  <Button variant="ghost" size="icon" className={cn("h-5 w-5", className)} {...p} />;
```

(Si `Button` no tiene `size="icon"`, usar el tamaño más chico disponible en `ui/src/components/ui/button.tsx`.)

- [ ] **Step 4: Implement groupers**

```ts
// ui/src/modules/sessions/groupers.ts
import type { FolderSession } from "../../transport/folderSessions";

export interface Section { id: string; label: string; defaultOpen: boolean; }
export interface Grouper {
  id: string; label: string; sections: Section[]; sectionOf: (s: FolderSession) => string;
}

const groupers: Grouper[] = [];
export function registerGrouper(g: Grouper) { if (!groupers.some((x) => x.id === g.id)) groupers.push(g); }
export function getGroupers(): Grouper[] { return groupers; }
export function getGrouper(id: string): Grouper { return groupers.find((g) => g.id === id) ?? groupers[0]; }

export function groupSessions(sessions: FolderSession[], g: Grouper) {
  return g.sections
    .map((section) => ({ section, items: sessions.filter((s) => g.sectionOf(s) === section.id) }))
    .filter((x) => x.items.length > 0);
}

registerGrouper({
  id: "none", label: "Sin agrupar",
  sections: [{ id: "all", label: "Sesiones", defaultOpen: true }], sectionOf: () => "all",
});

const ATTENTION = ["blocked", "questions", "ready"];
registerGrouper({
  id: "status", label: "Por estado",
  sections: [
    { id: "active", label: "En curso", defaultOpen: true },
    { id: "attention", label: "Necesitan tu atención", defaultOpen: true },
    { id: "queued", label: "En cola", defaultOpen: true },
    { id: "done", label: "Hechos", defaultOpen: false },
  ],
  sectionOf: (s) => s.process === "queued" ? "queued"
    : s.status === "done" ? "done"
    : ATTENTION.includes(s.status ?? "") ? "attention" : "active",
});
```

- [ ] **Step 5: Run tests**

Run: `cd ui && npx vitest run src/modules/sessions/groupers.test.ts src/components/ai-elements/queue.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ui/src/components/ai-elements/queue.tsx ui/src/components/ai-elements/queue.test.tsx ui/src/modules/sessions/groupers.ts ui/src/modules/sessions/groupers.test.ts
git commit -m "feat(ui): componente Queue (AI Elements, Tailwind 3) y registro de agrupadores

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Sidebar de sesiones-carpeta

**Files:**
- Create: `ui/src/modules/sessions/FolderSessionsPanel.tsx`, `ui/src/modules/sessions/SessionItem.tsx`, `ui/src/modules/sessions/RepoLine.tsx`, `ui/src/modules/sessions/GroupMenu.tsx`, `ui/src/modules/sessions/ConfirmRmDialog.tsx`
- Modify: `ui/src/App.tsx`, `ui/src/App.sessions.test.tsx`
- Delete: `ui/src/modules/sessions/{SessionsPanel,SessionNodeRow,NewSessionModal}.tsx` y sus tests (`SessionsPanel.test.tsx`, `SessionNodeRow.test.tsx`, `SessionNodeRow.rename.test.tsx`, `NewSessionModal.test.tsx`, `NewSessionModal.branches.test.tsx`)
- Test: `ui/src/modules/sessions/FolderSessionsPanel.test.tsx`

**Interfaces:**
- Consumes: Tasks 13–14.
- Produces: `FolderSessionsPanel` (sin props). Hidrata con `fetchSessions`, se suscribe a `onSessionsChanged`, marca `connected=false` en `getWs().onClose` y en fallo de fetch. Renderiza: fila **★ principal** (o botón "Principal" que hace `newSession({main:true, template:"main"})`), botón agrupar (`GroupMenu`), `[+]` (`openModal("session")`), bloque de sesiones (`kind==="ticket"`) agrupado con `Queue`, bloque **Revisiones** (`kind==="review"`, siempre aparte, con `[+ revisión]` → `openModal("review")`), banner "desconectado".
- `SessionItem({ session })`: punto de proceso (`●` running / `○` stopped / `◌` queued, con `aria-label`), id, título, badge de status, badge extra (`stale`/`merged`/`closed`, `⚠ poll`), `⚠ error` con el mensaje en `title`, expandible a `RepoLine`s; click → `setActive(id)`; acciones stop / rm (abre `ConfirmRmDialog`).
- `RepoLine({ session, repo })`: nombre, branch, `✓`/`✗ setup`, `missing` (con botón **quitar** → `rmRepo`); botón `⋯` que lista scripts del repo; cada script ejecutable → `runScript` + `addScriptTab` + `setActive`; no ejecutables se muestran deshabilitados con el aviso `chmod +x`.

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/modules/sessions/FolderSessionsPanel.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { useFolders } from "../../state/folders";

const listeners: Record<string, (p: any) => void> = {};
const closeCbs: (() => void)[] = [];
vi.mock("../../transport/wsClient", () => ({
  getWs: () => ({ on: (c: string, cb: any) => { listeners[c] = cb; }, off: () => {},
                  onClose: (cb: any) => closeCbs.push(cb) }),
}));
const tree = {
  workspaceRepos: [{ id: "repo-a", name: "repo-a", branch: "main" }],
  scripts: { "repo-a": [{ name: "run", executable: true }, { name: "test", executable: false }] },
  sessions: [
    { id: "s-main1", kind: "main", path: "", created: "1", permissions: "full", title: null, status: null,
      meta: {}, repos: [], error: null, process: "running", terminalId: "t0" },
    { id: "fin-1", kind: "ticket", path: "", created: "2", permissions: "analyze", title: "Exportar",
      status: "ready", meta: {}, error: null, process: "stopped", terminalId: null,
      repos: [{ name: "repo-a", state: "ok", branch: "fin-1", port: 8100, setup: "failed" }] },
    { id: "fin-2", kind: "ticket", path: "", created: "3", permissions: "analyze", title: "Roto",
      status: null, meta: {}, error: "TICKET.md: línea 2 inválida", process: "queued",
      terminalId: null,
      repos: [{ name: "repo-a", state: "missing", branch: null, port: null, setup: null }] },
    { id: "pr-repo-a-4", kind: "review", path: "", created: "4", permissions: "analyze",
      title: "Refactor auth", status: "reviewing", meta: { author: "@juan" }, repos: [], error: null,
      process: "stopped", terminalId: null, prState: "stale", pollError: null },
  ],
};
const fetchSessions = vi.fn().mockResolvedValue(tree);
const runScript = vi.fn().mockResolvedValue({ terminalId: "t5" });
const rmRepo = vi.fn().mockResolvedValue({ ok: true });
vi.mock("../../transport/folderSessions", async (orig) => ({
  ...(await orig<any>()), fetchSessions: (...a: any[]) => fetchSessions(...a),
  runScript: (...a: any[]) => runScript(...a), rmRepo: (...a: any[]) => rmRepo(...a),
}));

import { FolderSessionsPanel } from "./FolderSessionsPanel";

describe("FolderSessionsPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    useFolders.setState({ groupBy: "none", activeId: null, scriptTabs: {}, connected: true, modal: null });
  });

  it("principal primero, sesiones, y revisiones aparte", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    expect(screen.getByText("s-main1")).toBeInTheDocument();
    expect(screen.getByText("Revisiones")).toBeInTheDocument();
    expect(screen.getByText("Refactor auth")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByText("@juan")).toBeInTheDocument();
    expect(screen.getByLabelText("en cola")).toBeInTheDocument();
    expect(screen.getByTitle("TICKET.md: línea 2 inválida")).toBeInTheDocument();
  });

  it("agrupar por estado desde el botón y persistir", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    fireEvent.click(screen.getByLabelText("Agrupar"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Por estado" }));
    expect(screen.getByText("Necesitan tu atención")).toBeInTheDocument();
    expect(screen.getByText("En cola")).toBeInTheDocument();
    expect(localStorage.getItem("ide.groupBy")).toBe("status");
  });

  it("repo con setup fallido y menú de scripts", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    fireEvent.click(screen.getByText("Exportar"));
    expect(useFolders.getState().activeId).toBe("fin-1");
    expect(screen.getByText("✗ setup")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Scripts de repo-a"));
    expect(screen.getByRole("menuitem", { name: /test/ })).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(screen.getByRole("menuitem", { name: /run/ }));
    await waitFor(() => expect(runScript).toHaveBeenCalledWith(expect.anything(), "fin-1", "repo-a", "run"));
    expect(useFolders.getState().scriptTabs["fin-1"]).toEqual([{ terminalId: "t5", label: "repo-a:run" }]);
  });

  it("repo missing ofrece quitar", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Roto"));
    fireEvent.click(screen.getByRole("button", { name: "quitar" }));
    await waitFor(() => expect(rmRepo).toHaveBeenCalledWith(expect.anything(), "fin-2", "repo-a"));
  });

  it("evento sessions.changed actualiza y el cierre del WS muestra desconectado", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    act(() => listeners["sessions.changed"]({ ...tree, sessions: tree.sessions.slice(0, 1) }));
    expect(screen.queryByText("Exportar")).not.toBeInTheDocument();
    act(() => closeCbs.forEach((cb) => cb()));
    expect(screen.getByText(/desconectado/i)).toBeInTheDocument();
  });
});
```

Reemplazar `ui/src/App.sessions.test.tsx` por:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("./transport/wsClient", () => ({
  getWs: () => ({ on: () => {}, off: () => {}, onClose: () => {},
                  request: () => Promise.resolve({ modules: ["sessions", "terminal"] }) }),
}));
vi.mock("./transport/folderSessions", async (orig) => ({
  ...(await orig<any>()),
  fetchSessions: vi.fn().mockResolvedValue({ workspaceRepos: [], scripts: {}, sessions: [
    { id: "fin-9", kind: "ticket", path: "", created: "1", permissions: "analyze", title: "MiTicket",
      status: "analyzing", meta: {}, repos: [], error: null, process: "stopped", terminalId: null }] }),
}));

import App from "./App";

describe("App con sesiones-carpeta", () => {
  it("monta el sidebar nuevo", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("MiTicket")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && npx vitest run src/modules/sessions/FolderSessionsPanel.test.tsx src/App.sessions.test.tsx`
Expected: FAIL (`FolderSessionsPanel` no existe).

- [ ] **Step 3: Implement `GroupMenu` y `ConfirmRmDialog`**

```tsx
// ui/src/modules/sessions/GroupMenu.tsx
import { useState } from "react";
import { Layers } from "lucide-react";
import { getGroupers } from "./groupers";
import { useFolders } from "../../state/folders";
import { cn } from "../../lib/utils";

export function GroupMenu() {
  const { groupBy, setGroupBy } = useFolders();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button aria-label="Agrupar" onClick={() => setOpen((o) => !o)}
        className={cn("grid h-5 w-5 place-items-center rounded text-muted-foreground hover:text-foreground",
          groupBy !== "none" && "text-primary")}>
        <Layers size={13} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-10 mt-1 w-36 rounded-md border border-border bg-popover p-1 shadow">
          {getGroupers().map((g) => (
            <button key={g.id} role="menuitem" onClick={() => { setGroupBy(g.id); setOpen(false); }}
              className={cn("block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent",
                g.id === groupBy && "text-primary")}>
              {g.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
```

```tsx
// ui/src/modules/sessions/ConfirmRmDialog.tsx
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { rmSession } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";

export function ConfirmRmDialog({ id, open, onClose }: { id: string; open: boolean; onClose: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [needsForce, setNeedsForce] = useState(false);
  const run = async (force: boolean) => {
    try { await rmSession(getWs(), id, force); onClose(); }
    catch (e: any) {
      setError(e?.message ?? String(e));
      setNeedsForce(e?.code === "uncommitted_changes");
    }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Borrar sesión {id}</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">
          Para el proceso, corre <code>archive</code> de cada repo, quita los worktrees y borra la carpeta.
          Las branches se conservan.
        </p>
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          {needsForce
            ? <Button variant="destructive" onClick={() => run(true)}>Borrar igual (--force)</Button>
            : <Button variant="destructive" onClick={() => run(false)}>Borrar</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Implement `RepoLine` y `SessionItem`**

```tsx
// ui/src/modules/sessions/RepoLine.tsx
import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import type { FolderSession, RepoInfo } from "../../transport/folderSessions";
import { rmRepo, runScript } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { cn } from "../../lib/utils";

export function RepoLine({ session, repo }: { session: FolderSession; repo: RepoInfo }) {
  const { tree, addScriptTab, setActive } = useFolders();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scripts = tree.scripts[repo.name] ?? [];
  const launch = async (name: string) => {
    setOpen(false);
    try {
      const { terminalId } = await runScript(getWs(), session.id, repo.name, name);
      addScriptTab(session.id, { terminalId, label: `${repo.name}:${name}` });
      setActive(session.id);
    } catch (e: any) { setError(e?.message ?? String(e)); }
  };
  return (
    <div className="relative flex items-center gap-1.5 py-0.5 pl-7 pr-2 text-[11px]">
      <span className={cn(repo.state === "missing" && "text-destructive line-through")}>{repo.name}</span>
      <span className="font-mono text-primary">{repo.branch ?? "(detached)"}</span>
      {repo.state === "missing" && <span className="text-destructive">missing</span>}
      {repo.state === "missing" && (
        <button onClick={() => rmRepo(getWs(), session.id, repo.name).catch((e: any) => setError(e?.message ?? String(e)))}
          className="text-[10px] underline text-muted-foreground hover:text-foreground">quitar</button>)}
      {repo.setup === "ok" && <span className="text-muted-foreground">✓ setup</span>}
      {repo.setup === "failed" && <span className="text-destructive">✗ setup</span>}
      {error && <span role="alert" title={error} className="text-destructive">⚠</span>}
      <button aria-label={`Scripts de ${repo.name}`} onClick={() => setOpen((o) => !o)}
        className="ml-auto text-muted-foreground hover:text-foreground"><MoreHorizontal size={12} /></button>
      {open && (
        <div role="menu" className="absolute right-2 top-5 z-10 w-44 rounded-md border border-border bg-popover p-1 shadow">
          {scripts.length === 0 && <div className="px-2 py-1 text-muted-foreground">sin scripts en .ide/scripts/{repo.name}/</div>}
          {scripts.map((s) => (
            <button key={s.name} role="menuitem" aria-disabled={!s.executable}
              title={s.executable ? undefined : `chmod +x .ide/scripts/${repo.name}/${s.name}`}
              onClick={() => s.executable && launch(s.name)}
              className={cn("block w-full rounded px-2 py-1 text-left hover:bg-accent",
                !s.executable && "cursor-not-allowed text-muted-foreground")}>
              {s.name}{!s.executable && " ⚠ no ejecutable"}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
```

```tsx
// ui/src/modules/sessions/SessionItem.tsx
import { useState } from "react";
import { Square, Trash2 } from "lucide-react";
import type { FolderSession } from "../../transport/folderSessions";
import { stopSession } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
import { RepoLine } from "./RepoLine";
import { ConfirmRmDialog } from "./ConfirmRmDialog";
import { cn } from "../../lib/utils";

const DOT = { running: ["●", "corriendo"], stopped: ["○", "parada"], queued: ["◌", "en cola"] } as const;

export function SessionItem({ session }: { session: FolderSession }) {
  const { activeId, setActive } = useFolders();
  const [confirm, setConfirm] = useState(false);
  const [dot, label] = DOT[session.process];
  const extra = session.pollError ? "⚠ poll" : session.prState;
  return (
    <QueueItem>
      <div onClick={() => setActive(session.id)}
        className={cn("flex cursor-pointer items-center gap-1.5 px-2.5 py-1 text-xs hover:bg-accent",
          activeId === session.id && "bg-accent")}>
        <span aria-label={label} className={cn(session.process === "running" ? "text-primary" : "text-muted-foreground")}>{dot}</span>
        <span className="font-mono text-[11px]">{session.id}</span>
        <span className="truncate text-muted-foreground">{session.title}</span>
        {session.meta.author && <span className="text-[10px] text-muted-foreground">{session.meta.author}</span>}
        {session.status && <Badge variant="outline">{session.status}</Badge>}
        {extra && <Badge variant={session.pollError ? "destructive" : "secondary"}
          title={session.pollError ?? undefined}>{extra}</Badge>}
        {(session.error || session.launchError) && (
          <span title={session.error ?? session.launchError ?? ""} className="text-destructive">⚠ error</span>)}
        <QueueItemActions>
          {session.process !== "stopped" && (
            <QueueItemAction aria-label={`Parar ${session.id}`}
              onClick={(e) => { e.stopPropagation(); stopSession(getWs(), session.id); }}>
              <Square size={11} />
            </QueueItemAction>)}
          <QueueItemAction aria-label={`Borrar ${session.id}`}
            onClick={(e) => { e.stopPropagation(); setConfirm(true); }}>
            <Trash2 size={11} />
          </QueueItemAction>
        </QueueItemActions>
      </div>
      {session.repos.map((r) => <RepoLine key={r.name} session={session} repo={r} />)}
      <ConfirmRmDialog id={session.id} open={confirm} onClose={() => setConfirm(false)} />
    </QueueItem>
  );
}
```

(Simplificación respecto del spec: los repos se muestran siempre debajo de la sesión, sin toggle de expandir; si el sidebar se satura, agregar el toggle es local a `SessionItem`.)

- [ ] **Step 5: Implement `FolderSessionsPanel` y montarlo**

```tsx
// ui/src/modules/sessions/FolderSessionsPanel.tsx
import { useEffect } from "react";
import { Plus, Star } from "lucide-react";
import { useFolders } from "../../state/folders";
import { fetchSessions, newSession, onSessionsChanged } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { getGrouper, groupSessions } from "./groupers";
import { GroupMenu } from "./GroupMenu";
import { SessionItem } from "./SessionItem";
import { CustomizationsFooter } from "../settings/CustomizationsFooter";
import { Queue, QueueSection, QueueSectionTrigger, QueueSectionLabel, QueueSectionContent, QueueList }
  from "../../components/ai-elements/queue";

export function FolderSessionsPanel() {
  const { tree, connected, groupBy, setTree, setConnected, setActive, openModal } = useFolders();

  useEffect(() => {
    const ws = getWs();
    fetchSessions(ws).then(setTree).catch(() => setConnected(false));
    const off = onSessionsChanged(ws, setTree);
    ws.onClose(() => setConnected(false));
    return off;
  }, [setTree, setConnected]);

  const main = tree.sessions.find((s) => s.kind === "main");
  const tickets = tree.sessions.filter((s) => s.kind !== "main" && s.kind !== "review");
  const reviews = tree.sessions.filter((s) => s.kind === "review");
  const groups = groupSessions(tickets, getGrouper(groupBy));

  return (
    <aside className="flex w-[300px] flex-col overflow-auto border-r border-border bg-card">
      {!connected && (
        <div role="status" className="bg-destructive/15 px-2.5 py-1 text-[11px] text-destructive">
          desconectado del server: lo de abajo puede estar desactualizado
        </div>
      )}
      <div className={connected ? "" : "opacity-50"}>
        <div className="flex items-center gap-1.5 px-2.5 pb-1 pt-2.5">
          {main ? (
            <button onClick={() => setActive(main.id)} className="flex items-center gap-1.5 text-xs">
              <Star size={12} className="text-primary" /><span className="font-mono">{main.id}</span>
              <span className="text-muted-foreground">{main.process}</span>
            </button>
          ) : (
            <button onClick={() => newSession(getWs(), { main: true, template: "main" })
                .then((r: any) => setActive(r.session.id))}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
              <Star size={12} /> Principal
            </button>
          )}
          <div className="ml-auto flex items-center gap-1">
            <GroupMenu />
            <button aria-label="Nueva sesión" onClick={() => openModal("session")}
              className="text-muted-foreground hover:text-foreground"><Plus size={13} /></button>
          </div>
        </div>

        <Queue>
          {groups.map(({ section, items }) => (
            <QueueSection key={`${groupBy}-${section.id}`} defaultOpen={section.defaultOpen}>
              <QueueSectionTrigger><QueueSectionLabel label={section.label} count={items.length} /></QueueSectionTrigger>
              <QueueSectionContent>
                <QueueList>{items.map((s) => <SessionItem key={s.id} session={s} />)}</QueueList>
              </QueueSectionContent>
            </QueueSection>
          ))}
        </Queue>

        <div className="mx-2.5 mt-3 flex items-center justify-between border-t border-border pt-2 text-[10px] uppercase tracking-wide text-muted-foreground">
          <span>Revisiones</span>
          <button aria-label="Nueva revisión" onClick={() => openModal("review")}
            className="hover:text-foreground"><Plus size={12} /></button>
        </div>
        <QueueList>{reviews.map((s) => <SessionItem key={s.id} session={s} />)}</QueueList>
      </div>
      <div className="mt-auto"><CustomizationsFooter /></div>
    </aside>
  );
}
```

En `ui/src/App.tsx`: reemplazar los imports de `SessionsPanel` y `NewSessionModal` por `FolderSessionsPanel` (y `NewFolderSessionModal` llega en Task 16; por ahora no se monta modal), y `<SessionsPanel />` por `<FolderSessionsPanel />`, quitando `<NewSessionModal />`.

Borrar los archivos viejos listados en **Files → Delete**.

- [ ] **Step 6: Run tests**

Run: `cd ui && npm test`
Expected: PASS (los tests borrados ya no corren; si algún otro test importa `SessionsPanel`/`NewSessionModal`, apuntarlo al panel nuevo o borrar el assert obsoleto).

- [ ] **Step 7: Commit**

```bash
git add -A ui/src
git commit -m "feat(ui): sidebar de sesiones-carpeta (principal, agrupar por estado, revisiones, scripts)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: Modales de nueva sesión y nueva revisión

**Files:**
- Create: `ui/src/modules/sessions/NewFolderSessionModal.tsx`
- Modify: `ui/src/App.tsx` (montarlo)
- Test: `ui/src/modules/sessions/NewFolderSessionModal.test.tsx`

**Interfaces:**
- Consumes: `useFolders.modal`, `newSession`.
- Produces: `NewFolderSessionModal` — con `modal === "session"`: campos id (opcional), plantilla (`ticket` | `Sin plantilla`), título, notion_url, cuerpo/prompt (textarea), permisos (`Default del workspace` | analyze | full | default). Con plantilla `ticket` manda `{id?, template:"ticket", title, vars:{title, notion_url, body}, permissions?}`; sin plantilla manda `{id?, title?, prompt, permissions?}`. Con `modal === "review"`: campo URL → `{review: url}`. Error del server se muestra inline (`role="alert"`) y el modal queda abierto; éxito → `setActive(id)` + `closeModal()`.

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/modules/sessions/NewFolderSessionModal.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useFolders } from "../../state/folders";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const newSession = vi.fn();
vi.mock("../../transport/folderSessions", async (orig) => ({
  ...(await orig<any>()), newSession: (...a: any[]) => newSession(...a),
}));

import { NewFolderSessionModal } from "./NewFolderSessionModal";

describe("NewFolderSessionModal", () => {
  beforeEach(() => { newSession.mockReset(); useFolders.setState({ modal: null, activeId: null }); });

  it("crea ticket con plantilla y activa la sesión", async () => {
    newSession.mockResolvedValue({ session: { id: "fin-1" }, process: "running" });
    useFolders.setState({ modal: "session" });
    render(<NewFolderSessionModal />);
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "FIN-1" } });
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Exportar" } });
    fireEvent.change(screen.getByLabelText("URL de Notion"), { target: { value: "https://n" } });
    fireEvent.change(screen.getByLabelText("Detalle"), { target: { value: "cuerpo" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    await waitFor(() => expect(useFolders.getState().activeId).toBe("fin-1"));
    expect(newSession.mock.calls[0][1]).toEqual({ id: "FIN-1", template: "ticket", title: "Exportar",
      vars: { title: "Exportar", notion_url: "https://n", body: "cuerpo" } });
    expect(useFolders.getState().modal).toBe(null);
  });

  it("muestra el error del server y no cierra", async () => {
    newSession.mockRejectedValue({ code: "session_exists", message: "ya existe la sesión fin-1" });
    useFolders.setState({ modal: "session" });
    render(<NewFolderSessionModal />);
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ya existe");
    expect(useFolders.getState().modal).toBe("session");
  });

  it("revisión por URL", async () => {
    newSession.mockResolvedValue({ session: { id: "pr-repo-a-4" }, process: "running" });
    useFolders.setState({ modal: "review" });
    render(<NewFolderSessionModal />);
    fireEvent.change(screen.getByLabelText("URL del PR"),
      { target: { value: "https://github.com/acme/repo-a/pull/4" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    await waitFor(() => expect(newSession.mock.calls[0][1]).toEqual(
      { review: "https://github.com/acme/repo-a/pull/4" }));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/modules/sessions/NewFolderSessionModal.test.tsx`
Expected: FAIL (módulo inexistente).

- [ ] **Step 3: Implement**

```tsx
// ui/src/modules/sessions/NewFolderSessionModal.tsx
import { useState } from "react";
import { useFolders } from "../../state/folders";
import { newSession, type NewSessionReq } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Button } from "../../components/ui/button";

const field = "flex flex-col gap-1";
const area = "min-h-[80px] rounded-md border border-border bg-background p-2 text-xs";
const select = "h-8 rounded-md border border-border bg-background px-2 text-xs";

export function NewFolderSessionModal() {
  const { modal, closeModal, setActive } = useFolders();
  const [id, setId] = useState(""); const [title, setTitle] = useState("");
  const [notionUrl, setNotionUrl] = useState(""); const [body, setBody] = useState("");
  const [template, setTemplate] = useState<"ticket" | "none">("ticket");
  const [permissions, setPermissions] = useState<"" | "analyze" | "full" | "default">("");
  const [prUrl, setPrUrl] = useState(""); const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const payload = (): NewSessionReq => {
    if (modal === "review") return { review: prUrl.trim() };
    const base: NewSessionReq = {};
    if (id.trim()) base.id = id.trim();
    if (template === "ticket") {
      Object.assign(base, { template: "ticket", title,
        vars: { title, notion_url: notionUrl, body } });
    } else {
      if (title) base.title = title;
      base.prompt = body;
    }
    if (permissions) base.permissions = permissions;
    return base;
  };

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const res: any = await newSession(getWs(), payload());
      setActive(res.session.id);
      closeModal();
    } catch (e: any) { setError(e?.message ?? String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={modal !== null} onOpenChange={(o) => !o && closeModal()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{modal === "review" ? "Nueva revisión de PR" : "Nueva sesión"}</DialogTitle></DialogHeader>
        {modal === "review" ? (
          <div className={field}><Label htmlFor="pr">URL del PR</Label>
            <Input id="pr" value={prUrl} onChange={(e) => setPrUrl(e.target.value)} /></div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className={field}><Label htmlFor="sid">Id</Label>
              <Input id="sid" placeholder="vacío = al azar" value={id} onChange={(e) => setId(e.target.value)} /></div>
            <div className={field}><Label htmlFor="tpl">Plantilla</Label>
              <select id="tpl" className={select} value={template}
                onChange={(e) => setTemplate(e.target.value as any)}>
                <option value="ticket">ticket</option><option value="none">Sin plantilla</option>
              </select></div>
            <div className={field}><Label htmlFor="title">Título</Label>
              <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
            {template === "ticket" && (
              <div className={field}><Label htmlFor="nurl">URL de Notion</Label>
                <Input id="nurl" value={notionUrl} onChange={(e) => setNotionUrl(e.target.value)} /></div>)}
            <div className={field}><Label htmlFor="body">{template === "ticket" ? "Detalle" : "Prompt"}</Label>
              <textarea id="body" className={area} value={body} onChange={(e) => setBody(e.target.value)} /></div>
            <div className={field}><Label htmlFor="perm">Permisos</Label>
              <select id="perm" className={select} value={permissions}
                onChange={(e) => setPermissions(e.target.value as any)}>
                <option value="">Default del workspace</option>
                <option value="analyze">analyze</option><option value="full">full</option>
                <option value="default">default</option>
              </select></div>
          </div>
        )}
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={closeModal}>Cancelar</Button>
          <Button onClick={submit} disabled={busy}>Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

En `ui/src/App.tsx`: importar y montar `<NewFolderSessionModal />` donde estaba `<NewSessionModal />`.

- [ ] **Step 4: Run tests**

Run: `cd ui && npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src/modules/sessions/NewFolderSessionModal.tsx ui/src/modules/sessions/NewFolderSessionModal.test.tsx ui/src/App.tsx
git commit -m "feat(ui): modales de nueva sesión (plantilla ticket) y nueva revisión de PR

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: Vista principal por sesión + rail filtrado por `[ui] modules`

**Files:**
- Create: `ui/src/main/SessionView.tsx`
- Modify: `ui/src/layout/MainPanel.tsx`, `ui/src/layout/ActivityRail.tsx`, `ui/src/layout/ContextPanel.tsx`, `ui/src/App.tsx`
- Test: `ui/src/main/SessionView.test.tsx`, `ui/src/layout/rail.modules.test.tsx`

**Interfaces:**
- Consumes: Tasks 13–16, `TerminalTab`.
- Produces: `SessionView` — para `activeId`: tabs `claude` | `TICKET.md`/`REVIEW.md` (no en `main`) | un tab por `scriptTabs[activeId]` (cerrable). Tab `claude`: si `terminalId` → `TerminalTab`; si `queued` → "En cola (max_running)…"; si no → botón **Abrir** (`openSession`) y `launchError` si hay. Tab doc: `fetchDoc` al montar y en cada `sessions.changed` → `<pre>`. Revisión `stale`: banner "El PR tiene commits nuevos" + **Refrescar** (`refreshReview`). **Las terminales visitadas quedan montadas** (ocultas con `hidden`) para no perder salida. Sin sesión activa: texto guía.
- `MainPanel`: si `uiModules` no incluye `"chat"` → `<SessionView />`; si incluye → comportamiento actual.
- `ActivityRail`: filtra `getModules()` por `uiModules` (null = todos). `ContextPanel`: no se renderiza si no hay módulos visibles. `App` carga `fetchUiConfig` al montar (error → `setUiModules(["sessions","terminal"])` no; mantener `null` y mostrar todo es peor: **en error se marca desconectado** con `setConnected(false)`).

- [ ] **Step 1: Write the failing tests**

```tsx
// ui/src/main/SessionView.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useFolders } from "../state/folders";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({ on: () => {}, off: () => {} }) }));
const openSession = vi.fn().mockResolvedValue({ process: "running" });
const refreshReview = vi.fn().mockResolvedValue({});
vi.mock("../transport/folderSessions", async (orig) => ({
  ...(await orig<any>()),
  openSession: (...a: any[]) => openSession(...a),
  refreshReview: (...a: any[]) => refreshReview(...a),
  fetchDoc: vi.fn().mockResolvedValue({ name: "TICKET.md", text: "---\nstatus: ready\n---\n## Scope\nX" }),
}));
vi.mock("./TerminalTab", () => ({ TerminalTab: ({ id }: { id: string }) => <div data-testid={`term-${id}`} /> }));

import { SessionView } from "./SessionView";

const base = { path: "", created: "1", permissions: "analyze", meta: {}, repos: [], error: null };
const sessions: any[] = [
  { ...base, id: "a", kind: "ticket", title: "A", status: "ready", process: "running", terminalId: "t1" },
  { ...base, id: "b", kind: "ticket", title: "B", status: null, process: "stopped", terminalId: null,
    launchError: "no se encontró `claude`" },
  { ...base, id: "r", kind: "review", title: "R", status: "reviewing", process: "stopped",
    terminalId: null, prState: "stale" },
];

describe("SessionView", () => {
  beforeEach(() => useFolders.setState({
    tree: { sessions, workspaceRepos: [], scripts: {} }, activeId: "a", scriptTabs: {} }));

  it("terminal claude + doc", async () => {
    render(<SessionView />);
    expect(screen.getByTestId("term-t1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "TICKET.md" }));
    expect(await screen.findByText(/## Scope/)).toBeInTheDocument();
  });

  it("las terminales visitadas quedan montadas al cambiar de sesión", () => {   // Review Focus 4
    const { rerender } = render(<SessionView />);
    useFolders.setState({ activeId: "b" }); rerender(<SessionView />);
    expect(screen.getByTestId("term-t1")).toBeInTheDocument();
    expect(screen.getByTestId("term-t1").closest("[hidden]")).not.toBeNull();
  });

  it("parada: botón Abrir y launchError", async () => {
    useFolders.setState({ activeId: "b" });
    render(<SessionView />);
    expect(screen.getByText(/no se encontró/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    await waitFor(() => expect(openSession).toHaveBeenCalledWith(expect.anything(), "b"));
  });

  it("revisión stale ofrece refrescar", async () => {
    useFolders.setState({ activeId: "r" });
    render(<SessionView />);
    fireEvent.click(screen.getByRole("button", { name: "Refrescar" }));
    await waitFor(() => expect(refreshReview).toHaveBeenCalledWith(expect.anything(), "r"));
  });

  it("tabs de scripts", () => {
    useFolders.setState({ scriptTabs: { a: [{ terminalId: "t7", label: "repo-a:run" }] } });
    render(<SessionView />);
    fireEvent.click(screen.getByRole("tab", { name: "repo-a:run" }));
    expect(screen.getByTestId("term-t7")).toBeInTheDocument();
  });
});
```

```tsx
// ui/src/layout/rail.modules.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SquareTerminal, Search } from "lucide-react";
import { registerModule } from "../modules/registry";
import { useFolders } from "../state/folders";
import { ActivityRail } from "./ActivityRail";

registerModule({ id: "terminal", title: "Terminal", icon: SquareTerminal, Panel: () => null });
registerModule({ id: "search", title: "Buscar", icon: Search, Panel: () => null });

describe("ActivityRail filtrado", () => {
  it("muestra solo los módulos de [ui] modules", () => {
    useFolders.setState({ uiModules: ["sessions", "terminal"] });
    render(<ActivityRail />);
    expect(screen.getByLabelText("Terminal")).toBeInTheDocument();
    expect(screen.queryByLabelText("Buscar")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && npx vitest run src/main/SessionView.test.tsx src/layout/rail.modules.test.tsx`
Expected: FAIL (`SessionView` no existe; el rail muestra "Buscar").

- [ ] **Step 3: Implement `SessionView`**

```tsx
// ui/src/main/SessionView.tsx
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useFolders } from "../state/folders";
import { fetchDoc, onSessionsChanged, openSession, refreshReview } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { TerminalTab } from "./TerminalTab";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

type TabKey = "claude" | "doc" | string;      // string = terminalId de un script

function DocTab({ id }: { id: string }) {
  const [text, setText] = useState(""); const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const load = () => fetchDoc(getWs(), id).then((d) => setText(d.text)).catch((e) => setError(e?.message ?? String(e)));
    load();
    return onSessionsChanged(getWs(), load);
  }, [id]);
  if (error) return <p role="alert" className="p-4 text-xs text-destructive">{error}</p>;
  return <pre className="h-full overflow-auto whitespace-pre-wrap p-4 font-mono text-xs">{text}</pre>;
}

export function SessionView() {
  const { tree, activeId, scriptTabs, closeScriptTab } = useFolders();
  const [tab, setTab] = useState<TabKey>("claude");
  const [mounted, setMounted] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const session = tree.sessions.find((s) => s.id === activeId);
  const scripts = activeId ? scriptTabs[activeId] ?? [] : [];

  useEffect(() => { setTab("claude"); setError(null); }, [activeId]);
  const visibleTerm = tab === "claude" ? session?.terminalId ?? null
    : tab === "doc" ? null : tab;
  useEffect(() => {
    if (visibleTerm && !mounted.includes(visibleTerm)) setMounted((m) => [...m, visibleTerm]);
  }, [visibleTerm, mounted]);

  if (!session) {
    return <div className="p-6 text-sm text-muted-foreground">Elige una sesión del sidebar (o crea la principal con ★).</div>;
  }
  const docName = session.kind === "review" ? "REVIEW.md" : session.kind === "ticket" ? "TICKET.md" : null;
  const tabCls = (active: boolean) => cn("flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-xs",
    active ? "border-primary text-foreground" : "border-transparent text-muted-foreground");
  const act = (p: Promise<unknown>) => p.catch((e: any) => setError(e?.message ?? String(e)));

  return (
    <div className="flex h-full flex-col">
      <div role="tablist" className="flex border-b border-border bg-title-bg">
        <button role="tab" aria-selected={tab === "claude"} className={tabCls(tab === "claude")} onClick={() => setTab("claude")}>claude</button>
        {docName && <button role="tab" aria-selected={tab === "doc"} className={tabCls(tab === "doc")} onClick={() => setTab("doc")}>{docName}</button>}
        {scripts.map((s) => (
          <span key={s.terminalId} className={tabCls(tab === s.terminalId)}>
            <button role="tab" aria-selected={tab === s.terminalId} onClick={() => setTab(s.terminalId)}>{s.label}</button>
            <button aria-label={`cerrar ${s.label}`} onClick={() => { closeScriptTab(session.id, s.terminalId); setTab("claude"); }}><X size={11} /></button>
          </span>
        ))}
      </div>
      {session.prState === "stale" && (
        <div className="flex items-center gap-2 bg-accent px-3 py-1 text-xs">
          El PR tiene commits nuevos desde tu revisión.
          <Button size="sm" onClick={() => act(refreshReview(getWs(), session.id))}>Refrescar</Button>
        </div>
      )}
      {error && <p role="alert" className="px-3 py-1 text-xs text-destructive">{error}</p>}
      <div className="relative min-h-0 flex-1">
        {mounted.map((tid) => (
          <div key={tid} hidden={tid !== visibleTerm} className="h-full"><TerminalTab id={tid} /></div>
        ))}
        {tab === "claude" && !session.terminalId && (
          <div className="flex flex-col items-start gap-2 p-6 text-sm">
            {session.process === "queued" ? <span className="text-muted-foreground">En cola (max_running)…</span> : (
              <>
                {session.launchError && <p role="alert" className="text-xs text-destructive">{session.launchError}</p>}
                <Button onClick={() => act(openSession(getWs(), session.id))}>Abrir</Button>
              </>
            )}
          </div>
        )}
        {tab === "doc" && <DocTab id={session.id} />}
      </div>
    </div>
  );
}
```

Nota: en el test "quedan montadas", al pasar a `b` (sin terminal) el div de `t1` sigue en `mounted` con `hidden`.

- [ ] **Step 4: MainPanel, ActivityRail, ContextPanel, App**

`ui/src/layout/MainPanel.tsx` — al principio de `MainPanel`:

```tsx
  const uiModules = useFolders((s) => s.uiModules);
  if (uiModules && !uiModules.includes("chat")) {
    return <main className="flex flex-1 flex-col bg-background"><SessionView /></main>;
  }
```
(importar `useFolders` de `../state/folders` y `SessionView` de `../main/SessionView`).

`ui/src/layout/ActivityRail.tsx` — reemplazar `getModules().map(` por `visibleModules().map(` y agregar en el archivo:

```tsx
import { useFolders } from "../state/folders";
...
  const uiModules = useFolders((s) => s.uiModules);
  const visibleModules = () => getModules().filter((m) => !uiModules || uiModules.includes(m.id));
```

`ui/src/layout/ContextPanel.tsx` — antes del `return`:

```tsx
  const uiModules = useFolders((s) => s.uiModules);
  const visible = getModules().filter((m) => !uiModules || uiModules.includes(m.id));
  if (visible.length === 0) return null;
  const mod = visible.find((m) => m.id === activePanel) ?? visible[0];
```
(y usar ese `mod`; quitar la línea `const mod = getModules().find(...)` original).

`ui/src/App.tsx` — cargar la config de UI al montar:

```tsx
import { useEffect } from "react";
import { useFolders } from "./state/folders";
import { fetchUiConfig } from "./transport/folderSessions";
import { getWs } from "./transport/wsClient";
...
export default function App() {
  const { setUiModules, setConnected } = useFolders();
  useEffect(() => {
    fetchUiConfig(getWs()).then((c) => setUiModules(c.modules)).catch(() => setConnected(false));
  }, [setUiModules, setConnected]);
  ...
```

- [ ] **Step 5: Run tests**

Run: `cd ui && npm test`
Expected: PASS. Tests de layout existentes que asumen todos los módulos visibles: `uiModules` arranca en `null` (= todos), así que no cambian.

- [ ] **Step 6: Commit**

```bash
git add ui/src
git commit -m "feat(ui): vista por sesión (claude/doc/scripts) y rail filtrado por [ui] modules

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 18: Verificación end-to-end + docs

**Files:**
- Modify: `CLAUDE.md` (sección "Estado actual" y "Decisiones": el modelo de sesión ahora es sesiones-carpeta)
- Modify: `docs/design/ROADMAP.md` (fila nueva "Sesiones-carpeta" ✅)
- Modify: `docs/superpowers/HANDOFF.md` (verificar que no quede en 0 bytes tras editar: `wc -c`)
- Modify: `README.md` (requisito `gh` para revisiones)

- [ ] **Step 1: Suites completas**

Run: `cd server && uv run pytest -q && cd ../ui && npm test && npm run build`
Expected: todo verde y build OK (tsc sin errores).

- [ ] **Step 2: Prueba manual en un workspace real** (usar `superpowers:verification-before-completion`)

```bash
cd server && uv run ide build && cd ..
W=$(mktemp -d) && git clone -q . $W/ide-copy && cd $W && uv run --project /Users/topc/dev/ide/server ide init
mkdir -p .ide/scripts/ide-copy && printf '#!/bin/sh\necho setup en $PWD puerto $IDE_PORT\n' > .ide/scripts/ide-copy/setup && chmod +x .ide/scripts/ide-copy/setup
uv run --project /Users/topc/dev/ide/server ide run --cwd $W
```

Checklist (anotar ✅/❌ en el commit):
1. Sidebar vacío con botón ★ Principal; rail solo con Terminal.
2. `[+]` → ticket `TEST-1` con plantilla → aparece `test-1` con `analyzing` y ● corriendo; tab `claude` muestra el TUI de Claude Code con el prompt.
3. Pedirle en esa terminal "ejecuta `ide repo add ide-copy`" → corre sin pedir permiso (perfil analyze), aparece el repo con `✓ setup`, `IDE_PORT=8100`.
4. Editar a mano `TICKET.md` → `status: blocked` → el badge cambia sin recargar. Agrupar → "Por estado" → aparece en "Necesitan tu atención".
5. `config.toml` con `max_running = 1`, crear otra sesión → `◌ en cola`; parar la primera → la segunda arranca.
6. Cambiar entre sesiones y volver → la salida del TUI sigue ahí.
7. Parar `ide run`, levantarlo de nuevo → todas `○`; click → Abrir → `claude --continue` retoma la conversación.
8. Revisión: `[+ revisión]` con un PR real de un repo del workspace → `pr-<repo>-<n>` con worktree detached; con `poll_interval = 30`, pushear un commit al PR → badge `stale` → Refrescar.
9. Matar el server con la UI abierta → banner "desconectado".
10. `ide session rm test-1` con un archivo sin commitear → se niega; `--force` → borra.

- [ ] **Step 3: Actualizar docs**

- `CLAUDE.md`: en "Decisiones de arquitectura" reemplazar el bullet de **Workspace + `.ide/`** y **Modelo de sesión** por: sesión = carpeta `.ide/sessions/<id>/` con `claude` interactivo; kinds `main/ticket/review`; repos = worktrees en `.ide/worktrees/<id>/<repo>` vía symlink; CLI `ide session|repo|script`; spec `docs/superpowers/specs/2026-10-13-sesiones-carpeta-design.md`. En "Estado actual": sesiones-carpeta hechas; módulos viejos ocultos vía `[ui] modules`.
- `ROADMAP.md`: fila `| Sesiones-carpeta | Simplificación: sesión = carpeta + claude interactivo, despacho por plantilla, scripts por repo, max_running, revisiones de PR con polling, sidebar con Queue. | ✅ hecho |`.
- `README.md`: requisitos runtime `claude` (CLI) y `gh` (revisiones de PR).
- `HANDOFF.md`: estado y próximos pasos (chat propio sobre sesiones-carpeta; re-habilitar módulos sobre `resolve_cwd` nuevo). Verificar `wc -c docs/superpowers/HANDOFF.md` > 0.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md docs/design/ROADMAP.md docs/superpowers/HANDOFF.md
git commit -m "docs: sesiones-carpeta hechas (roadmap, handoff, CLAUDE.md, requisitos)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
