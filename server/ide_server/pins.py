# server/ide_server/pins.py
"""Pines (módulo Pines): mensajes de claude guardados para usar después (p.ej. un texto para mandar
por un hilo). Los mensajes salen limpios del transcript de la sesión (no de la terminal, que trae
saltos de línea y bordes del TUI). Los pines viven en la base (`kv` `pins:<clave del desarrollo>`)."""
from __future__ import annotations
import json
import secrets
from datetime import datetime
from pathlib import Path
from ide_server.db import Db
from ide_server.sessions_fs import read_toml, session_path
from ide_server.supervisor import encode_project_dir

MAX_TEXT = 20000


def recent_messages(root: Path, sid: str, home: Path, limit: int = 15) -> list[dict]:
    """Los últimos mensajes de texto de claude en la conversación actual de la sesión."""
    path = session_path(root, sid)
    d = home / ".claude" / "projects" / encode_project_dir(path.resolve())
    cs = (read_toml(path / ".session.toml") or {}).get("claude_session")
    f = d / f"{cs}.jsonl" if cs and (d / f"{cs}.jsonl").is_file() else \
        max(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, default=None) if d.is_dir() else None
    if f is None:
        return []
    st = f.stat()
    key = (str(f), st.st_size, st.st_mtime_ns, limit)
    if _cache.get(sid, (None,))[0] == key:          # la UI pregunta cada 8 s: sin cambios, lo mismo
        return _cache[sid][1]
    # solo la cola del transcript: los de sesiones largas pesan 100+ MB y leerlos enteros (y parsear cada
    # línea) llevaba el server a cientos de MB por llamada. Se agranda la ventana si no alcanzan los mensajes.
    out: list[dict] = []
    tail = TAIL_START
    while True:
        out = _assistant_texts(f, st.st_size, tail)
        if len(out) >= limit or tail >= min(st.st_size, TAIL_MAX):
            break
        tail *= 4
    res = out[-limit:][::-1]
    _cache[sid] = (key, res)
    return res


TAIL_START = 2 * 2**20
TAIL_MAX = 32 * 2**20
_cache: dict[str, tuple] = {}


def _assistant_texts(f: Path, size: int, tail: int) -> list[dict]:
    out = []
    with f.open("rb") as fh:
        fh.seek(max(0, size - tail))
        if size > tail:
            fh.readline()                            # la primera línea quedó cortada
        for raw in fh:
            if b'"assistant"' not in raw:            # filtro barato antes de parsear
                continue
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            if e.get("type") != "assistant":
                continue
            content = (e.get("message") or {}).get("content")
            text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text") \
                if isinstance(content, list) else content if isinstance(content, str) else ""
            text = text.strip()
            if len(text) >= 20:                      # sin los "Ahora reviso…" de una línea corta
                out.append({"id": e.get("uuid") or secrets.token_hex(6), "at": e.get("timestamp"), "text": text[:MAX_TEXT]})
    return out


def all_pins(db: Db) -> dict[str, list[dict]]:
    return db.with_prefix("pins:")


def add(db: Db, key: str, text: str, source: str | None) -> dict:
    pin = {"id": secrets.token_hex(6), "text": text[:MAX_TEXT], "source": source,
           "at": datetime.now().isoformat(timespec="minutes")}
    db.set(f"pins:{key}", [pin, *(db.get(f"pins:{key}") or [])])
    return pin


def remove(db: Db, key: str, pid: str) -> None:
    rest = [p for p in db.get(f"pins:{key}") or [] if p.get("id") != pid]
    db.set(f"pins:{key}", rest) if rest else db.delete(f"pins:{key}")
