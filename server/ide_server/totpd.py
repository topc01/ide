# server/ide_server/totpd.py
"""Guardián del código de verificación de Telegram (2FA): un proceso aparte, que **no se reinicia con el IDE**, lee
la clave del llavero una vez al arrancar (el llavero la guarda con confirmación: macOS te pregunta, y con «Permitir»
—no «Permitir siempre»— ninguna otra app la lee sin preguntarte) y la tiene solo en memoria. El IDE le pregunta por un
socket local si un código es correcto; la clave nunca sale de este proceso. Limita los intentos (un proceso que
pruebe códigos por el socket se bloquea igual).

Protocolo (una línea JSON por conexión): {"op": "verify", "code": "123456"} → {"ok": bool, "step": int|null};
{"op": "status"} → {"loaded": bool}; {"op": "reload"} → vuelve a leer el llavero."""
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

SOCK = Path.home() / ".ide-totp" / "sock"
MAX_FAILS, PER, LOCK = 5, 600, 3600       # 5 incorrectos en 10 min → 1 h sin aceptar


def _read_secret() -> str | None:
    from ide_server.telegram_guard import SERVICE
    out = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", "totp", "-w"],
                         capture_output=True, text=True, timeout=300)    # espera tu «Permitir»
    return out.stdout.strip() or None if out.returncode == 0 else None


class Daemon:
    def __init__(self) -> None:
        self.secret: str | None = None
        self.fails: list[float] = []
        self.locked = 0.0
        self.lock = threading.Lock()

    def load(self) -> None:
        self.secret = _read_secret()

    def handle(self, req: dict) -> dict:
        from ide_server.telegram_guard import totp
        import hmac
        op = req.get("op")
        if op == "status":
            return {"loaded": bool(self.secret), "locked": self.locked > time.time()}
        if op == "reload":                      # en otro hilo: espera tu «Permitir» sin trabar el socket
            threading.Thread(target=self.load, daemon=True).start()
            return {"loading": True}
        if op != "verify":
            return {"error": "op"}
        with self.lock:
            now = time.time()
            if self.locked > now or not self.secret:
                return {"ok": False, "step": None, "locked": self.locked > now}
            code = str(req.get("code") or "")
            for off in (-1, 0, 1):
                step, want = totp(self.secret, now, off)
                if hmac.compare_digest(want, code):
                    self.fails.clear()
                    return {"ok": True, "step": step}
            self.fails = [t for t in self.fails if now - t < PER] + [now]
            if len(self.fails) >= MAX_FAILS:
                self.locked, self.fails = now + LOCK, []
            return {"ok": False, "step": None, "locked": self.locked > now}


def serve() -> None:
    SOCK.parent.mkdir(mode=0o700, exist_ok=True)
    os.chmod(SOCK.parent, 0o700)
    try:
        SOCK.unlink()
    except FileNotFoundError:
        pass
    d = Daemon()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o077)                   # el socket nace solo para tu usuario
    try:
        srv.bind(str(SOCK))
    finally:
        os.umask(old)
    os.chmod(SOCK, 0o600)
    srv.listen(8)
    threading.Thread(target=d.load, daemon=True).start()   # el llavero pregunta: el socket ya responde mientras
    while True:
        conn, _ = srv.accept()
        try:
            conn.settimeout(5)
            data = b""
            while not data.endswith(b"\n") and len(data) < 512:
                chunk = conn.recv(512)
                if not chunk:
                    break
                data += chunk
            res = d.handle(json.loads(data or b"{}"))
            conn.sendall(json.dumps(res).encode() + b"\n")
        except Exception:  # noqa: BLE001 — una conexión mala no tumba al guardián
            pass
        finally:
            conn.close()


# -- cliente -------------------------------------------------------------------------------------------------
def _peer_is_guardian(c: socket.socket) -> bool:
    """Del otro lado del socket tiene que estar el guardián (este módulo, con el python del IDE), no algo que se puso en
    su lugar: se mira el proceso dueño de la conexión (LOCAL_PEERPID) y su línea de comando."""
    try:
        pid = c.getsockopt(0, 0x002, 4)          # SOL_LOCAL, LOCAL_PEERPID (macOS)
        pid = int.from_bytes(pid, sys.byteorder) if isinstance(pid, bytes) else int(pid)
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout.split()
    except (OSError, ValueError):
        return False
    # el python del framework de macOS se re-ejecuta como …/Python.app/…/Python: se mira que sea un python
    return len(cmd) >= 4 and Path(cmd[0]).name.lower().startswith("python") and cmd[1:4] == ["-I", "-m", "ide_server.totpd"]


def ask(req: dict, timeout: float = 5) -> dict | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(timeout)
            c.connect(str(SOCK))
            if sys.platform == "darwin" and not _peer_is_guardian(c):
                return None
            c.sendall(json.dumps(req).encode() + b"\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = c.recv(4096)
                if not chunk:
                    break
                data += chunk
        return json.loads(data)
    except (OSError, ValueError):
        return None


def ensure() -> None:
    """Lo arranca si no corre (aparte del IDE: sobrevive a sus reinicios)."""
    if ask({"op": "status"}, timeout=1) is not None:
        return
    # -I: sin el directorio actual ni variables PYTHON* en el camino de módulos (no carga código ajeno con acceso al llavero)
    subprocess.Popen([sys.executable, "-I", "-m", "ide_server.totpd"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True, cwd="/")


if __name__ == "__main__":
    serve()
