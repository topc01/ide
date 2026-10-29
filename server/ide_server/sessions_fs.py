# server/ide_server/sessions_fs.py
from __future__ import annotations
import fcntl
import json
import re
import secrets
import shutil
import string
import subprocess
import threading
import tomllib
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator
import tomli_w
from ide_server import seeds
from ide_server.sessions_store import slugify
from ide_server.workspace import discover_repos

KINDS = ("main", "ticket", "review", "ide", "recursos")
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


def require_plain_name(name: str, what: str = "nombre") -> str:
    """Rechaza nombres que no sean un componente simple de path (sin '/', '.', '..')."""
    if not isinstance(name, str) or not name or name in (".", "..") or Path(name).name != name:
        raise SessionError("invalid_name", f"{what} inválido: {name!r}")
    return name


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


def sessions_dir(root: Path) -> Path:
    return root / ".ide" / "sessions"


def session_path(root: Path, sid: str) -> Path:
    return sessions_dir(root) / sid


STATE_FILE = "SESSION.md"
LEGACY_STATE = {"ticket": "TICKET.md", "review": "REVIEW.md"}


def state_file(kind: str | None) -> str | None:
    """El `.md` de la sesión (estado, análisis, feedback): SESSION.md para tickets y revisiones."""
    return STATE_FILE if kind in LEGACY_STATE else None


def repo_links(path: Path) -> list[Path]:
    """Los repos de una sesión: sus symlinks a worktrees (no los TICKET.md/REVIEW.md que quedaron
    apuntando a SESSION.md tras la migración)."""
    return sorted(p for p in path.iterdir() if p.is_symlink() and p.name not in LEGACY_STATE.values())


def migrate_state_file(path: Path, kind: str | None) -> None:
    """TICKET.md/REVIEW.md de antes → SESSION.md; el nombre viejo queda como symlink (una sesión que
    ya corría y lo lee no se rompe)."""
    old = path / LEGACY_STATE.get(kind or "", "")
    if kind in LEGACY_STATE and old.is_file() and not old.is_symlink() and not (path / STATE_FILE).exists():
        old.rename(path / STATE_FILE)
        old.symlink_to(STATE_FILE)


def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def write_toml(path: Path, data: dict) -> None:
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


_LOCK = threading.RLock()                       # threads del server
_LOCK_STATE: dict = {"depth": 0, "fh": None}      # flock: entre procesos (server + CLI)


@contextmanager
def workspace_lock(root: Path) -> Iterator[None]:
    """Lock exclusivo del workspace (`.ide/.lock`), reentrante dentro del proceso."""
    with _LOCK:
        if _LOCK_STATE["depth"] == 0:
            path = root / ".ide" / ".lock"
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(path, "a")
            fcntl.flock(fh, fcntl.LOCK_EX)
            _LOCK_STATE["fh"] = fh
        _LOCK_STATE["depth"] += 1
        try:
            yield
        finally:
            _LOCK_STATE["depth"] -= 1
            if _LOCK_STATE["depth"] == 0:
                fh, _LOCK_STATE["fh"] = _LOCK_STATE["fh"], None
                fcntl.flock(fh, fcntl.LOCK_UN)
                fh.close()


def update_session_toml(root: Path, sid: str, fn: Callable[[dict], None]) -> dict:
    path = session_path(root, sid) / ".session.toml"
    with workspace_lock(root):
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
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
    return None


def create_session_dir(root: Path, *, sid: str, kind: str, permissions: str, prompt: str,
                       meta: dict | None = None, now: datetime | None = None) -> Path:
    if kind not in KINDS:
        raise SessionError("invalid_kind", f"kind inválido: {kind!r}")
    if permissions not in PERMISSIONS:
        raise SessionError("invalid_permissions",
                           f"permisos inválidos: {permissions!r} (analyze | full | default)")
    with workspace_lock(root):
        return _create_session_dir(root, sid=sid, kind=kind, permissions=permissions,
                                   prompt=prompt, meta=meta, now=now)


