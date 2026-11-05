from __future__ import annotations
import asyncio
import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from ide_server.plugins import Registry
from ide_server.pty_manager import PtyManager
from ide_server.workspace import resolve_cwd

REPLAY_BYTES = 2 * 1024 * 1024
RESTART_MARK = b"\r\n\x1b[2m-- el IDE se reinicio: lo de arriba es de antes del reinicio --\x1b[0m\r\n"


@dataclass
class TerminalHooks:
    spawn: Callable[..., str]
    kill: Callable[[str], None]
    write: Callable[[str, bytes], None] | None = None
    last_input: Callable[[], float] | None = None   # cuándo se tecleó por última vez (cualquier terminal)
    save_history: Callable[[], None] | None = None  # persiste el historial de las terminales con clave
    signal: Callable[[str, int], None] | None = None  # señal al grupo del proceso (congelar / soltar)


def register(registry: Registry, root: Path, manager, pty: PtyManager | None = None) -> TerminalHooks:
    pty = pty or PtyManager()
    terms: dict[str, dict] = {}                 # tid -> {sessionId, cmd, cwd}
    # Lo último que imprimió cada terminal (y cuántos bytes lleva en total): una terminal que se
    # abre en el navegador con el proceso ya corriendo arranca con esto en vez de vacía.
    history: dict[str, bytearray] = {}
    emitted: dict[str, int] = {}
    # Terminales con `persist_key` (el `claude` de cada sesión): su historial se guarda en disco y
    # sobrevive a un reinicio del server (al relanzarse arranca con lo de antes).
    hist_dir = root / ".ide" / "terminals"
    saved: dict[str, int] = {}                  # tid -> `emitted` cuando se guardó
    state = {"last_input": 0.0}

    def _hist_file(key: str) -> Path:
        return hist_dir / f"{key}.log"

    def save_history() -> None:
        for tid, t in list(terms.items()):
            key = t.get("persist_key")
            if not key or saved.get(tid) == emitted.get(tid):
                continue
            hist_dir.mkdir(parents=True, exist_ok=True)
            _hist_file(key).write_bytes(bytes(history.get(tid, b"")))
            saved[tid] = emitted.get(tid, 0)

    def _attach(tid: str, on_exit: Callable[[], None] | None = None,
                on_output: Callable[[bytes], None] | None = None) -> None:
        loop = asyncio.get_running_loop()
        fd = pty.fd(tid)

        def _emit(data: bytes) -> None:
            buf = history.setdefault(tid, bytearray())
            buf += data
            if len(buf) > REPLAY_BYTES:
                del buf[:len(buf) - REPLAY_BYTES]
            emitted[tid] = emitted.get(tid, 0) + len(data)
            loop.create_task(manager.broadcast(
                f"terminal.data.{tid}", {"data": base64.b64encode(data).decode(), "end": emitted[tid]}))
            if on_output is not None:
                on_output(data)

        def _on_readable() -> None:
            data = pty.read(tid, timeout=0.0)
            if data:
                _emit(data)
            if not pty.is_alive(tid):
                try:
                    loop.remove_reader(fd)
                except (OSError, ValueError):
                    pass
                while data := pty.read(tid, timeout=0.0):     # lo que quedó en el buffer
                    _emit(data)
                code = pty.exit_code(tid)                     # que la pantalla diga cómo terminó
                _emit(f"\r\n\x1b[2m[terminó: exit {code if code is not None else '?'}]\x1b[0m\r\n".encode())
                pty.reap(tid)                                 # cierra el fd; el pid ya se cosechó
                if key := terms.get(tid, {}).get("persist_key"):  # terminó solo: no es un reinicio
                    _hist_file(key).unlink(missing_ok=True)
                    saved.pop(tid, None)
                loop.create_task(manager.broadcast(f"terminal.exit.{tid}", {}))
                if on_exit is not None:
                    on_exit()

        loop.add_reader(fd, _on_readable)

    def spawn_process(cwd: Path, argv: list[str], env: dict[str, str],
                      on_exit: Callable[[], None], session_id: str | None = None,
                      on_output: Callable[[bytes], None] | None = None,
                      on_input: Callable[[], None] | None = None,
                      persist_key: str | None = None) -> str:
        tid = pty.spawn(cwd, argv, env=env)
        terms[tid] = {"sessionId": session_id, "cmd": argv, "cwd": str(cwd),
                      "on_input": on_input, "persist_key": persist_key}
        if persist_key and _hist_file(persist_key).is_file():   # viene de un reinicio del server
            old = _hist_file(persist_key).read_bytes()[-REPLAY_BYTES:]
            history[tid] = bytearray(old + RESTART_MARK)
            emitted[tid] = len(history[tid])
        _attach(tid, on_exit, on_output)
        return tid

    def kill_process(tid: str) -> None:
        if tid in pty.list_ids():               # ya cosechado/desconocido: no-op
            try:
                asyncio.get_running_loop().remove_reader(pty.fd(tid))
            except (OSError, ValueError, KeyError, RuntimeError):
                pass
        key = terms.get(tid, {}).get("persist_key")
        pty.close(tid)
        terms.pop(tid, None)
        history.pop(tid, None)
        emitted.pop(tid, None)
        saved.pop(tid, None)
        if key:                                 # se paró a propósito: no es un reinicio del server
            _hist_file(key).unlink(missing_ok=True)

    async def open_(payload: dict) -> dict:
        cwd = resolve_cwd(root, payload)
        cmd = payload.get("cmd") or [os.environ.get("SHELL", "/bin/zsh")]
        tid = pty.spawn(cwd, cmd)
        terms[tid] = {"sessionId": payload.get("sessionId"), "cmd": cmd, "cwd": str(cwd)}
        _attach(tid)
        return {"id": tid, "cwd": str(cwd)}

    async def list_(payload: dict) -> dict:
        sid = payload.get("sessionId")
        out = [{"id": tid, "cmd": t["cmd"], "alive": pty.is_alive(tid)}
               for tid, t in terms.items() if t["sessionId"] == sid]
        return {"terminals": out}

    async def write_(payload: dict) -> dict:
        pty.write(payload["id"], base64.b64decode(payload["data"]))
        state["last_input"] = time.time()
        on_input = terms.get(payload["id"], {}).get("on_input")
        if on_input is not None:
            on_input()
        return {"ok": True}

    async def replay_(payload: dict) -> dict:
        """Lo último impreso por la terminal y hasta qué byte (`end`): el cliente escribe esto y
        después solo los eventos con `end` mayor (sin perder ni duplicar)."""
        buf = bytes(history.get(payload["id"], b""))
        nl = buf.find(b"\n") if len(buf) >= REPLAY_BYTES else -1
        if nl != -1:                            # recortado: empezar en una línea entera
            buf = buf[nl + 1:]
        return {"data": base64.b64encode(buf).decode(), "end": emitted.get(payload["id"], 0)}

    async def resize_(payload: dict) -> dict:
        pty.resize(payload["id"], int(payload["cols"]), int(payload["rows"]))
        return {"ok": True}

    async def close_(payload: dict) -> dict:
        kill_process(payload["id"])
        return {"ok": True}

    registry.register("terminal.open", open_)
    registry.register("terminal.list", list_)
    registry.register("terminal.write", write_)
    registry.register("terminal.replay", replay_)
    registry.register("terminal.resize", resize_)
    registry.register("terminal.close", close_)

    # compartido con Tasks 4-5 (write/resize/close + streaming) vía cierre:
    register._pty = pty        # type: ignore[attr-defined]
    register._terms = terms    # type: ignore[attr-defined]
    register._manager = manager  # type: ignore[attr-defined]
    return TerminalHooks(spawn=spawn_process, kill=kill_process, write=pty.write,
                         last_input=lambda: state["last_input"], save_history=save_history,
                         signal=pty.signal_group)
