# server/ide_server/updater.py
"""Auto-actualización bajo el supervisor de `ide run`: el server vigila su propio código instalado
y, cuando cambia (p.ej. `uv tool install --reinstall`), avisa a la UI y se reinicia cuando no hay
nadie escribiendo en una terminal **y ninguna sesión está trabajando** (reiniciar les cortaba el turno a medias), o
cuando lo piden («reiniciar ahora»). Sale con `RESTART_CODE` y el supervisor lo
relanza en el mismo puerto. Sin supervisor (`IDE_SUPERVISED` ausente) no hace nada."""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import signal
import time
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger(__name__)
RESTART_CODE = 75
SUPERVISED_ENV = "IDE_SUPERVISED"
CHECK_EVERY = 5         # s entre chequeos de la huella del código
IDLE_BEFORE = 60        # s sin teclas en ninguna terminal antes de reiniciar solo
PKG_DIR = Path(__file__).parent


def supervised() -> bool:
    return os.environ.get(SUPERVISED_ENV) == "1"


def fingerprint(pkg: Path = PKG_DIR) -> str:
    """Huella del código instalado (nombres, tamaños y mtimes de los .py y del index de la UI)."""
    h = hashlib.sha1()
    files = sorted([*pkg.rglob("*.py"), pkg / "web" / "index.html"])
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        h.update(f"{f.relative_to(pkg)}:{st.st_size}:{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


class Updater:
    def __init__(self, *, last_input: Callable[[], float], before_restart: Callable[[], None],
                 notify: Callable[[dict], Awaitable[None]], busy: Callable[[], int] | None = None) -> None:
        self._last_input, self._before, self._notify = last_input, before_restart, notify
        self._busy = busy or (lambda: 0)       # sesiones trabajando: reiniciar les corta el turno
        self._initial = fingerprint()
        self.pending = False
        self.restart_requested = False

    def status(self) -> dict:
        return {"pending": self.pending, "supervised": supervised(), "idleBefore": IDLE_BEFORE}

    def restart_now(self) -> None:
        """Cierra el server ordenadamente; el supervisor lo relanza con el código nuevo."""
        if not supervised():
            raise RuntimeError("el IDE no corre bajo el supervisor de `ide run`: reinícialo a mano")
        self.restart_requested = True
        try:
            self._before()                      # p.ej. guardar el historial de las terminales
        except Exception:  # noqa: BLE001
            log.exception("antes de reiniciar")
        os.kill(os.getpid(), signal.SIGTERM)    # uvicorn hace el shutdown ordenado

    async def run(self, stop: asyncio.Event) -> None:
        if not supervised():
            return
        seen = self._initial
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), CHECK_EVERY)
                return
            except asyncio.TimeoutError:
                pass
            fp = await asyncio.to_thread(fingerprint)
            if fp != seen:                      # todavía se está instalando: esperar a que pare
                seen = fp
                continue
            if fp != self._initial and not self.pending:
                self.pending = True
                log.info("hay una versión nueva del IDE: se reinicia cuando no haya nadie escribiendo")
                await self._notify(self.status())
            if self.pending and time.time() - self._last_input() >= IDLE_BEFORE and not self._busy():
                self.restart_now()
                return
