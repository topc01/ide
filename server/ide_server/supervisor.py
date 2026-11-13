# server/ide_server/supervisor.py
from __future__ import annotations
import json
from datetime import datetime
import logging
import os
import re
import shlex
import secrets
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable
from ide_server.config import reviews_config
from ide_server.sessions_fs import SessionError, session_cwd, session_path, read_toml, update_session_toml

log = logging.getLogger(__name__)

# lo que imprime claude al interrumpir un turno (Esc / Ctrl+C)
INTERRUPT_MARKS = (b"What should Claude do instead", b"Interrupted by user")
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


def install_skills(root: Path, session_dir: Path) -> None:
    """Skills del IDE (`.ide/skills/*`, p.ej. /backlog) en la sesión principal: se copian a su
    `.claude/skills/` (skills de proyecto del cwd de su claude) en cada lanzamiento."""
    manager = root / ".ide" / "manager.md"    # su rol: manager de los desarrollos (su CLAUDE.md)
    if manager.is_file():
        shutil.copyfile(manager, session_dir / "CLAUDE.md")
    src = root / ".ide" / "skills"
    if not src.is_dir():
        return
    for skill in src.iterdir():
        if (skill / "SKILL.md").is_file():
            shutil.copytree(skill, session_dir / ".claude" / "skills" / skill.name, dirs_exist_ok=True)


def enable_plugins(session_dir: Path, plugins: list[str]) -> None:
    """Plugins por sesión: `.claude/settings.json` en la carpeta de la sesión (el cwd de su
    `claude`) es config de proyecto, así que solo esa sesión los carga."""
    if not plugins:
        return
    f = session_dir / ".claude" / "settings.json"
    data = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SessionError("bad_settings", f"{f} no es JSON válido: {exc}") from exc
    wanted = {**data.get("enabledPlugins", {}), **{p: True for p in plugins}}
    if wanted != data.get("enabledPlugins"):
        f.parent.mkdir(exist_ok=True)
        f.write_text(json.dumps({**data, "enabledPlugins": wanted}, indent=2) + "\n", encoding="utf-8")


HOOK_EVENTS = ("UserPromptSubmit", "Stop", "Notification")


def install_hooks(session_dir: Path) -> None:
    """Hooks de Claude Code en `.claude/settings.json` de la sesión: `ide hook` le avisa al IDE cuándo
    claude empieza un turno (trabajando), lo termina o pide un permiso (esperando tu input)."""
    f = session_dir / ".claude" / "settings.json"
    data = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SessionError("bad_settings", f"{f} no es JSON válido: {exc}") from exc
    hooks = dict(data.get("hooks") or {})
    ours = {"type": "command", "command": "ide hook", "timeout": 5}
    for ev in HOOK_EVENTS:
        groups = [g for g in hooks.get(ev) or []
                  if not any(h.get("command") == "ide hook" for h in g.get("hooks") or [])]
        hooks[ev] = groups + [{"hooks": [ours]}]
    # tests solo con permiso del usuario (ver test_guard): solo para Bash, sin pasar por el server
    groups = [g for g in hooks.get("PreToolUse") or []
              if not any(h.get("command") == "ide hook" for h in g.get("hooks") or [])]
    hooks["PreToolUse"] = groups + [{"matcher": "Bash", "hooks": [ours]}]
    if hooks != data.get("hooks"):
        f.parent.mkdir(exist_ok=True)
        f.write_text(json.dumps({**data, "hooks": hooks}, indent=2) + "\n", encoding="utf-8")


