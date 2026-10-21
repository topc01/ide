# server/ide_server/later.py
"""Pendientes "para después": preguntas o temas de un desarrollo que el usuario no puede resolver ahora
(p.ej. los tiene que conversar con el equipo). Los deja la sesión (`ide later add`) o el usuario desde
la UI; se responden desde el módulo "Para después" (la respuesta se le manda a la sesión) o se
descartan. En la base: `kv` `later:<id>` = {id, key, text, context, actor, created, status, answer,
resolved}; `key` = clave del desarrollo (`s:<sesión>`, `st:<stack>`, `p:<url>`)."""
from __future__ import annotations
import secrets
from datetime import datetime
from ide_server.db import Db

MAX_TEXT = 2000


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def add(db: Db, key: str, text: str, context: str | None, actor: str) -> dict:
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        raise ValueError("el pendiente necesita un texto")
    item = {"id": f"{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(3)}", "key": key, "text": text,
            "context": (context or "").strip()[:MAX_TEXT] or None, "actor": actor, "created": _now(),
            "status": "open", "answer": None, "resolved": None}
    db.set(f"later:{item['id']}", item)
    return item


def get(db: Db, item_id: str) -> dict | None:
    return db.get(f"later:{item_id}")


def items(db: Db, *, open_only: bool = True) -> list[dict]:
    out = [v for v in db.with_prefix("later:").values() if not open_only or v.get("status") == "open"]
    return sorted(out, key=lambda v: v["created"])


def close(db: Db, item_id: str, status: str, answer: str | None = None) -> dict:
    item = get(db, item_id)
    if item is None:
        raise KeyError(item_id)
    item.update(status=status, answer=answer, resolved=_now())
    db.set(f"later:{item_id}", item)
    return item


def as_markdown(db: Db, names: dict[str, str] | None = None) -> str:
    """Los abiertos, para la revisión de la manager (más viejos primero)."""
    names = names or {}
    lines = []
    for it in items(db):
        days = (datetime.now() - datetime.fromisoformat(it["created"])).days
        who = "la sesión" if it["actor"].startswith("claude") else "el usuario"
        lines.append(f"- [{it['key']}{' · ' + names[it['key']] if it['key'] in names else ''}] hace {days} d "
                     f"({who}): «{' '.join(it['text'].split())}»"
                     + (f" — contexto: {' '.join(it['context'].split())[:300]}" if it.get("context") else ""))
    return "\n".join(lines) or "(ninguno)"
