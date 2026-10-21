# server/ide_server/feedback.py
"""Material para la revisión nocturna de la sesión manager (`ide feedback collect`).

Por sesión: lo anotado en `## Feedback` de su SESSION.md y los mensajes del usuario de sus transcripts
desde `since` (con un trozo de lo que la sesión acababa de decir/hacer), para que la manager detecte
también las correcciones que la sesión no anotó. Los planes que arma la manager van en
`.ide/sessions/<principal>/feedback/AAAA-MM-DD.md` (frontmatter `status: pending|applied`)."""
from __future__ import annotations
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from ide_server.sessions_fs import find_main, list_sessions, parse_frontmatter, session_path
from ide_server.supervisor import encode_project_dir

MAX_MSGS = 80
MAX_TEXT = 600
_SKIP = ("<command-", "<local-command", "<bash-", "<task-notification", "<system-reminder", "Caveat:", "[Request interrupted")


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def _messages(transcript: Path, since: datetime) -> list[dict]:
    out, last_assistant = [], ""
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        msg = e.get("message") or {}
        if e.get("type") == "assistant":
            t = _text(msg.get("content")).strip()
            if t:
                last_assistant = t
            continue
        if e.get("type") != "user" or e.get("isMeta") or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            continue
        text = _text(content).strip()
        if not text or text.startswith(_SKIP):
            continue
        try:
            at = datetime.fromisoformat((e.get("timestamp") or "").replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except ValueError:
            continue
        if at < since:
            continue
        out.append({"at": at.isoformat(timespec="minutes"), "user": text[:MAX_TEXT],
                    "after": last_assistant[-300:]})
    return out


def _feedback_section(md: Path) -> str:
    if not md.is_file():
        return ""
    _, body = parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
    m = re.search(r"^## Feedback[^\n]*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return m.group(1).strip() if m else ""


def collect(root: Path, home: Path, since: datetime | None = None) -> dict:
    since = since or datetime.now() - timedelta(days=7)
    main = find_main(root)
    out = []
    for s in list_sessions(root):
        if s["id"] == main:
            continue
        path = session_path(root, s["id"])
        d = home / ".claude" / "projects" / encode_project_dir(path.resolve())
        msgs = []
        for t in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
            if datetime.fromtimestamp(t.stat().st_mtime) >= since:
                msgs += _messages(t, since)
        msgs.sort(key=lambda m: m["at"])
        noted = _feedback_section(path / "SESSION.md")
        if msgs or noted:
            out.append({"id": s["id"], "kind": s["kind"], "title": s.get("title"), "feedback": noted,
                        "messages": msgs[-MAX_MSGS:]})
    try:                                        # pendientes para después, abiertos (los ve la manager)
        from ide_server.db import Db
        from ide_server import later
        db = Db(root)
        pending = later.as_markdown(db, db.dev_names())
    except Exception:  # noqa: BLE001 — sin base: sin esa sección
        pending = None
    return {"since": since.isoformat(timespec="minutes"), "sessions": out, "later": pending}


def as_markdown(data: dict) -> str:
    lines = [f"# Material para la revisión de feedback (desde {data['since']})", ""]
    for s in data["sessions"]:
        lines += [f"## {s['id']} ({s['kind']}) — {s.get('title') or ''}", ""]
        if s["feedback"]:
            lines += ["### Feedback anotado en SESSION.md", s["feedback"], ""]
        if s["messages"]:
            lines += ["### Mensajes del usuario (con lo último que dijo la sesión antes)"]
            for m in s["messages"]:
                after = " ".join(m["after"].split())
                lines.append(f"- [{m['at']}] " + (f"(tras: «…{after[-160:]}») " if after else "")
                             + "usuario: «" + " ".join(m["user"].split()) + "»")
            lines.append("")
    if not data["sessions"]:
        lines.append("(nada nuevo)")
    if data.get("later"):
        lines += ["", "## Pendientes para después (abiertos, más viejos primero)", data["later"]]
    return "\n".join(lines) + "\n"


def pending_plans(root: Path) -> list[str]:
    main = find_main(root)
    d = session_path(root, main) / "feedback" if main else None
    if not d or not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.md")):
        if f.name.startswith("material-"):      # lo que juntó el IDE, no un plan
            continue
        try:
            meta, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if meta.get("status") == "pending":
            out.append(f.name)
    return out
