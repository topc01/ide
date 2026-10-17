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
                reviewedSha=data.get("reviewed_sha"))
    ports, setup = data.get("ports", {}), data.get("setup", {})
    if not isinstance(ports, dict):
        ports = {}
    if not isinstance(setup, dict):
        setup = {}
    for link in sorted(p for p in path.iterdir() if p.is_symlink()):
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


def list_sessions(root: Path) -> list[dict]:
    d = sessions_dir(root)
    if not d.is_dir():
        return []
    items = [read_session(root, p.name) for p in d.iterdir()
             if p.is_dir() and not p.is_symlink() and p.name not in RESERVED
             and not p.name.startswith(".")]
    return sorted(items, key=lambda s: (s["kind"] != "main", s["created"], s["id"]))


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
        ide / "skills" / "backlog" / "SKILL.md": seeds.SKILL_BACKLOG,
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
