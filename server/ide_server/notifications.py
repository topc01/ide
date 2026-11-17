# server/ide_server/notifications.py
"""Las notificaciones del IDE (campana arriba a la derecha): todo lo que antes era solo un aviso de macOS (una
sesión te espera, Recursos…) más las PRs que te piden revisar. `kv notifs` = [{id, at, kind, title, body, focus,
read}] (las últimas 200, la más nueva primero). `focus` = la sesión (o la PR, `p:<url>`) que abre el click."""
from __future__ import annotations

import secrets
from datetime import datetime

MAX = 200


def items(db) -> list[dict]:
    return list(db.get("notifs") or [])


def add(db, kind: str, title: str, body: str | None = None, focus: str | None = None) -> dict:
    n = {"id": secrets.token_hex(5), "at": datetime.now().isoformat(timespec="seconds"), "kind": kind,
         "title": title[:300], "body": (body or "")[:600] or None, "focus": focus, "read": False}
    db.set("notifs", [n, *items(db)][:MAX])
    return n


def mark_read(db, nid: str | None = None) -> None:
    cur = items(db)
    for n in cur:
        if nid is None or n["id"] == nid:
            n["read"] = True
    db.set("notifs", cur)


def remove(db, nid: str | None = None) -> None:
    db.set("notifs", [] if nid is None else [n for n in items(db) if n["id"] != nid])
