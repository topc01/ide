# server/ide_server/later.py
"""Bloqueantes (antes «para después»): decisiones (`kind: decision`, algo que el usuario decide o conversa) y
pendientes (`kind: pending`, algo que se espera de alguien) de un desarrollo; `blocks` = la sesión ya no puede
avanzar en nada más (el desarrollo pasa a Bloqueado mientras quede uno abierto). Antes: preguntas o temas de un desarrollo que el usuario no puede resolver ahora
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


KINDS = ("decision", "pending")


def _next_num(db: Db) -> int:
    n = int(db.get("laterseq") or 0) + 1        # una sola numeración (D3, P4): fuera del prefijo `later:`
    db.set("laterseq", n)
    return n


def code(item: dict) -> str:
    """El código corto: D<n> (decisión) o P<n> (pendiente)."""
    return f"{'P' if item.get('kind') == 'pending' else 'D'}{item.get('num') or '?'}"


def number_all(db: Db) -> None:
    """Numera los que no tienen número (los de antes), del más viejo al más nuevo."""
    # los abiertos primero (son los que se ven: D1, P2…), después los cerrados
    rows = sorted((v for v in db.with_prefix("later:").values() if isinstance(v, dict) and not v.get("num")),
                  key=lambda v: (v.get("status") != "open", v.get("created") or ""))
    for v in rows:
        v["num"] = _next_num(db)
        db.set(f"later:{v['id']}", v)


def add(db: Db, key: str, text: str, context: str | None, actor: str, *, artifact: str | None = None,
        with_: str | None = None, kind: str | None = None, blocks: bool = False) -> dict:
    """Una decisión: la pregunta (una línea), opcionalmente el artefacto con el análisis y con quién conversarla."""
    from ide_server.artifacts import URL_RE
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        raise ValueError("la decisión necesita la pregunta")
    artifact = (artifact or "").strip() or None
    if artifact and not URL_RE.match(artifact):
        raise ValueError("--artifact tiene que ser el link de un artefacto: https://claude.ai/artifact/<id>")
    item = {"id": f"{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(3)}", "key": key, "text": text,
            "context": (context or "").strip()[:MAX_TEXT] or None, "actor": actor, "created": _now(),
            "status": "open", "answer": None, "resolved": None, "artifact": artifact,
            "with": (with_ or "").strip()[:80] or None,
            "kind": kind if kind in KINDS else "decision", "blocks": bool(blocks), "num": _next_num(db)}
    db.set(f"later:{item['id']}", item)
    return item


def get(db: Db, item_id: str) -> dict | None:
    """Por id o por código (D3 / P4)."""
    import re
    m = re.fullmatch(r"[DPdp](\d+)", str(item_id or "").strip())
    if m:
        return next((v for v in db.with_prefix("later:").values() if isinstance(v, dict) and v.get("num") == int(m.group(1))), None)
    return db.get(f"later:{item_id}")


def items(db: Db, *, open_only: bool = True) -> list[dict]:
    out = [v for v in db.with_prefix("later:").values() if not open_only or v.get("status") == "open"]
    return sorted(out, key=lambda v: v["created"])


def update(db: Db, item_id: str, *, text: str | None = None, artifact: str | None = None, with_: str | None = None,
           kind: str | None = None, blocks: bool | None = None) -> dict:
    """Editar una decisión abierta: la pregunta, el artefacto y con quién ("" los saca)."""
    from ide_server.artifacts import URL_RE
    item = get(db, item_id)
    if item is None or item.get("status") != "open":
        raise KeyError(item_id)
    if text is not None:
        text = text.strip()[:MAX_TEXT]
        if not text:
            raise ValueError("la decisión necesita la pregunta")
        item["text"] = text
    if artifact is not None:
        artifact = artifact.strip() or None
        if artifact and not URL_RE.match(artifact):
            raise ValueError("el artefacto tiene que ser un link https://claude.ai/artifact/<id>")
        item["artifact"] = artifact
    if with_ is not None:
        item["with"] = with_.strip()[:80] or None
    if kind in KINDS:
        item["kind"] = kind
    if blocks is not None:
        item["blocks"] = bool(blocks)
    db.set(f"later:{item['id']}", item)
    return item


def close(db: Db, item_id: str, status: str, answer: str | None = None) -> dict:
    item = get(db, item_id)
    if item is None:
        raise KeyError(item_id)
    item.update(status=status, answer=answer, resolved=_now())
    db.set(f"later:{item['id']}", item)
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
