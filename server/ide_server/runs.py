# server/ide_server/runs.py
"""Servidores: scripts por repo (`.ide/scripts/<repo>/<nombre>`) corriendo en un worktree como
procesos independientes del IDE (siguen vivos si el server se reinicia).

Cada corrida vive en `.ide/runs/<lugar>/<repo>/<nombre>/`: `log` (salida, se pisa en cada
arranque), `meta.json` (pid, cuándo, comando) y `exit` (código, lo escribe el wrapper al terminar).
`lugar` = id de la sesión, o `wt-<repo>-<n>` para el worktree de una PR sin sesión (ver
`pr_worktrees`). El proceso arranca en su propio grupo (`start_new_session`): parar = señal al grupo."""
from __future__ import annotations
import base64
import json
import os
import re
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from ide_server.repos_fs import worktree_path
from ide_server.scripts import script_argv, script_env
from ide_server.sessions_fs import SessionError, require_plain_name

LOG_TAIL = 1024 * 1024                          # primer pedido del log: lo último (1 MB)
LOG_CHUNK = 512 * 1024
STOP_GRACE = 15                                 # segundos entre SIGTERM y SIGKILL
_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):\d+/?")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# el wrapper anota el código de salida: así se sabe cómo terminó aunque el IDE se haya reiniciado
_WRAPPER = '"$@"; echo $? > "$IDE_RUN_EXIT"'


def runs_dir(root: Path) -> Path:
    return root / ".ide" / "runs"


