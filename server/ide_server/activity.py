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
_TASK = re.compile(r"<task-id>([\w-]+)</task-id>")       # a veces el aviso trae solo el id del agente
_AGENT_ID = re.compile(r"agentId: ([\w-]+)")
MAX_BACKGROUND_S = 3 * 3600         # uno más viejo se da por muerto (p.ej. claude se reinició sin avisar)
MAX_SILENT_S = 20 * 60              # uno que no escribe en su conversación hace 20 min, también


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
    tasks_done: set[str] = set()
    agent_of: dict[str, str] = {}       # tool_use_id → agentId (del resultado «Async agent launched … agentId: …»)
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                tasks_done |= set(_TASK.findall(line))
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
                            if (m := _AGENT_ID.search(body)):
                                agent_of[c["tool_use_id"]] = m.group(1)
    except OSError:
        return 0
    # los subagentes dejan su conversación en <transcript>/subagents/agent-*.jsonl (+ .meta.json con su
    # toolUseId): uno cortado con Esc no avisa (`stoppedByUser`), y uno que ya no escribe hace rato murió
    import time
    sub = f.with_suffix("") / "subagents"
    for meta in sub.glob("agent-*.meta.json") if sub.is_dir() else []:
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tid = m.get("toolUseId")
        if tid not in launched or tid in done:
            continue
        log = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
        try:
            idle = time.time() - log.stat().st_mtime
        except OSError:
            idle = 0
        if m.get("stoppedByUser") or idle > MAX_SILENT_S:
            done.add(tid)
    done |= {tid for tid, aid in agent_of.items() if aid in tasks_done}
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


MAX_MESSAGE = 12_000


def questions_in(text: str | None) -> list[str]:
    """Las preguntas de un mensaje: líneas que terminan en «?» (sin viñetas ni negritas)."""
    out = []
    for line in (text or "").splitlines():
        line = re.sub(r"^[\s>*\-•\d.)]+", "", line).replace("**", "").strip()
        if line.endswith("?") and len(line) > 3:
            out.append(line)
    return out[-4:]


_LOGIN = re.compile(r"\bide browser (login|new)\b")


def wait_reason(text: str | None) -> str:
    """Por qué te espera al terminar el turno: «login» si te pide iniciar una sesión de navegador (`ide browser
    login|new`), «question» si termina con una pregunta, si no «turn»."""
    if _LOGIN.search(text or ""):
        return "login"
    return "question" if questions_in(text) else "turn"


def _summary(name: str, inp: dict) -> str:
    """Una línea de lo que hace una herramienta: el comando, el archivo, la búsqueda…"""
    if name == "Bash" and isinstance(inp.get("description"), str) and inp["description"].strip():
        return f"{name}: {inp['description'].strip()[:300]}"
    for k in ("command", "file_path", "pattern", "url", "query", "description", "prompt", "path"):
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            return f"{name}: {v.strip().splitlines()[0][:300]}"
    return name


def _resolve(transcript: str | None, home: Path) -> Path | None:
    if not transcript:
        return None
    f = Path(transcript).expanduser().resolve()
    if f.suffix != ".jsonl" or not f.is_relative_to((home / ".claude" / "projects").resolve()) or not f.is_file():
        return None
    return f


def detail(transcript: str | None, home: Path, recent: int = 8) -> dict:
    """Para el detalle de «te esperan» / «trabajando»: el último mensaje de claude (entero), la herramienta que
    pidió y todavía no tiene resultado (un permiso o una pregunta con opciones) y lo último que hizo."""
    out: dict = {"message": None, "messageAt": None, "pending": None, "recent": [], "unresolved": 0}
    f = _resolve(transcript, home)
    if f is None:
        return out
    try:
        with open(f, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 1_500_000))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return out
    uses: list[tuple[str, str, dict, str]] = []      # (id, nombre, input, hora)
    results: set[str] = set()
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("isSidechain"):
            continue
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if e.get("type") == "assistant" and c.get("type") == "text" and c.get("text", "").strip():
                out["message"], out["messageAt"] = c["text"].strip()[:MAX_MESSAGE], e.get("timestamp")
            elif e.get("type") == "assistant" and c.get("type") == "tool_use":
                uses.append((c.get("id") or "", c.get("name") or "?", c.get("input") or {}, e.get("timestamp") or ""))
            elif c.get("type") == "tool_result":
                results.add(c.get("tool_use_id") or "")
    out["unresolved"] = sum(1 for u in uses if u[0] not in results and u[0])
    out["recent"] = [{"tool": n, "summary": _summary(n, i), "at": t} for _, n, i, t in uses[-recent:]][::-1] if recent else []
    if uses and uses[-1][0] not in results:
        tid, name, inp, at = uses[-1]
        p: dict = {"id": tid, "tool": name, "summary": _summary(name, inp), "at": at}
        if name == "AskUserQuestion":
            p["questions"] = [{"question": q.get("question"), "header": q.get("header"),
                               "multiSelect": bool(q.get("multiSelect")),
                               "options": [{"label": o.get("label"), "description": o.get("description")}
                                           for o in q.get("options") or [] if isinstance(o, dict)]}
                              for q in inp.get("questions") or [] if isinstance(q, dict)]
        elif name == "Bash":
            p["command"] = str(inp.get("command") or "")[:4000]
            p["description"] = inp.get("description")
        out["pending"] = p
    return out
