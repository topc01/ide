# server/ide_server/artifacts.py
"""Los artefactos que publica el claude de una sesión (herramienta `Artifact`: "Published <archivo> at
<url>") quedan como link en sus Adjuntos (`attachments/<fecha>-<nombre>.url`). Se lee el transcript de
forma incremental (offset por archivo en la base) y no se repite un link que ya está.

Además, cada sesión lleva su lista (`kv artifacts:<sesión>` = [{url, title, description, at, card}]) para la
card y el módulo Artefactos; `card: false` = no se muestra en la card. Republicar el mismo artefacto no lo
repite (actualiza su título)."""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from ide_server.db import Db
from ide_server.sessions_fs import list_sessions, session_path
from ide_server.supervisor import encode_project_dir

URL_RE = re.compile(r"^https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9_-]{6,80}$")
_PUB = re.compile(r"Published (\S+) at (https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9-]+)")


def _known(att: Path) -> set[str]:
    out = set()
    for f in att.glob("*.url") if att.is_dir() else []:
        m = re.search(r"^URL=(\S+)", f.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            out.add(m.group(1))
    return out


def _save(att: Path, url: str, source: str, at: str | None) -> None:
    name = re.sub(r"[^A-Za-z0-9._ -]+", "-", Path(source).stem).strip(" .-")[:70] or "artefacto"
    try:
        stamp = datetime.fromisoformat((at or "").replace("Z", "+00:00")).astimezone().strftime("%Y%m%d-%H%M%S")
    except ValueError:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    att.mkdir(exist_ok=True)
    (att / f"{stamp}-artefacto-{name}.url").write_text(f"[InternetShortcut]\nURL={url}\n", encoding="utf-8")


def items(db: Db, sid: str) -> list[dict]:
    return list(db.get(f"artifacts:{sid}") or [])


def _put(db: Db, sid: str, found: list[dict]) -> bool:
    cur = items(db, sid)
    by = {a["url"]: a for a in cur}
    changed = False
    for f in found:
        old = by.get(f["url"])
        if old is None:
            cur.append({**f, "card": True})
            by[f["url"]] = cur[-1]
            changed = True
        elif f.get("title") and (old.get("title"), old.get("description")) != (f["title"], f.get("description") or old.get("description")):
            old.update(title=f["title"], description=f.get("description") or old.get("description"))
            changed = True
    if changed:
        db.set(f"artifacts:{sid}", cur)
    return changed


def _local(at: str | None) -> str:
    try:
        return datetime.fromisoformat((at or "").replace("Z", "+00:00")).astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    except ValueError:
        return datetime.now().isoformat(timespec="seconds")


def add(db: Db, sid: str, url: str, title: str | None = None) -> dict:
    url = url.strip()
    if not URL_RE.match(url):
        raise ValueError("tiene que ser el link de un artefacto: https://claude.ai/artifact/<id>")
    _put(db, sid, [{"url": url, "title": (title or "").strip()[:200] or None, "description": None,
                    "at": datetime.now().isoformat(timespec="seconds")}])
    return next(a for a in items(db, sid) if a["url"] == url)


def remove(db: Db, sid: str, url: str) -> bool:
    cur = items(db, sid)
    rest = [a for a in cur if a["url"] != url]
    if len(rest) != len(cur):
        db.set(f"artifacts:{sid}", rest)
    return len(rest) != len(cur)


def set_card(db: Db, sid: str, url: str, show: bool) -> bool:
    cur = items(db, sid)
    for a in cur:
        if a["url"] == url:
            a["card"] = bool(show)
            db.set(f"artifacts:{sid}", cur)
            return True
    return False


def scan(root: Path, home: Path, db: Db) -> int:
    """Revisa lo nuevo de los transcripts de cada sesión; devuelve cuántos cambios hubo (links en Adjuntos y
    artefactos nuevos o retitulados en la lista de la sesión)."""
    added = 0
    for s in list_sessions(root):
        path = session_path(root, s["id"])
        d = home / ".claude" / "projects" / encode_project_dir(path.resolve())
        if not d.is_dir():
            continue
        att = path / "attachments"
        known = None
        for t in d.glob("*.jsonl"):
            key = f"artscan2:{t}"                       # 2: se releyó todo una vez para armar la lista por sesión
            descs: dict[str, str] = {}
            found: list[dict] = []
            size, off = t.stat().st_size, db.get(key, 0)
            if size <= off:
                continue
            end = off
            with open(t, "rb") as fh:                   # línea a línea: los transcripts pesan 100+ MB
                fh.seek(off)
                for raw in fh:
                    if not raw.endswith(b"\n"):           # solo líneas completas
                        break
                    end += len(raw)
                    if b'"Artifact"' not in raw and b"Published " not in raw:
                        continue
                    try:
                        e = json.loads(raw)
                    except ValueError:
                        continue
                    content = (e.get("message") or {}).get("content")
                    r = e.get("toolUseResult")
                    for x in content if isinstance(content, list) else []:
                        if x.get("type") == "tool_use" and x.get("name") == "Artifact":
                            if isinstance((x.get("input") or {}).get("description"), str):
                                descs[x.get("id") or ""] = x["input"]["description"][:400]
                            continue
                        if x.get("type") != "tool_result":
                            continue
                        if isinstance(r, dict) and r.get("artifact_id") and not r.get("asset") \
                                and URL_RE.match(str(r.get("url") or "")):
                            found.append({"url": r["url"], "title": str(r.get("title") or "")[:200] or None,
                                          "description": descs.get(x.get("tool_use_id") or ""),
                                          "at": _local(e.get("timestamp"))})
                        text = json.dumps(x.get("content"))
                        for src, url in _PUB.findall(text):
                            known = _known(att) if known is None else known
                            if url not in known:
                                _save(att, url, src, e.get("timestamp"))
                                known.add(url)
                                added += 1
            if found and _put(db, s["id"], found):
                added += 1
            db.set(key, end)
    return added
