# server/ide_server/artifacts.py
"""Los artefactos que publica el claude de una sesión (herramienta `Artifact`: "Published <archivo> at
<url>") quedan como link en sus Adjuntos (`attachments/<fecha>-<nombre>.url`). Se lee el transcript de
forma incremental (offset por archivo en la base) y no se repite un link que ya está."""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from ide_server.db import Db
from ide_server.sessions_fs import list_sessions, session_path
from ide_server.supervisor import encode_project_dir

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


def scan(root: Path, home: Path, db: Db) -> int:
    """Revisa lo nuevo de los transcripts de cada sesión; devuelve cuántos links agregó."""
    added = 0
    for s in list_sessions(root):
        path = session_path(root, s["id"])
        d = home / ".claude" / "projects" / encode_project_dir(path.resolve())
        if not d.is_dir():
            continue
        att = path / "attachments"
        known = None
        for t in d.glob("*.jsonl"):
            key = f"artscan:{t}"
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
                    for x in content if isinstance(content, list) else []:
                        if x.get("type") != "tool_result":
                            continue
                        text = json.dumps(x.get("content"))
                        for src, url in _PUB.findall(text):
                            known = _known(att) if known is None else known
                            if url not in known:
                                _save(att, url, src, e.get("timestamp"))
                                known.add(url)
                                added += 1
            db.set(key, end)
    return added
