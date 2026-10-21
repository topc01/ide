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
