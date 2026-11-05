from __future__ import annotations
import fcntl
import os
import pty
import select
import signal
import struct
import termios
import threading
import uuid
from pathlib import Path


class PtyManager:
    def __init__(self) -> None:
        self._terms: dict[str, dict] = {}

    def spawn(self, cwd: Path, argv: list[str], env: dict[str, str] | None = None) -> str:
        tid = uuid.uuid4().hex[:12]
        pid, fd = pty.fork()
        if pid == 0:                            # hijo: stdio ya es el slave pty
            try:
                os.chdir(str(cwd))
            except OSError:
                pass
            try:
                if env is None:
                    os.execvp(argv[0], argv)
                else:
                    os.execvpe(argv[0], argv, env)
            except OSError:
                os._exit(127)                   # execvp falló (comando inexistente)
        self._terms[tid] = {"pid": pid, "fd": fd}
        return tid

    def read(self, tid: str, timeout: float = 0.0) -> bytes:
        fd = self._terms[tid]["fd"]
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            return b""
        try:
            return os.read(fd, 65536)
        except OSError:
            return b""                          # EOF / fd cerrado

    def write(self, tid: str, data: bytes, timeout: float = 10.0) -> None:
        """Escribe TODO `data`. El buffer de entrada de una terminal en macOS es de ~1 KB y el fd puede
        quedar no bloqueante (el loop lo vigila): `os.write` escribe una parte y el resto se perdía
        (un paste largo llegaba cortado). Se sigue escribiendo a medida que el programa lee."""
        fd = self._terms[tid]["fd"]
        view, deadline = memoryview(data), None
        while view:
            try:
                n = os.write(fd, view)
            except BlockingIOError:
                n = 0
            view = view[n:]
            if view:
                import time
                deadline = deadline or time.monotonic() + timeout
                if time.monotonic() > deadline:
                    raise TimeoutError(f"la terminal no acepta más entrada ({len(view)} bytes sin escribir)")
                select.select([], [fd], [], 0.05)

    def resize(self, tid: str, cols: int, rows: int) -> None:
        fd = self._terms[tid]["fd"]
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def is_alive(self, tid: str) -> bool:
        t = self._terms.get(tid)
        if not t:
            return False
        if t.get("reaped"):
            return False
        try:
            wpid, status = os.waitpid(t["pid"], os.WNOHANG)
        except OSError:
            wpid, status = t["pid"], None       # ya no es hijo nuestro: tratarlo como cosechado
        if wpid == 0:
            return True
        t["reaped"] = True                      # el pid quedó libre: nunca más le mandamos señales
        if status is not None:
            t["code"] = os.waitstatus_to_exitcode(status)
        return False

    def exit_code(self, tid: str) -> int | None:
        """Código de salida de un proceso que ya terminó (negativo = murió por esa señal)."""
        return (self._terms.get(tid) or {}).get("code")

    def reap(self, tid: str) -> None:
        """Libera un proceso que ya terminó solo: cierra el fd sin mandar señales."""
        t = self._terms.pop(tid, None)
        if t:
            self._close_fd(t)

    def close(self, tid: str) -> None:
        t = self._terms.pop(tid, None)
        if not t:
            return
        if not t.get("reaped"):
            try:
                os.kill(t["pid"], signal.SIGKILL)
                if os.waitpid(t["pid"], os.WNOHANG)[0] == 0:
                    # Todavía no murió (p. ej. trabado saliendo en el kernel): cosecharlo en un hilo.
                    # Un waitpid bloqueante acá congela el event loop y con él todo el server.
                    threading.Thread(target=self._reap_blocking, args=(t["pid"],), daemon=True).start()
            except OSError:
                pass
        self._close_fd(t)

    @staticmethod
    def _reap_blocking(pid: int) -> None:
        try:
            os.waitpid(pid, 0)                  # reap: evita zombie
        except OSError:
            pass

    @staticmethod
    def _close_fd(t: dict) -> None:
        try:
            os.close(t["fd"])
        except OSError:
            pass

    def signal_group(self, tid: str, sig: int) -> None:
        """Una señal a todo el grupo del proceso (pty.fork lo deja líder de su sesión: sus hijos, también)."""
        pid = self._terms[tid]["pid"]
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass

    def fd(self, tid: str) -> int:
        return self._terms[tid]["fd"]

    def list_ids(self) -> list[str]:
        return list(self._terms)
