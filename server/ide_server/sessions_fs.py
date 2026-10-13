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