def build_argv(root: Path, sid: str, *, command: str, resume: bool,
               claude_session: str | None = None, claude_name: str | None = None,
               prompt: str | None = None) -> list[str]:
    path = session_path(root, sid)
    data = read_toml(path / ".session.toml")
    perm, kind = data.get("permissions", "default"), data.get("kind")
    argv = shlex.split(command)
    if isinstance(data.get("model"), str) and data["model"]:
        argv += ["--model", data["model"]]          # `ide session new --model` / `ide session model`
    if perm in ("analyze", "full"):
        profile = "main" if (kind == "main" and perm == "analyze") else perm
        argv += ["--settings", str(root / ".ide" / "permissions" / f"{profile}.json")]
    if perm == "full":
        argv += ["--permission-mode", "bypassPermissions"]
    if kind == "ide":
        # corre en el repo del IDE: los hooks de actividad van por --settings (no se escribe en el repo)
        hook = {"type": "command", "command": "ide hook", "timeout": 5}
        argv += ["--settings", json.dumps({"hooks": {ev: [{"hooks": [hook]}] for ev in HOOK_EVENTS}})]
    # `--add-dir` y `--mcp-config` son variádicos en claude: con `=` no se comen el prompt posicional.
    argv.append(f"--add-dir={root / '.ide' / 'worktrees' / sid}")
    from ide_server.browsers import allowed_tools, write_mcp_config
    # perfiles de navegador (`ide browser`); una sesión que no pide permisos no recibe los de cuentas REAL
    if (mcp := write_mcp_config(root, local_only=perm == "full")) is not None:
        argv.append(f"--mcp-config={mcp}")
        if tools := allowed_tools(root):
            argv.append(f"--allowedTools={','.join(tools)}")
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
                 write: Callable[[str, bytes], None] | None = None,
                 signal: Callable[[str, int], None] | None = None) -> None:
        # secreto de la principal para `ide session send`: solo en memoria y en el entorno de SU claude
        # (sin archivo: cualquier sesión podría leerlo). Al reiniciar el server los claude se relanzan
        # (sus PTY mueren con él), así que la principal recibe el nuevo.
        self.manager_token = secrets.token_urlsafe(32)
        # la sesión Plugins: responde por Telegram (`ide reply`) y le escribe solo a la sesión IDE (#93)
        self.plugins_token = secrets.token_urlsafe(32)
        self._root, self._spawn, self._kill = root, spawn, kill
        self._url, self._command, self._max = server_url, command, max_running
        self._home = home or Path.home()
        self._on_change = on_change or (lambda: None)
        self._which = which
        self._agents = agents            # None = no mirar sesiones de fondo (tests)
        self._write = write
        self._signal = signal
        self._frozen: dict[str, str] = {}           # sid -> desde cuándo está congelado (SIGSTOP)
        self._running: dict[str, str] = {}
        self._launched_at: dict[str, float] = {}   # cuándo se lanzó su claude (send espera a que arranque)
        self._send_lock = threading.Lock()   # dos envíos a la vez no se intercalan letra a letra
        self._queue: list[tuple[str, bool]] = []
        self._errors: dict[str, str] = {}
        self._head: dict[str, bytes] = {}           # sid -> inicio de la salida del proceso
        self._tail: dict[str, bytes] = {}           # sid -> lo último impreso (para ver una interrupción)
        # actividad de su claude (por los hooks): {state: working|waiting, since, note, reason}
        self._activity: dict[str, dict] = {}
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
                      "attention": self._attention.get(sid),
                      "activity": self._activity.get(sid) if sid in self._running else None,
                      "frozen": self._frozen.get(sid) if sid in self._running else None} for sid in sids}

    def set_activity(self, sid: str, state: str, note: str | None = None, reason: str | None = None) -> str | None:
        """Devuelve el estado anterior."""
        prev = (self._activity.get(sid) or {}).get("state")
        self._activity[sid] = {"state": state, "note": note, "reason": reason,
                               "since": datetime.now().isoformat(timespec="seconds")}
        self._on_change()
        return prev

    def start(self, sid: str, *, resume: bool | None = None, prompt: str | None = None) -> str:
        path = session_path(self._root, sid)
        if not (path / ".session.toml").is_file():
            raise SessionError("unknown_session", f"no existe la sesión {sid}")
        if self.state(sid) != "stopped":
            return self.state(sid)
        if resume is None:
            resume = has_history(session_cwd(self._root, sid), self._home)
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

    def snapshot_tids(self) -> list[str]:
        """Las terminales de los claude que corren (para saber si un comando viene de uno)."""
        return list(self._running.values())

    def freeze(self, sid: str, on: bool) -> None:
        """Congela (SIGSTOP) o suelta (SIGCONT) el claude de la sesión y todo lo que lanzó: deja de usar CPU y
        tokens al instante y sigue exactamente donde estaba; su memoria queda ocupada."""
        import signal as _sig
        tid = self._running.get(sid)
        if tid is None or self._signal is None:
            raise SessionError("not_running", f"la sesión {sid} no está corriendo")
        if on:
            self._signal(tid, _sig.SIGSTOP)
            self._frozen[sid] = datetime.now().isoformat(timespec="seconds")
        else:
            self._signal(tid, _sig.SIGCONT)
            self._frozen.pop(sid, None)
        self._on_change()

    def interrupt(self, sid: str) -> None:
        """Esc en su claude: corta el turno en curso (como cuando lo interrumpes a mano)."""
        tid = self._running.get(sid)
        if tid is not None and self._write is not None:
            if sid in self._frozen:
                self.freeze(sid, False)
            self._write(tid, b"\x1b")

    def stop(self, sid: str) -> None:
        tid_ = self._running.get(sid)
        if tid_ is not None and sid in self._frozen and self._signal is not None:
            import signal as _sig               # congelado no muere con SIGTERM/SIGHUP hasta que se suelta
            self._signal(tid_, _sig.SIGCONT)
        self._frozen.pop(sid, None)
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

    def press(self, sid: str, key: bytes) -> None:
        """Una tecla en la terminal del `claude` que corre (Enter = aceptar el permiso, Esc = rechazarlo)."""
        tid = self._running.get(sid)
        if tid is None or self._write is None:
            raise SessionError("not_running", f"la sesión {sid} no está corriendo")
        with self._send_lock:
            self._write(tid, key)

    def send(self, sid: str, text: str, *, escape_first: bool = False) -> None:
        """Escribe `text` en el input del `claude` que corre y lo envía (Enter). `escape_first`: antes aprieta
        Esc (cierra un permiso o una pregunta con opciones pendientes) y espera a que vuelva el input."""
        tid = self._running.get(sid)
        if tid is None or self._write is None:
            raise SessionError("not_running", f"la sesión {sid} no está corriendo")
        # sin caracteres de control (salvo \n): el texto trae datos de GitHub (p.ej. el título del
        # PR) y un \r o un ESC se leerían como teclas en el TUI de claude
        clean = _CTRL_RE.sub("", text.replace("\r\n", "\n").replace("\t", " "))
        body = clean.rstrip().split("\n")
        # de a poco, como tipeado: escrito de un golpe, claude se queda solo con el final de un texto
        # largo. Alt+Enter (\x1b\r) = salto de línea en claude; nunca se parte entre dos escrituras.
        tokens = [t for i, line in enumerate(body) for t in ([*line] if i == 0 else ["\x1b\r", *line])]
        chunks = ["".join(tokens[i:i + 64]) for i in range(0, len(tokens), 64)]

        def type_it() -> None:
            # recién lanzado: claude todavía no muestra su input (o pregunta si confías en la carpeta, en una
            # sesión nueva). Lo tipeado ahí se pierde o responde el diálogo: se espera a que esté listo (hasta 10 min)
            start = time.time()
            while time.time() - start < 600 and self._running.get(sid) == tid:
                launched = self._launched_at.get(sid, 0)
                if sid not in self._attention and time.time() - launched >= 6:
                    break
                time.sleep(0.5)
            with self._send_lock:
                if escape_first:
                    self._write(tid, b"\x1b")
                    time.sleep(1.0)
                for c in chunks:
                    if self._running.get(sid) != tid:
                        return
                    self._write(tid, c.encode())
                    time.sleep(0.01)
                # el Enter aparte: pegado junto al texto, claude lo toma como parte del paste
                time.sleep(0.4)
                if self._running.get(sid) == tid:
                    self._write(tid, b"\r")
        threading.Thread(target=type_it, daemon=True).start()

    def paste(self, sid: str, text: str) -> None:
        """Pega `text` en el input de su claude como un paste de terminal (sin Enter): así una ruta a
        una imagen entra como adjunto ([Image #n]), igual que arrastrar un archivo a la terminal."""
        tid = self._running.get(sid)
        if tid is None or self._write is None:
            raise SessionError("not_running", f"la sesión {sid} no está corriendo")
        clean = _CTRL_RE.sub("", text.replace("\r", " ").replace("\n", " "))
        self._write(tid, b"\x1b[200~" + clean.encode() + b"\x1b[201~")

    def _launch(self, sid: str, resume: bool, prompt: str | None = None) -> None:
        path = session_path(self._root, sid)
        # Cada sesión fija su conversación de claude (`claude_session` en .session.toml): nueva
        # con --session-id, retomada con --resume <id>. Las viejas adoptan la más reciente.
        # `claude_name` (--name con un token aleatorio) marca los claude que lanzó el IDE: el
        # daemon, al pasar una sesión a segundo plano, la bifurca con otro sessionId.
        data = read_toml(path / ".session.toml")
        if data.get("kind") == "review":
            enable_plugins(path, list(reviews_config(self._root)["plugins"]))
        if data.get("kind") == "main":
            install_skills(self._root, path)
        cwd = session_cwd(self._root, sid, data)
        if data.get("kind") != "ide":
            install_hooks(path)
        cs, name = data.get("claude_session"), data.get("claude_name")
        if not cs or not name:
            cs = cs or (latest_transcript_id(cwd, self._home) if resume else None) or str(uuid.uuid4())
            name = name or f"{sid} · {uuid.uuid4().hex[:8]}"
            update_session_toml(self._root, sid, lambda d: d.update(claude_session=cs, claude_name=name))
        argv = build_argv(self._root, sid, command=self._command, resume=resume,
                          claude_session=cs, claude_name=name, prompt=prompt)
        if resume and self._agents is not None:
            # sigue viva en segundo plano (p.ej. tras reiniciar el server): reengancharla, pero
            # SOLO si la lanzó el IDE (una lanzada a mano podría tener otros permisos)
            mine = [a["id"] for a in self._agents.background(cwd)
                    if a.get("sessionId") == cs or a.get("name") == name]
            if mine:
                argv = [*shlex.split(self._command), "attach", mine[0]]
                if prompt:   # `attach` no recibe prompt: se escribe cuando el TUI ya cargó
                    threading.Timer(3.0, lambda: sid in self._running and self.send(sid, prompt)).start()
        if self._which(argv[0]) is None:
            raise SessionError("claude_missing",
                               f"no se encontró `{argv[0]}` en el PATH (¿instalaste claude?)")
        (self._root / ".ide" / "worktrees" / sid).mkdir(parents=True, exist_ok=True)  # --add-dir
        from ide_server.devs import dev_env   # el claude de la sesión sabe su número (ramas, slugs)
        env = {**clean_env(dict(os.environ)), **dev_env(self._root, sid), "IDE_SESSION_ID": sid, "IDE_URL": self._url,
               # solo la principal: con esto `ide session send` prueba que es ella (ver sessions.send)
               **({"IDE_MANAGER_TOKEN": self.manager_token} if data.get("kind") == "main" else {}),
               **({"IDE_PLUGINS_TOKEN": self.plugins_token} if data.get("kind") == "plugins" else {}),
               "IDE_WORKSPACE": str(self._root),
               # vitest usa un proceso por núcleo (11 en esta Mac, ~2,7 GB): como pytest, a lo más 2 (manda sobre la config)
               "VITEST_MAX_WORKERS": "2"}
        holder: dict[str, str] = {}
        tid = self._spawn(cwd, argv, env,
                          lambda: self._on_exit(sid, holder.get("tid")),
                          on_output=lambda data: self._on_output(sid, holder.get("tid"), data),
                          on_input=lambda: self._on_input(sid, holder.get("tid")),
                          persist_key=f"claude-{sid}")   # su pantalla sobrevive a un reinicio del server
        holder["tid"] = tid
        self._launched_at[sid] = time.time()
        self._forget(sid)
        self._running[sid] = tid
        # hasta el primer hook: con prompt trabaja; sin prompt queda en el input
        self._activity[sid] = {"state": "working" if prompt else "waiting", "note": None, "reason": "launch",
                               "since": datetime.now().isoformat(timespec="seconds")}
        if resume and not prompt:
            # retomada (p.ej. al reiniciar el IDE) sin nada que hacer: te esperaba desde su último mensaje, no
            # «recién abierta». El motivo y la nota salen de ese mensaje.
            try:
                self._activity[sid] = self._resumed_activity(cwd, cs) or self._activity[sid]
            except Exception:  # noqa: BLE001 — si no se puede leer, queda «recién abierta»
                log.exception("actividad al retomar %s", sid)
        self._errors.pop(sid, None)

    def _resumed_activity(self, cwd: Path, cs: str) -> dict | None:
        from ide_server import activity as activity_mod
        f = self._home / ".claude" / "projects" / encode_project_dir(cwd.resolve()) / f"{cs}.jsonl"
        det = activity_mod.detail(str(f), self._home, 0)
        if not det.get("message"):
            return None
        since = datetime.now()
        if det.get("messageAt"):
            since = datetime.fromisoformat(det["messageAt"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        asks = bool(activity_mod.questions_in(det["message"]))
        return {"state": "waiting", "note": activity_mod.first_line(det["message"]),
                "reason": "question" if asks else "turn", "since": since.isoformat(timespec="seconds")}

    def _forget(self, sid: str) -> None:
        self._head.pop(sid, None)
        self._attention.pop(sid, None)

    def _on_output(self, sid: str, tid: str | None, data: bytes) -> None:
        if tid is None or self._running.get(sid) != tid:
            return
        # interrumpido con Esc / Ctrl+C: claude no corre el hook Stop, así que la card se quedaba en
        # «trabajando». Lo que imprime el TUI al cortar el turno lo pasa a «te espera».
        # (solo en salidas chicas: un redibujo entero de la pantalla —al cambiar el tamaño— repite el texto viejo)
        if (self._activity.get(sid) or {}).get("state") == "working" and len(data) < 4096:
            tail = self._tail.get(sid, b"")[-64:] + data
            self._tail[sid] = tail[-64:]
            if any(m in tail for m in INTERRUPT_MARKS):
                self._tail[sid] = b""
                self.set_activity(sid, "waiting", note="Lo interrumpiste: espera qué hacer", reason="interrupt")
        if sid in self._attention:
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
        """El usuario escribió en la terminal: asumimos que respondió el diálogo (o el permiso)."""
        if (self._activity.get(sid) or {}).get("reason") == "permission":
            self.set_activity(sid, "working")
        if tid is not None and self._running.get(sid) == tid and \
                self._attention.pop(sid, None) is not None:
            self._head[sid] = b""         # seguir mirando: puede venir otro diálogo (bypass)
            self._on_change()

    def _on_exit(self, sid: str, tid: str | None) -> None:
        if tid is None or self._running.get(sid) != tid:
            return
        del self._running[sid]
        self._activity.pop(sid, None)
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
