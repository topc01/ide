# server/ide_server/supervisor.py
from __future__ import annotations
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable
from ide_server.sessions_fs import SessionError, session_path, read_toml, update_session_toml

log = logging.getLogger(__name__)

SpawnFn = Callable[..., str]   # (cwd, argv, env, on_exit, *, on_output, on_input) -> tid
KillFn = Callable[[str], None]

# Claude Code pide confirmar la carpeta (o el modo bypass) la primera vez: la sesión queda
# esperando y ocupa un cupo. Lo detectamos en el inicio de la salida (sin ANSI ni espacios,
# porque el TUI a veces reemplaza espacios por movimientos de cursor).
ATTENTION_HEAD = 8192
_ANSI_RE = re.compile(rb"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
_CTRL_RE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]")
_TRUST_NEEDLES = ("trustthefiles", "doyoutrust", "bypasspermissionsmode")


def _flat(head: bytes) -> str:
    return re.sub(r"\s+", "", _ANSI_RE.sub(b"", head).decode("utf-8", "replace")).lower()


def needs_trust(head: bytes) -> bool:
    text = _flat(head)
    return any(n in text for n in _TRUST_NEEDLES)


# `claude --continue` se niega si la conversación sigue viva en segundo plano (el daemon de
# Claude Code la conserva cuando muere el PTY, p.ej. al reiniciar el server).
def says_backgrounded(head: bytes) -> bool:
    return "isrunninginthebackground" in _flat(head)


# Marcadores que Claude Code pone en el entorno de sus procesos hijos. Si el server corre
# dentro de una sesión de claude, cada sesión los heredaría: claude se cree sesión hija,
# no guarda historial ("Transcript saving is off") y no se puede retomar.
PARENT_CLAUDE_ENV = (
    "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_CODE_EXECPATH", "CLAUDE_PID", "CLAUDE_EFFORT",
)


def clean_env(base: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in base.items() if k not in PARENT_CLAUDE_ENV}