class Runner:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._children: dict[str, subprocess.Popen] = {}   # lanzados por este server (para cosecharlos)
        self._lock = threading.Lock()

    # -- rutas ---------------------------------------------------------------------------------
    def _dir(self, place: str, repo: str, name: str) -> Path:
        for v, what in ((place, "lugar"), (repo, "repo"), (name, "script")):
            require_plain_name(v, what)
        return runs_dir(self.root) / place / repo / name

    @staticmethod
    def _key(place: str, repo: str, name: str) -> str:
        return f"{place}/{repo}/{name}"

    # -- estado -------------------------------------------------------------------------------------
    def _alive(self, key: str, meta: dict) -> bool:
        child = self._children.get(key)
        if child is not None:
            if child.poll() is None:
                return True
            self._children.pop(key, None)
            return False
        pid = meta.get("pid")
        if not pid:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass
        # el pid pudo reusarse tras reiniciar la máquina: tiene que seguir siendo nuestro wrapper
        out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True)
        return meta.get("argv", [""])[0] in out.stdout

    def _status(self, d: Path, place: str, repo: str, name: str) -> dict:
        key = self._key(place, repo, name)
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        exit_file = d / "exit"
        code = None
        if exit_file.is_file():
            try:
                code = int(exit_file.read_text().strip() or "-1")
            except ValueError:
                code = -1
        if code is not None:
            state = "exited"
        elif self._alive(key, meta):
            state = "stopping" if meta.get("stopping") else "running"
        else:
            state = "stopped" if meta.get("stopping") else "lost"   # lost: murió sin anotar (kill -9, reboot)
        return {"place": place, "repo": repo, "name": name, "state": state, "exitCode": code,
                "pid": meta.get("pid"), "started": meta.get("started"), "ended": meta.get("ended"),
                "urls": self._urls(d)}

    @staticmethod
    def _urls(d: Path) -> list[str]:
        """URLs locales que el proceso anunció (las primeras distintas, p.ej. `API -> http://localhost:8001`)."""
        try:
            with open(d / "log", "rb") as f:
                head = f.read(256 * 1024).decode("utf-8", "replace")
        except OSError:
            return []
        seen: list[str] = []
        for m in _URL_RE.finditer(_ANSI_RE.sub("", head)):
            u = m.group(0).rstrip("/").replace("0.0.0.0", "localhost").replace("127.0.0.1", "localhost")
            if u not in seen:
                seen.append(u)
            if len(seen) == 4:
                break
        return seen

    def status(self, place: str, repo: str, name: str) -> dict:
        return self._status(self._dir(place, repo, name), place, repo, name)

    def list(self) -> list[dict]:
        base = runs_dir(self.root)
        out = []
        if not base.is_dir():
            return out
        for pd in sorted(p for p in base.iterdir() if p.is_dir()):
            for rd in sorted(p for p in pd.iterdir() if p.is_dir()):
                for nd in sorted(p for p in rd.iterdir() if p.is_dir()):
                    out.append(self._status(nd, pd.name, rd.name, nd.name))
        return out

    # -- acciones -----------------------------------------------------------------------------------
    def start(self, place: str, repo: str, name: str) -> dict:
        d = self._dir(place, repo, name)
        cwd = worktree_path(self.root, place, repo)
        if not cwd.is_dir():
            raise SessionError("unknown_worktree", f"no hay worktree de {repo} en {place}")
        argv = script_argv(self.root, repo, name)
        with self._lock:
            cur = self._status(d, place, repo, name) if d.is_dir() else None
            if cur and cur["state"] in ("running", "stopping"):
                raise SessionError("already_running", f"{repo}/{name} ya está corriendo en {place}")
            d.mkdir(parents=True, exist_ok=True)
            (d / "exit").unlink(missing_ok=True)
            env = script_env(self.root, place, repo)
            env.update(IDE_RUN_EXIT=str(d / "exit"), FORCE_COLOR="1", CLICOLOR_FORCE="1")
            with open(d / "log", "wb") as log:
                log.write(f"$ {repo}/{name}  ({cwd})\n".encode())
                log.flush()
                proc = subprocess.Popen(["/bin/sh", "-c", _WRAPPER, "sh", *argv], cwd=cwd, env=env,
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
            self._children[self._key(place, repo, name)] = proc
            (d / "meta.json").write_text(json.dumps({
                "pid": proc.pid, "argv": argv, "cwd": str(cwd),
                "started": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
        return self._status(d, place, repo, name)

    def stop(self, place: str, repo: str, name: str) -> dict:
        d = self._dir(place, repo, name)
        st = self._status(d, place, repo, name)
        if st["state"] != "running" or not st["pid"]:
            return st
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        meta["stopping"] = True
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        pid = st["pid"]
        try:
            os.killpg(pid, signal.SIGTERM)      # el grupo entero (docker compose, vite, sus hijos)
        except ProcessLookupError:
            pass
        threading.Thread(target=self._finish_stop, args=(d, place, repo, name, pid), daemon=True).start()
        return self._status(d, place, repo, name)

    def _finish_stop(self, d: Path, place: str, repo: str, name: str, pid: int) -> None:
        deadline = time.time() + STOP_GRACE
        key = self._key(place, repo, name)
        while time.time() < deadline:
            if not self._alive(key, {"pid": pid, "argv": [""]}) or self._dead_group(pid):
                break
            time.sleep(0.5)
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            meta["ended"] = datetime.now().isoformat(timespec="seconds")
            (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        except (OSError, ValueError):
            pass

    @staticmethod
    def _dead_group(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def stop_place(self, place: str, repo: str | None = None, wait: float = STOP_GRACE + 2) -> None:
        """Para todo lo que corre en un lugar (o en un repo de él) antes de archivar/borrar, y espera."""
        running = [r for r in self.list() if r["place"] == place and (repo is None or r["repo"] == repo)
                   and r["state"] in ("running", "stopping")]
        for r in running:
            self.stop(place, r["repo"], r["name"])
        deadline = time.time() + wait
        while time.time() < deadline and any(
                self.status(place, r["repo"], r["name"])["state"] in ("running", "stopping") for r in running):
            time.sleep(0.5)

    def log(self, place: str, repo: str, name: str, offset: int) -> dict:
        """Bytes del log desde `offset` (-1 = lo último). `reset` = el log se reescribió (corrida nueva)."""
        f = self._dir(place, repo, name) / "log"
        try:
            size = f.stat().st_size
        except FileNotFoundError:
            return {"data": "", "end": 0, "reset": offset > 0}
        reset = offset > size
        if offset < 0 or reset:
            offset = max(0, size - LOG_TAIL)
        with open(f, "rb") as fh:
            fh.seek(offset)
            data = fh.read(min(size - offset, LOG_CHUNK))
        return {"data": base64.b64encode(data).decode(), "end": offset + len(data), "reset": reset}
