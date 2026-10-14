# server/ide_server/supervisor.py
from __future__ import annotations
import os
import re
import shlex
import shutil
from pathlib import Path
from typing import Callable
from ide_server.sessions_fs import SessionError, session_path, read_toml

SpawnFn = Callable[[Path, list[str], dict[str, str], Callable[[], None]], str]
KillFn = Callable[[str], None]


def encode_project_dir(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def has_history(path: Path, home: Path) -> bool:
    d = home / ".claude" / "projects" / encode_project_dir(path.resolve())
    return d.is_dir() and any(d.glob("*.jsonl"))


def build_argv(root: Path, sid: str, *, command: str, resume: bool) -> list[str]:
    path = session_path(root, sid)
    perm = read_toml(path / ".session.toml").get("permissions", "default")
    argv = shlex.split(command)
    if perm in ("analyze", "full"):
        argv += ["--settings", str(root / ".ide" / "permissions" / f"{perm}.json")]
    if perm == "full":
        argv += ["--permission-mode", "bypassPermissions"]
    if resume:
        argv.append("--continue")
    else:
        prompt_file = path / "PROMPT.md"
        prompt = prompt_file.read_text(encoding="utf-8").strip() if prompt_file.is_file() else ""
        if prompt:
            argv.append(prompt)
    return argv


class Supervisor:
    """Dueño único de los procesos `claude` de las sesiones-carpeta."""

    def __init__(self, root: Path, *, spawn: SpawnFn, kill: KillFn, server_url: str,
                 command: str = "claude", max_running: int | None = None,
                 home: Path | None = None, on_change: Callable[[], None] | None = None,
                 which: Callable[[str], str | None] = shutil.which) -> None:
        self._root, self._spawn, self._kill = root, spawn, kill
        self._url, self._command, self._max = server_url, command, max_running
        self._home = home or Path.home()
        self._on_change = on_change or (lambda: None)
        self._which = which
        self._running: dict[str, str] = {}
        self._queue: list[tuple[str, bool]] = []
        self._errors: dict[str, str] = {}

    def state(self, sid: str) -> str:
        if sid in self._running:
            return "running"
        if any(q == sid for q, _ in self._queue):
            return "queued"
        return "stopped"

    def snapshot(self) -> dict[str, dict]:
        sids = set(self._running) | {q for q, _ in self._queue} | set(self._errors)
        return {sid: {"process": self.state(sid), "terminalId": self._running.get(sid),
                      "launchError": self._errors.get(sid)} for sid in sids}

    def start(self, sid: str, *, resume: bool | None = None) -> str:
        path = session_path(self._root, sid)
        if not (path / ".session.toml").is_file():
            raise SessionError("unknown_session", f"no existe la sesión {sid}")
        if self.state(sid) != "stopped":
            return self.state(sid)
        if resume is None:
            resume = has_history(path, self._home)
        if self._max is not None and len(self._running) >= self._max:
            self._queue.append((sid, resume))
            self._on_change()
            return "queued"
        self._launch(sid, resume)
        self._on_change()
        return "running"

    def stop(self, sid: str) -> None:
        self._queue = [(q, r) for q, r in self._queue if q != sid]
        self._errors.pop(sid, None)
        tid = self._running.pop(sid, None)
        if tid is not None:
            self._kill(tid)
            self._drain()
        self._on_change()

    def _launch(self, sid: str, resume: bool) -> None:
        argv = build_argv(self._root, sid, command=self._command, resume=resume)
        if self._which(argv[0]) is None:
            raise SessionError("claude_missing",
                               f"no se encontró `{argv[0]}` en el PATH (¿instalaste claude?)")
        env = {**os.environ, "IDE_SESSION_ID": sid, "IDE_URL": self._url,
               "IDE_WORKSPACE": str(self._root)}
        holder: dict[str, str] = {}
        tid = self._spawn(session_path(self._root, sid), argv, env,
                          lambda: self._on_exit(sid, holder.get("tid")))
        holder["tid"] = tid
        self._running[sid] = tid
        self._errors.pop(sid, None)

    def _on_exit(self, sid: str, tid: str | None) -> None:
        if tid is None or self._running.get(sid) != tid:
            return
        del self._running[sid]
        self._drain()
        self._on_change()

    def _drain(self) -> None:
        while self._queue and (self._max is None or len(self._running) < self._max):
            sid, resume = self._queue.pop(0)
            try:
                self._launch(sid, resume)
            except Exception as exc:  # un fallo no debe trabar la cola ni quedar silencioso
                self._errors[sid] = str(exc) or type(exc).__name__
