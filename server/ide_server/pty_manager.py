from __future__ import annotations
import fcntl
import os
import pty
import select
import signal
import struct
import termios
import uuid
from pathlib import Path


class PtyManager:
    def __init__(self) -> None:
        self._terms: dict[str, dict] = {}

    def spawn(self, cwd: Path, argv: list[str]) -> str:
        tid = uuid.uuid4().hex[:12]
        pid, fd = pty.fork()
        if pid == 0:                            # hijo: stdio ya es el slave pty
            try:
                os.chdir(str(cwd))
            except OSError:
                pass
            try:
                os.execvp(argv[0], argv)
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

    def write(self, tid: str, data: bytes) -> None:
        os.write(self._terms[tid]["fd"], data)

    def resize(self, tid: str, cols: int, rows: int) -> None:
        fd = self._terms[tid]["fd"]
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def is_alive(self, tid: str) -> bool:
        t = self._terms.get(tid)
        if not t:
            return False
        try:
            wpid, _ = os.waitpid(t["pid"], os.WNOHANG)
            return wpid == 0
        except OSError:
            return False

    def close(self, tid: str) -> None:
        t = self._terms.pop(tid, None)
        if not t:
            return
        try:
            os.kill(t["pid"], signal.SIGKILL)
            os.waitpid(t["pid"], 0)             # reap: evita zombie
        except OSError:
            pass
        try:
            os.close(t["fd"])
        except OSError:
            pass

    def fd(self, tid: str) -> int:
        return self._terms[tid]["fd"]

    def list_ids(self) -> list[str]:
        return list(self._terms)
