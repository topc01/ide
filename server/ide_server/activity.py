# server/ide_server/activity.py
"""Actividad del claude de una sesión, por sus hooks (`ide hook`): trabajando (empezó un turno) o
esperando tu input (terminó el turno o pide un permiso). La nota de "esperando" es la primera línea
del último mensaje de claude."""
from __future__ import annotations
import json
import re
from pathlib import Path

MAX_NOTE = 200


def first_line(text: str) -> str | None:
    for line in text.splitlines():
        line = re.sub(r"[*_`#>]+", "", line).strip(" -•\t")
        if line:
            return line[:MAX_NOTE]
    return None


def last_note(transcript: str | None, home: Path) -> str | None:
    """Primera línea del último mensaje de texto de claude en el transcript (solo transcripts de
    Claude Code: `~/.claude/projects/…/*.jsonl`)."""
    if not transcript:
        return None
    f = Path(transcript).expanduser().resolve()
    if f.suffix != ".jsonl" or not f.is_relative_to((home / ".claude" / "projects").resolve()) or not f.is_file():
        return None
    try:
        with open(f, "rb") as fh:                   # solo la cola: los transcripts crecen mucho
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 400_000))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "assistant":
            continue
        content = (e.get("message") or {}).get("content")
        text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text") \
            if isinstance(content, list) else content if isinstance(content, str) else ""
        if text.strip():
            return first_line(text)
    return None


_ASYNC = "Async agent launched"
_NOTIF = re.compile(r"<tool-use-id>(toolu_[\w-]+)</tool-use-id>")
MAX_BACKGROUND_S = 3 * 3600         # uno más viejo se da por muerto (p.ej. claude se reinició sin avisar)


def pending_agents(transcript: str | None, home: Path) -> int:
    """Subagentes que claude lanzó en segundo plano y cuyo aviso de término todavía no llegó:
    claude cierra el turno mientras corren, pero sigue trabajando. Los comandos de terminal en segundo plano
    no cuentan (un servidor corre para siempre)."""
    from datetime import datetime, timezone
    if not transcript:
        return 0
    f = Path(transcript).expanduser().resolve()
    if f.suffix != ".jsonl" or not f.is_relative_to((home / ".claude" / "projects").resolve()) or not f.is_file():
        return 0
    launched: dict[str, str] = {}       # tool_use_id → hora
    asked: dict[str, str] = {}          # Agent/Task lanzados (aún sin saber si en segundo plano)
    done: set[str] = set()
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "toolu_" not in line:
                    continue
                done |= set(_NOTIF.findall(line))       # <task-notification> (completado, fallido o detenido)
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                content = (e.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use" and c.get("name") in ("Agent", "Task"):
                        asked[c.get("id")] = e.get("timestamp") or ""
                    elif c.get("type") == "tool_result" and c.get("tool_use_id") in asked:
                        body = json.dumps(c.get("content"))
                        if _ASYNC in body:
                            launched[c["tool_use_id"]] = asked[c["tool_use_id"]]
    except OSError:
        return 0
    now = datetime.now(timezone.utc)
    n = 0
    for tid, ts in launched.items():
        if tid in done:
            continue
        try:
            age = (now - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
        except ValueError:
            continue
        if age < MAX_BACKGROUND_S:
            n += 1
    return n