def _create_session_dir(root: Path, *, sid: str, kind: str, permissions: str, prompt: str,
                        meta: dict | None, now: datetime | None) -> Path:
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
            first = "investigating" if kind == "ticket" else "reviewing"
            extra = {k: v for k, v in (meta or {}).items() if k != "status"}
            (path / sf).write_text(write_frontmatter({"status": first, **extra}, ""),
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
    except (OSError, UnicodeDecodeError) as exc:
        info["error"] = f".session.toml ilegible: {exc}"
        return info
    kind = data.get("kind")
    if kind is not None and not isinstance(kind, str):
        info["error"] = f"kind inválido: {kind!r}"
        kind = None
    info.update(kind=kind, permissions=data.get("permissions"),
                created=str(data.get("created", "")), prUrl=data.get("pr_url"),
                reviewedSha=data.get("reviewed_sha"),
                # revisión de un stack: las PRs que revisa, de abajo hacia arriba (pr_url = la de arriba)
                stackPrs=[u for u in data.get("stack_prs") or [] if isinstance(u, str)] or None)
    ports, setup = data.get("ports", {}), data.get("setup", {})
    if not isinstance(ports, dict):
        ports = {}
    if not isinstance(setup, dict):
        setup = {}
    for link in repo_links(path):
        ok = link.exists()
        info["repos"].append({"name": link.name, "state": "ok" if ok else "missing",
                              "branch": _branch(link) if ok else None,
                              "port": ports.get(link.name), "setup": setup.get(link.name)})
    sf = state_file(info["kind"])
    try:
        migrate_state_file(path, info["kind"])
    except OSError as exc:
        info["error"] = f"no pude migrar a SESSION.md: {exc}"
    if sf and (path / sf).is_file():
        try:
            meta, _ = parse_frontmatter((path / sf).read_text(encoding="utf-8"))
            info["status"] = meta.pop("status", None)
            info["title"] = meta.pop("title", None)
            info["meta"] = meta
        except (SessionError, OSError, UnicodeDecodeError) as exc:
            info["error"] = f"{sf}: {exc}"
    return info


def session_cwd(root: Path, sid: str, data: dict | None = None) -> Path:
    """Dónde corre su claude: la carpeta de la sesión; la sesión `ide` corre en el repo del IDE."""
    data = data if data is not None else read_toml(session_path(root, sid) / ".session.toml")
    if data.get("kind") == "ide" and data.get("cwd"):
        return Path(data["cwd"])
    return session_path(root, sid)


IDE_SESSION = "ide"


def ensure_ide_session(root: Path, repo: str | None, resume: str | None) -> str | None:
    """La sesión "IDE" (pestaña junto a la manager): un claude en el repo del IDE (`[ide] repo` de
    config.toml). `resume` = la conversación de claude a retomar la primera vez. Idempotente."""
    if not repo or not Path(repo).expanduser().is_dir():
        return None
    path = session_path(root, IDE_SESSION)
    if (path / ".session.toml").is_file():
        return IDE_SESSION
    path.mkdir(parents=True, exist_ok=True)
    data = {"kind": "ide", "permissions": "default", "created": datetime.now().isoformat(timespec="seconds"),
            "cwd": str(Path(repo).expanduser().resolve())}
    if resume:
        data["claude_session"] = resume
    write_toml(path / ".session.toml", data)
    return IDE_SESSION


RECURSOS_MD = """# Recursos

Eres la sesión **Recursos** del IDE: cuidas la batería y la CPU del computador del usuario. Te pregunta
cosas como "por qué se me va la batería" o "qué puedo cortar".

## Cómo mirar

- `ide procs` (o `--json`): batería, servidores del IDE, contenedores y procesos que más consumen, cada
  recurso del IDE con su sesión, cuándo se usó por última vez (log del servidor, conversación de claude)
  y si está **ABANDONADO** (sin uso hace `idle_hours`, desarrollo mergeado/pausado, sesión archivada,
  o contenedor huérfano).
- `ide session ls` / `ide dev ls`: qué es cada sesión (`n-…`) y en qué está.
- `ps`, `top -l 1`, `docker ps`, `docker stats --no-stream`, `pmset -g batt` para mirar más.
- `alertas.log` (en tu carpeta): los avisos del vigilante del IDE (CPU alta sostenida, batería que cae
  rápido). Ese vigilante no usa IA; tú solo trabajas cuando el usuario te habla.

## Qué puedes cortar

- **Solo lo ABANDONADO, solo con `ide procs stop <id>`** (el comando se niega con lo que está en uso).
  Corta sin preguntar y cuéntale al usuario qué cortaste y por qué.
- Lo que está **en uso** pero consume mucho (p.ej. una api al 300% de CPU): **propónselo** con el dato
  (cuánto consume, de qué desarrollo es, desde cuándo) y el comando para que lo corte él
  (`ide procs stop <id>` en su terminal, o desde el módulo Servidores).
- **Nunca** mates procesos con `kill`/`pkill`, ni apps del usuario (Chrome, WhatsApp, Slack…), ni
  procesos de macOS, ni los `claude` de otras sesiones, ni la infraestructura compartida (la base y
  rabbitmq de `finnecto-api`): de esos solo informas y propones.
- Si algo del sistema consume mucho (Spotlight indexando, un proceso de macOS), explícale qué es y si
  se pasa solo.

Responde corto: qué consume, de quién es, qué cortaste y qué le propones cortar.
"""


def ensure_recursos_session(root: Path) -> str:
    """La sesión "Recursos" (pestaña junto a la manager y la IDE): un claude que mira qué consume el
    computador (`ide procs`). Idempotente; su CLAUDE.md y sus permisos se escriben si faltan."""
    import json
    path = session_path(root, "recursos")
    path.mkdir(parents=True, exist_ok=True)
    if not (path / ".session.toml").is_file():
        write_toml(path / ".session.toml", {"kind": "recursos", "permissions": "default", "title": "Recursos",
                                            "created": datetime.now().isoformat(timespec="seconds")})
    if not (path / "CLAUDE.md").is_file():
        (path / "CLAUDE.md").write_text(RECURSOS_MD, encoding="utf-8")
    settings = path / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    for rule in ("Bash(ide procs:*)", "Bash(ide session ls:*)", "Bash(ide dev ls:*)", "Bash(ide dev show:*)",
                 "Bash(ide server ls:*)", "Bash(ps:*)", "Bash(top -l:*)", "Bash(docker ps:*)",
                 "Bash(docker stats:*)", "Bash(pmset -g:*)", "Read(./alertas.log)"):
        if rule not in allow:
            allow.append(rule)
    settings.parent.mkdir(exist_ok=True)
    settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "recursos"


def list_sessions(root: Path) -> list[dict]:
    d = sessions_dir(root)
    if not d.is_dir():
        return []
    items = [read_session(root, p.name) for p in d.iterdir()
             if p.is_dir() and not p.is_symlink() and p.name not in RESERVED
             and not p.name.startswith(".")]
    return sorted(items, key=lambda s: (s["kind"] != "main", s["kind"] != "ide", s["kind"] != "recursos",
                                        s["created"], s["id"]))


def seed_workspace(root: Path) -> list[Path]:
    ide = root / ".ide"
    for d in (ide / "scripts", ide / "worktrees", sessions_dir(root) / "templates",
              ide / "permissions", ide / "prompts", ide / "skills" / "backlog"):
        d.mkdir(parents=True, exist_ok=True)
    files = {
        sessions_dir(root) / "CLAUDE.md": seeds.claude_md([r["id"] for r in discover_repos(root)]),
        sessions_dir(root) / "templates" / "ticket.md": seeds.TEMPLATE_TICKET,
        sessions_dir(root) / "templates" / "review.md": seeds.TEMPLATE_REVIEW,
        ide / "prompts" / "tickets-y-prs.md": seeds.PROMPT_TICKETS_PRS,
        ide / "prompts" / "review-pr.md": seeds.PROMPT_REVIEW_PR,
        ide / "prompts" / "rereview-pr.md": seeds.PROMPT_REREVIEW_PR,
        ide / "prompts" / "review-stack.md": seeds.PROMPT_REVIEW_STACK,
        ide / "skills" / "backlog" / "SKILL.md": seeds.SKILL_BACKLOG,
        ide / "manager.md": seeds.MANAGER_MD,
        ide / "prompts" / "nightly-review.md": seeds.PROMPT_NIGHTLY,
        ide / "permissions" / "analyze.json": json.dumps(seeds.PERM_ANALYZE, indent=2) + "\n",
        ide / "permissions" / "main.json": json.dumps(seeds.PERM_MAIN, indent=2) + "\n",
        ide / "permissions" / "full.json": json.dumps(seeds.PERM_FULL, indent=2) + "\n",
    }
    created = []
    for path, content in files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(path)
    return created