class ClaudeAgents:
    """Sesiones de claude en segundo plano (`claude agents|stop`), por carpeta de sesión."""

    def __init__(self, command: str, run=subprocess.run) -> None:
        self._cmd, self._run = shlex.split(command), run

    def background(self, cwd: Path) -> list[dict]:
        """Sesiones de fondo en esa carpeta: {id (de `claude attach`), sessionId, name}."""
        try:
            out = self._run([*self._cmd, "agents", "--json", "--cwd", str(cwd)],
                            capture_output=True, text=True, timeout=10, env=clean_env(dict(os.environ)))
            items = json.loads(out.stdout or "[]") if out.returncode == 0 else []
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            log.warning("no se pudo consultar `claude agents`: %s", exc)
            return []
        here = str(cwd.resolve())
        return [a for a in items
                if a.get("kind") == "background" and a.get("id")
                and str(Path(a.get("cwd", "")).resolve()) == here]

    def stop(self, agent_id: str) -> None:
        try:
            self._run([*self._cmd, "stop", agent_id], capture_output=True, timeout=10,
                      env=clean_env(dict(os.environ)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("no se pudo detener la sesión de fondo %s: %s", agent_id, exc)


def encode_project_dir(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _transcripts(path: Path, home: Path) -> list[Path]:
    d = home / ".claude" / "projects" / encode_project_dir(path.resolve())
    return list(d.glob("*.jsonl")) if d.is_dir() else []


def has_history(path: Path, home: Path) -> bool:
    return bool(_transcripts(path, home))


def latest_transcript_id(path: Path, home: Path) -> str | None:
    """La conversación que elegiría `claude --continue` (la más reciente de la carpeta)."""
    files = _transcripts(path, home)
    return max(files, key=lambda f: f.stat().st_mtime).stem if files else None


def _positional(prompt: str) -> str:
    return " " + prompt if prompt.startswith("-") else prompt   # que claude no lo lea como flag


def build_argv(root: Path, sid: str, *, command: str, resume: bool,
               claude_session: str | None = None, claude_name: str | None = None,
               prompt: str | None = None) -> list[str]:
    path = session_path(root, sid)
    data = read_toml(path / ".session.toml")
    perm, kind = data.get("permissions", "default"), data.get("kind")
    argv = shlex.split(command)
    if perm in ("analyze", "full"):
        profile = "main" if (kind == "main" and perm == "analyze") else perm
        argv += ["--settings", str(root / ".ide" / "permissions" / f"{profile}.json")]
    if perm == "full":
        argv += ["--permission-mode", "bypassPermissions"]
    # `--add-dir` es variádico en claude: con `=` no se come el prompt posicional.
    argv.append(f"--add-dir={root / '.ide' / 'worktrees' / sid}")
    if kind == "main":
        argv.append(f"--add-dir={root / '.ide' / 'sessions'}")
    if claude_name:
        argv += ["--name", claude_name]
    if resume:
        argv += ["--resume", claude_session] if claude_session else ["--continue"]
        if prompt:
            argv.append(_positional(prompt))
    else:
        if claude_session:
            argv += ["--session-id", claude_session]
        prompt_file = path / "PROMPT.md"
        prompt = prompt or (prompt_file.read_text(encoding="utf-8").strip()
                            if prompt_file.is_file() else "")
        if prompt:
            argv.append(_positional(prompt))
    return argv


class Supervisor:
    """Dueño único de los procesos `claude` de las sesiones-carpeta."""

    def __init__(self, root: Path, *, spawn: SpawnFn, kill: KillFn, server_url: str,
                 command: str = "claude", max_running: int | None = None,
                 home: Path | None = None, on_change: Callable[[], None] | None = None,
                 which: Callable[[str], str | None] = shutil.which,
                 agents: ClaudeAgents | None = None,
                 write: Callable[[str, bytes], None] | None = None) -> None:
        self._root, self._spawn, self._kill = root, spawn, kill
        self._url, self._command, self._max = server_url, command, max_running
        self._home = home or Path.home()
        self._on_change = on_change or (lambda: None)
        self._which = which
        self._agents = agents            # None = no mirar sesiones de fondo (tests)
        self._write = write
        self._running: dict[str, str] = {}
        self._queue: list[tuple[str, bool]] = []
        self._errors: dict[str, str] = {}
        self._head: dict[str, bytes] = {}           # sid -> inicio de la salida del proceso
        self._attention: dict[str, str] = {}        # sid -> "trust"

    def state(self, sid: str) -> str:
        if sid in self._running:
            return "running"
        if any(q == sid for q, _ in self._queue):
            return "queued"
        return "stopped"

    def snapshot(self) -> dict[str, dict]:
        sids = set(self._running) | {q for q, _ in self._queue} | set(self._errors)
        return {sid: {"process": self.state(sid), "terminalId": self._running.get(sid),
                      "launchError": self._errors.get(sid),
                      "attention": self._attention.get(sid)} for sid in sids}

    def start(self, sid: str, *, resume: bool | None = None, prompt: str | None = None) -> str:
        path = session_path(self._root, sid)
        if not (path / ".session.toml").is_file():
            raise SessionError("unknown_session", f"no existe la sesión {sid}")
        if self.state(sid) != "stopped":
            return self.state(sid)
        if resume is None:
            resume = has_history(path, self._home)
        if self._max is not None and len(self._running) >= self._max:
            if prompt:
                raise SessionError("queue_full", f"hay {self._max} sesiones corriendo (max_running): "
                                                 f"no puedo lanzar {sid} con el prompt ahora")
            self._queue.append((sid, resume))
            self._on_change()
            return "queued"
        self._launch(sid, resume, prompt)
        self._on_change()
        return "running"

    def stop(self, sid: str) -> None:
        self._queue = [(q, r) for q, r in self._queue if q != sid]
        self._errors.pop(sid, None)
        tid = self._running.pop(sid, None)
        self._forget(sid)
        if tid is not None:
            self._kill(tid)
            self._drain()
        if self._agents is not None:     # matar el PTY deja viva la sesión en el daemon de claude
            threading.Thread(target=self._stop_background, args=(session_path(self._root, sid),),
                             daemon=True).start()
        self._on_change()

    def _stop_background(self, path: Path) -> None:
        for _ in range(5):               # el daemon tarda un poco en registrarla como de fondo
            time.sleep(1)
            for a in self._agents.background(path):
                self._agents.stop(a["id"])

    def send(self, sid: str, text: str) -> None:
        """Escribe `text` en el input del `claude` que corre y lo envía (Enter)."""
        tid = self._running.get(sid)
        if tid is None or self._write is None:
            raise SessionError("not_running", f"la sesión {sid} no está corriendo")
        # sin caracteres de control (salvo \n): el texto trae datos de GitHub (p.ej. el título del
        # PR) y un \r o un ESC se leerían como teclas en el TUI de claude
        clean = _CTRL_RE.sub("", text.replace("\r\n", "\n").replace("\t", " "))
        body = clean.rstrip().split("\n")
        self._write(tid, "\x1b\r".join(body).encode())   # Alt+Enter = salto de línea en claude
        # el Enter aparte: pegado junto al texto, claude lo toma como parte del paste
        threading.Timer(0.4, lambda: self._running.get(sid) == tid and self._write(tid, b"\r")).start()

    def _launch(self, sid: str, resume: bool, prompt: str | None = None) -> None:
        path = session_path(self._root, sid)
        # Cada sesión fija su conversación de claude (`claude_session` en .session.toml): nueva
        # con --session-id, retomada con --resume <id>. Las viejas adoptan la más reciente.
        # `claude_name` (--name con un token aleatorio) marca los claude que lanzó el IDE: el
        # daemon, al pasar una sesión a segundo plano, la bifurca con otro sessionId.
        data = read_toml(path / ".session.toml")
        cs, name = data.get("claude_session"), data.get("claude_name")
        if not cs or not name:
            cs = cs or (latest_transcript_id(path, self._home) if resume else None) or str(uuid.uuid4())
            name = name or f"{sid} · {uuid.uuid4().hex[:8]}"
            update_session_toml(self._root, sid, lambda d: d.update(claude_session=cs, claude_name=name))
        argv = build_argv(self._root, sid, command=self._command, resume=resume,
                          claude_session=cs, claude_name=name, prompt=prompt)
        if resume and self._agents is not None:
            # sigue viva en segundo plano (p.ej. tras reiniciar el server): reengancharla, pero
            # SOLO si la lanzó el IDE (una lanzada a mano podría tener otros permisos)
            mine = [a["id"] for a in self._agents.background(path)
                    if a.get("sessionId") == cs or a.get("name") == name]
            if mine:
                argv = [*shlex.split(self._command), "attach", mine[0]]
                if prompt:   # `attach` no recibe prompt: se escribe cuando el TUI ya cargó
                    threading.Timer(3.0, lambda: sid in self._running and self.send(sid, prompt)).start()
        if self._which(argv[0]) is None:
            raise SessionError("claude_missing",
                               f"no se encontró `{argv[0]}` en el PATH (¿instalaste claude?)")
        (self._root / ".ide" / "worktrees" / sid).mkdir(parents=True, exist_ok=True)  # --add-dir
        env = {**clean_env(dict(os.environ)), "IDE_SESSION_ID": sid, "IDE_URL": self._url,
               "IDE_WORKSPACE": str(self._root)}
        holder: dict[str, str] = {}
        tid = self._spawn(session_path(self._root, sid), argv, env,
                          lambda: self._on_exit(sid, holder.get("tid")),
                          on_output=lambda data: self._on_output(sid, holder.get("tid"), data),
                          on_input=lambda: self._on_input(sid, holder.get("tid")))
        holder["tid"] = tid
        self._forget(sid)
        self._running[sid] = tid
        self._errors.pop(sid, None)

    def _forget(self, sid: str) -> None:
        self._head.pop(sid, None)
        self._attention.pop(sid, None)

    def _on_output(self, sid: str, tid: str | None, data: bytes) -> None:
        if tid is None or self._running.get(sid) != tid or sid in self._attention:
            return
        head = self._head.get(sid, b"")
        if len(head) >= ATTENTION_HEAD:
            return
        head = (head + data)[:ATTENTION_HEAD]
        self._head[sid] = head
        if needs_trust(head):
            self._attention[sid] = "trust"
            self._on_change()

    def _on_input(self, sid: str, tid: str | None) -> None:
        """El usuario escribió en la terminal: asumimos que respondió el diálogo."""
        if tid is not None and self._running.get(sid) == tid and \
                self._attention.pop(sid, None) is not None:
            self._head[sid] = b""         # seguir mirando: puede venir otro diálogo (bypass)
            self._on_change()

    def _on_exit(self, sid: str, tid: str | None) -> None:
        if tid is None or self._running.get(sid) != tid:
            return
        del self._running[sid]
        if says_backgrounded(self._head.get(sid, b"")):
            self._errors[sid] = ("claude dice que la conversación sigue en segundo plano y no se "
                                 "pudo reenganchar: revisa `claude agents` (attach o stop)")
        self._forget(sid)
        self._drain()
        self._on_change()

    def _drain(self) -> None:
        while self._queue and (self._max is None or len(self._running) < self._max):
            sid, resume = self._queue.pop(0)
            try:
                self._launch(sid, resume)
            except Exception as exc:  # un fallo no debe trabar la cola ni quedar silencioso
                self._errors[sid] = str(exc) or type(exc).__name__
