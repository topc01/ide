# server/ide_server/tour.py
"""Recorridos (`ide tour`): la sesión prepara los pasos de lo que hizo (pantalla + qué mirar) y el usuario lo
recorre cuando quiere desde la card: el IDE abre un Chrome con la sesión local compartida y un recuadro que le
dice qué mirar en cada paso; lo que escribe se junta y le llega a la sesión al terminar. `kv tour:<sesión>` =
{steps, at, title, status: ready|running|done, notes}."""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

PLAYWRIGHT_CORE = "1.64.1"
MAX_STEPS = 30


def runtime_dir() -> Path:
    return Path.home() / ".cache" / "ide-tour"


def validate(raw, root: Path) -> list[dict]:
    """Los pasos: [{url (localhost o un sitio de prueba de `[browsers] test_hosts`), text, selector?}].
    ValueError si algo no sirve."""
    from ide_server.browsers import is_local
    if not isinstance(raw, list) or not raw:
        raise ValueError("el recorrido necesita al menos un paso: [{\"url\": …, \"text\": …}]")
    if len(raw) > MAX_STEPS:
        raise ValueError(f"máximo {MAX_STEPS} pasos")
    out = []
    for i, s in enumerate(raw, 1):
        if not isinstance(s, dict):
            raise ValueError(f"paso {i}: tiene que ser un objeto {{url, text, selector?}}")
        url, text = str(s.get("url") or "").strip(), str(s.get("text") or "").strip()
        if any(c.isspace() for c in url) or not is_local(root, url):
            raise ValueError(f"paso {i}: la url tiene que ser de localhost (o de un sitio de prueba de "
                             f"[browsers] test_hosts): {url[:120]!r}")
        if not text:
            raise ValueError(f"paso {i}: falta `text` (qué tiene que mirar el usuario)")
        sel = s.get("selector")
        out.append({"url": url, "text": text[:600], **({"selector": str(sel)[:300]} if sel else {})})
    return out


def ensure_runtime() -> Path:
    """playwright-core en ~/.cache/ide-tour (una vez; usa el Chrome instalado, no baja navegadores)."""
    d = runtime_dir()
    if not (d / "node_modules" / "playwright-core").is_dir():
        d.mkdir(parents=True, exist_ok=True)
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("falta npm (node) para abrir el recorrido")
        r = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--prefix", str(d), f"playwright-core@{PLAYWRIGHT_CORE}"],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError("no pude instalar playwright-core: " + (r.stderr or r.stdout)[-300:])
    return d


def launch(root: Path, sid: str, tour: dict, ide_url: str, theme: str = "dark") -> str:
    """Abre el Chrome del recorrido (proceso aparte). Devuelve el token con que avisa al terminar."""
    from ide_server.browsers import _shared_local
    d = ensure_runtime()
    cookies, login = _shared_local(root)
    token = secrets.token_urlsafe(24)
    cfg = {"steps": tour["steps"], "sid": sid, "ide": ide_url, "token": token, "cookies": str(cookies),
           "login": str(login), "title": tour.get("title") or sid,
           "theme": theme, "pos_file": str(runtime_dir() / "widget-pos.json")}
    fd, path = tempfile.mkstemp(prefix="tour-", suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(cfg, fh)
    os.chmod(path, 0o600)
    script = Path(__file__).parent / "assets" / "tour.js"
    stop_open(sid)                                   # un recorrido por sesión: el anterior se cierra
    log = open(runtime_dir() / f"{sid}.log", "w")
    proc = subprocess.Popen([shutil.which("node") or "node", str(script), path], cwd=d, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True, env={**os.environ, "NODE_PATH": str(d / "node_modules")})
    reg = runtime_dir() / "procs"
    reg.mkdir(exist_ok=True)
    (reg / f"{proc.pid}.json").write_text(json.dumps({"sid": sid, "started": time.time()}), encoding="utf-8")
    return token


def _is_tour(pid: int) -> bool:
    out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return "ide_server/assets/tour.js" in out


def open_tours() -> list[dict]:
    """Los recorridos abiertos (su node y su Chrome, en un grupo de procesos): [{pid, sid, started}]. También los de
    antes de este registro (sesión «?»)."""
    reg = runtime_dir() / "procs"
    known = {}
    for f in (reg.glob("*.json") if reg.is_dir() else []):
        try:
            known[int(f.stem)] = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            f.unlink(missing_ok=True)
    out = []
    ps = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    for line in ps.splitlines():
        pid_s, _, cmd = line.strip().partition(" ")
        if "ide_server/assets/tour.js" in cmd and pid_s.isdigit():
            info = known.pop(int(pid_s), {})
            out.append({"pid": int(pid_s), "sid": info.get("sid") or "?", "started": info.get("started")})
    for pid in known:                                 # ya terminaron
        (reg / f"{pid}.json").unlink(missing_ok=True)
    return out


def stop_tour(pid: int) -> None:
    """Cierra un recorrido: su node y su Chrome (el grupo de procesos que abrió)."""
    import signal
    if not _is_tour(pid):
        raise ValueError(f"{pid} no es un recorrido")
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    (runtime_dir() / "procs" / f"{pid}.json").unlink(missing_ok=True)


def stop_open(sid: str) -> None:
    for t in open_tours():
        if t["sid"] == sid:
            stop_tour(t["pid"])


def feedback_text(tour: dict, notes: list[dict], reason: str, seen: int, total: int) -> str:
    steps = tour.get("steps") or []
    head = f"[Recorrido] El usuario recorrió {seen} de {total} pasos"
    head += " y lo dio por terminado." if reason == "end" else " y cerró la ventana."
    if not notes:
        return head + " No dejó comentarios."
    lines = [head, "", "Sus comentarios (atiéndelos; si alguno es una pregunta, contéstala):"]
    for n in notes:
        st = steps[n["step"] - 1] if 0 < n.get("step", 0) <= len(steps) else {}
        lines.append(f"- Paso {n['step']} ({st.get('text', '')[:80]}; {n.get('url', '')}): {n['text']}")
    return "\n".join(lines)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")
