from __future__ import annotations
import asyncio
import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from ide_server.plugins import Registry
from ide_server.pty_manager import PtyManager
from ide_server.workspace import resolve_cwd


@dataclass
class TerminalHooks:
    spawn: Callable[..., str]
    kill: Callable[[str], None]


def register(registry: Registry, root: Path, manager, pty: PtyManager | None = None) -> TerminalHooks:
    pty = pty or PtyManager()
    terms: dict[str, dict] = {}                 # tid -> {sessionId, cmd, cwd}

    def _attach(tid: str, on_exit: Callable[[], None] | None = None,
                on_output: Callable[[bytes], None] | None = None) -> None:
        loop = asyncio.get_running_loop()
        fd = pty.fd(tid)

        def _emit(data: bytes) -> None:
            loop.create_task(manager.broadcast(
                f"terminal.data.{tid}", {"data": base64.b64encode(data).decode()}))
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
                pty.reap(tid)                                 # cierra el fd; el pid ya se cosechó
                loop.create_task(manager.broadcast(f"terminal.exit.{tid}", {}))
                if on_exit is not None:
                    on_exit()

        loop.add_reader(fd, _on_readable)

    def spawn_process(cwd: Path, argv: list[str], env: dict[str, str],
                      on_exit: Callable[[], None], session_id: str | None = None,
                      on_output: Callable[[bytes], None] | None = None,
                      on_input: Callable[[], None] | None = None) -> str:
        tid = pty.spawn(cwd, argv, env=env)
        terms[tid] = {"sessionId": session_id, "cmd": argv, "cwd": str(cwd),
                      "on_input": on_input}
        _attach(tid, on_exit, on_output)
        return tid

    def kill_process(tid: str) -> None:
        if tid in pty.list_ids():               # ya cosechado/desconocido: no-op
            try:
                asyncio.get_running_loop().remove_reader(pty.fd(tid))
            except (OSError, ValueError, KeyError, RuntimeError):
                pass
        pty.close(tid)
        terms.pop(tid, None)

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
        on_input = terms.get(payload["id"], {}).get("on_input")
        if on_input is not None:
            on_input()
        return {"ok": True}

    async def resize_(payload: dict) -> dict:
        pty.resize(payload["id"], int(payload["cols"]), int(payload["rows"]))
        return {"ok": True}

    async def close_(payload: dict) -> dict:
        kill_process(payload["id"])
        return {"ok": True}

    registry.register("terminal.open", open_)
    registry.register("terminal.list", list_)
    registry.register("terminal.write", write_)
    registry.register("terminal.resize", resize_)
    registry.register("terminal.close", close_)

    # compartido con Tasks 4-5 (write/resize/close + streaming) vía cierre:
    register._pty = pty        # type: ignore[attr-defined]
    register._terms = terms    # type: ignore[attr-defined]
    register._manager = manager  # type: ignore[attr-defined]
    return TerminalHooks(spawn=spawn_process, kill=kill_process)
