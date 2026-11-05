"""¿De dónde viene una llamada HTTP local? Para los comandos que se permiten «desde tu terminal» (sin token de la
manager): un comando que corre dentro del IDE (el claude de una sesión, una terminal de una sesión, o algo que
lanzaron) no cuenta como tu terminal aunque no diga de qué sesión viene.

Se busca el proceso dueño del otro extremo de la conexión (`lsof`) y se revisa:
- que ningún ancestro sea el server (todo lo que el IDE lanza cuelga de él);
- que tenga una terminal (tty) y que no sea una de las del IDE (un proceso que se desprendió de su padre igual
  conserva la tty de la sesión);
- sin tty (un proceso desprendido y sin terminal) no se le cree.
Es una barrera, no aislamiento: una sesión que corre cualquier comando corre con tu usuario."""
from __future__ import annotations
import os
import subprocess


def _ps() -> dict[int, tuple[int, str]]:
    out = subprocess.run(["ps", "-Ao", "pid=,ppid=,tty="], capture_output=True, text=True, timeout=10).stdout
    procs: dict[int, tuple[int, str]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            procs[int(parts[0])] = (int(parts[1]), parts[2] if len(parts) > 2 else "??")
    return procs


def _owner(port: int) -> int | None:
    """El pid local dueño de la conexión cuyo puerto de origen es `port` (no el server)."""
    out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:ESTABLISHED", "-Fpn"],
                         capture_output=True, text=True, timeout=10).stdout
    me, pid = os.getpid(), None
    for line in out.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid and pid != me and f":{port}->" in line:
            return pid
    return None


def caller_is_ide(port: int | None, claude_pids: set[int] | None = None,
                  user_pids: set[int] | None = None) -> tuple[bool, str]:
    """(True, por qué) si la llamada viene de algo que corre dentro del IDE o no se puede saber de dónde.
    Lo que cuelga del claude de una sesión es de esa sesión; lo que cuelga de una terminal que el usuario abrió
    en la UI (módulo Terminal) es del usuario, aunque esa terminal la haya abierto el IDE."""
    if not port:
        return True, "no sé de dónde viene la llamada"
    try:
        pid = _owner(port)
        procs = _ps()
    except (OSError, subprocess.SubprocessError, ValueError):
        return True, "no pude ver qué proceso llama"
    if pid is None or pid not in procs:
        return True, "no encontré el proceso que llama"
    server = os.getpid()
    chain = _ancestors(pid, procs)
    if claude_pids and chain & claude_pids:
        return True, "corre dentro del claude de una sesión"
    if user_pids and chain & user_pids:
        return False, ""
    # las terminales que abrió el IDE (no la del propio server, que es la de la ventana donde corriste `ide run`)
    ide_ttys = {tty for p, (pp, tty) in procs.items()
                if p != server and tty not in ("??", "", procs.get(server, (0, ""))[1]) and _descends(p, server, procs)}
    tty = procs[pid][1]
    if _descends(pid, server, procs):
        return True, "corre dentro del IDE (una sesión o una terminal del IDE)"
    if tty in ("??", ""):
        return True, "no corre en una terminal"
    if tty in ide_ttys:
        return True, "corre en una terminal del IDE"
    return False, ""


def _ancestors(pid: int, procs: dict[int, tuple[int, str]]) -> set[int]:
    out = set()
    while pid and pid not in out:
        out.add(pid)
        pid = procs.get(pid, (0, ""))[0]
    return out


def _descends(pid: int, ancestor: int, procs: dict[int, tuple[int, str]]) -> bool:
    seen = set()
    while pid and pid not in seen:
        if pid == ancestor:
            return True
        seen.add(pid)
        pid = procs.get(pid, (0, ""))[0]
    return False
