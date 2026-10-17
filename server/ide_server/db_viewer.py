# server/ide_server/db_viewer.py
"""Visor de la base de un desarrollo (pgweb), detrás del server del IDE.

Por cada worktree con base (su `.env` tiene `POSTGRES_NAME`) se levanta un `pgweb` en 127.0.0.1, en un
puerto libre, con usuario/clave de basic auth aleatorios que solo conoce el IDE, y con el prefijo
`db/<lugar>/<repo>`. La UI lo abre por `/db/<lugar>/<repo>/` (proxy del IDE, con sus chequeos de
origen): pgweb no tiene auth propia y si quedara expuesto, cualquier página podría mandarle SQL."""
from __future__ import annotations
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote
from ide_server.repos_fs import worktree_path
from ide_server.sessions_fs import SessionError, require_plain_name

DOCKER_HOSTS = {"db", "postgres", "host.docker.internal", ""}


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k.strip().removeprefix("export ").strip()] = v
    return out


def db_conf(wt: Path) -> dict | None:
    """Conexión desde el host a la base del worktree (la del `.env`; `.env.local` pisa)."""
    env = {**read_env(wt / ".env"), **read_env(wt / ".env.local")}
    name = env.get("POSTGRES_NAME") or env.get("POSTGRES_DB")
    if not name:
        return None
    host = env.get("POSTGRES_HOST", "")
    return {"name": name, "user": env.get("POSTGRES_USER", "postgres"), "password": env.get("POSTGRES_PASSWORD", ""),
            "host": "127.0.0.1" if host in DOCKER_HOSTS else host, "port": env.get("POSTGRES_PORT") or "5432"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DbViewer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._procs: dict[str, dict] = {}       # "<lugar>/<repo>" -> {proc, port, auth, db}
        self._lock = threading.Lock()

    def _wt(self, place: str, repo: str) -> Path:
        require_plain_name(place, "lugar")
        require_plain_name(repo, "repo")
        wt = worktree_path(self.root, place, repo)
        if not wt.is_dir():
            raise SessionError("unknown_worktree", f"no hay worktree de {repo} en {place}")
        return wt

    def list(self, place: str) -> list[dict]:
        base = self.root / ".ide" / "worktrees" / require_plain_name(place, "lugar")
        out = []
        for wt in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
            c = db_conf(wt)
            if c:
                out.append({"repo": wt.name, "name": c["name"], "running": f"{place}/{wt.name}" in self._procs})
        return out

    def open(self, place: str, repo: str) -> dict:
        if shutil.which("pgweb") is None:
            raise SessionError("pgweb_missing", "falta pgweb: brew install pgweb")
        conf = db_conf(self._wt(place, repo))
        if conf is None:
            raise SessionError("no_db", f"el .env de {repo} en {place} no dice qué base usa (POSTGRES_NAME)")
        key = f"{place}/{repo}"
        with self._lock:
            cur = self._procs.get(key)
            if cur and cur["proc"].poll() is None and cur["db"] == conf:
                return {"path": f"/db/{key}/", "name": conf["name"]}
            if cur:
                self._kill(cur)
            port, user, pw = _free_port(), "ide", secrets.token_urlsafe(24)
            url = (f"postgres://{quote(conf['user'], safe='')}:{quote(conf['password'], safe='')}@"
                   f"{conf['host']}:{conf['port']}/{quote(conf['name'], safe='')}?sslmode=disable")
            # la conexión y la clave van por entorno (no quedan a la vista en `ps`)
            env = {**os.environ, "PGWEB_DATABASE_URL": url, "PGWEB_AUTH_USER": user, "PGWEB_AUTH_PASS": pw,
                   "PGWEB_URL_PREFIX": f"db/{key}"}
            proc = subprocess.Popen(["pgweb", "--bind", "127.0.0.1", "--listen", str(port), "--skip-open",
                                     "--lock-session"], env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            for _ in range(50):                 # que esté escuchando antes de devolver
                if proc.poll() is not None:
                    err = proc.stderr.read().decode(errors="replace").strip() if proc.stderr else ""
                    raise SessionError("pgweb_failed", f"pgweb no arrancó: {err[-300:] or proc.returncode}")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            self._procs[key] = {"proc": proc, "port": port, "auth": (user, pw), "db": conf}
        return {"path": f"/db/{key}/", "name": conf["name"]}

    def target(self, key: str) -> tuple[int, tuple[str, str]] | None:
        cur = self._procs.get(key)
        if not cur or cur["proc"].poll() is not None:
            return None
        return cur["port"], cur["auth"]

    @staticmethod
    def _kill(cur: dict) -> None:
        try:
            cur["proc"].terminate()
            cur["proc"].wait(timeout=5)
        except Exception:  # noqa: BLE001
            cur["proc"].kill()

    def close_all(self) -> None:
        with self._lock:
            for cur in self._procs.values():
                self._kill(cur)
            self._procs.clear()
