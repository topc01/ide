# server/ide_server/tools.py
"""Registro de herramientas evaluadas (plugins, skills, MCP, apps) que lleva la sesión Plugins: una fila por
herramienta (nombre, link, estado, motivo) y el historial de cada cambio de estado. `ide tools` y el módulo
Configuración de la UI."""
from __future__ import annotations
from datetime import datetime
from ide_server.db import Db
from ide_server.sessions_fs import SessionError

STATES = ("por-evaluar", "cubierta", "descartada", "a-implementar", "en-uso", "retirada")
MAX = 4000


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _state(s: str | None) -> str:
    s = (s or "").strip().lower()
    if s not in STATES:
        raise SessionError("bad_state", f"estado inválido: {s!r} (uno de: {', '.join(STATES)})")
    return s


def _link(link: str | None) -> str | None:
    """Solo http(s): el link se abre desde la UI (un `javascript:` correría en el IDE)."""
    link = (link or "").strip()
    if link and not link.lower().startswith(("http://", "https://")):
        raise SessionError("bad_link", f"el link tiene que ser http(s): {link[:80]!r}")
    return link[:2000] or None


def _row(r) -> dict:
    return {"name": r[0], "link": r[1], "state": r[2], "reason": r[3], "created": r[4], "updated": r[5]}


def get(db: Db, name: str) -> dict | None:
    with db._lock:
        r = db._conn.execute("SELECT name, link, state, reason, created, updated FROM tools WHERE name = ?",
                             (name.strip(),)).fetchone()
    return _row(r) if r else None


def add(db: Db, name: str, link: str | None, state: str, reason: str | None, actor: str, at: str | None = None) -> dict:
    name = (name or "").strip()[:200]
    if not name:
        raise SessionError("bad_request", "falta el nombre de la herramienta")
    if get(db, name):
        raise SessionError("exists", f"{name} ya está en el registro: usa `ide tools set {name} <estado> -m …`")
    st, at = _state(state), at or _now()
    reason = (reason or "").strip()[:MAX] or None
    with db._lock:
        db._conn.execute("INSERT INTO tools VALUES (?, ?, ?, ?, ?, ?)", (name, _link(link), st, reason, at, at))
        db._conn.execute("INSERT INTO tools_history (name, at, from_state, to_state, reason, actor) VALUES (?, ?, ?, ?, ?, ?)",
                         (name, at, None, st, reason, actor))
    return get(db, name)


def set_state(db: Db, name: str, state: str, reason: str | None, actor: str, link: str | None = None) -> dict:
    cur = get(db, name)
    if cur is None:
        raise SessionError("not_found", f"{name} no está en el registro: usa `ide tools add`")
    st, at = _state(state), _now()
    reason = (reason or "").strip()[:MAX] or None
    with db._lock:
        db._conn.execute("UPDATE tools SET state = ?, reason = COALESCE(?, reason), link = COALESCE(?, link), updated = ? "
                         "WHERE name = ?", (st, reason, _link(link), at, cur["name"]))
        db._conn.execute("INSERT INTO tools_history (name, at, from_state, to_state, reason, actor) VALUES (?, ?, ?, ?, ?, ?)",
                         (cur["name"], at, cur["state"], st, reason, actor))
    return get(db, cur["name"])


def listing(db: Db, q: str | None = None, state: str | None = None) -> list[dict]:
    conds, args = [], []
    if state:
        conds.append("state = ?"); args.append(_state(state))
    if q:
        conds.append("(name LIKE ? OR reason LIKE ? OR link LIKE ?)"); args += [f"%{q.strip()}%"] * 3
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    with db._lock:
        rows = db._conn.execute(f"SELECT name, link, state, reason, created, updated FROM tools {where} "
                                "ORDER BY updated DESC", args).fetchall()
    return [_row(r) for r in rows]


def history(db: Db, name: str) -> list[dict]:
    with db._lock:
        rows = db._conn.execute("SELECT at, from_state, to_state, reason, actor FROM tools_history WHERE name = ? "
                                "ORDER BY id", (name.strip(),)).fetchall()
    return [{"at": a, "from": f, "to": t, "reason": r, "actor": ac} for a, f, t, r, ac in rows]
