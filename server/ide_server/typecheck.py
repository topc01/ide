# server/ide_server/typecheck.py
"""`ide typecheck [<repo>] [--build]`: el chequeo de tipos del proyecto entero (`npm run type-check` = `vue-tsc
--noEmit`) o el build (`npm run build`, que también corre `vue-tsc`), **de a uno entre todas las sesiones** y con tope
de memoria. Cada uno se come varios GB (el del embed, ~6 GB): dos a la vez, más todo lo demás, llenaron la memoria de
la Mac (19-11). El hook frena `vue-tsc`, `npm run type-check` y `npm run build` sueltos y manda acá.

- Candado global (`~/.cache/ide/typecheck.lock`, `flock`): el que llega después espera (hasta `WAIT` s) y dice de quién
  es el que corre.
- `NODE_OPTIONS=--max-old-space-size=MAX_MB` (reemplaza el que traiga el entorno: no se puede subir)."""
from __future__ import annotations
import fcntl
import json
import os
import subprocess
import time
from pathlib import Path
from typing import TextIO

from ide_server.repos_fs import require_session
from ide_server.sessions_fs import SessionError, repo_links

LOCK = Path.home() / ".cache" / "ide" / "typecheck.lock"
MAX_MB = 4096
WAIT = 30 * 60
RUN_TIMEOUT = 20 * 60


def _scripts(wt: Path) -> dict:
    try:
        return json.loads((wt / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError):
        return {}


def run(root: Path, sid: str, repo: str | None, *, build: bool, out: TextIO) -> int:
    links = {p.name: p.resolve() for p in repo_links(require_session(root, sid))}
    script = "build" if build else "type-check"
    fronts = [n for n, wt in links.items() if script in _scripts(wt)]
    if repo is None:
        if len(fronts) != 1:
            raise SessionError("which_repo", f"dime el repo: `ide typecheck <repo>` (con `{script}`: {', '.join(fronts) or 'ninguno'})")
        repo = fronts[0]
    if repo not in links:
        raise SessionError("unknown_repo", f"la sesión {sid} no tiene {repo} (tiene: {', '.join(links) or 'ninguno'})")
    wt = links[repo]
    if script not in _scripts(wt):
        raise SessionError("no_script", f"{repo} no tiene el script `{script}` en su package.json")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK, "a+")
    start = time.time()
    told = False
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if not told:
                fh.seek(0)
                who = fh.read().strip() or "otra sesión"
                out.write(f"hay otro chequeo de tipos corriendo ({who}): espero a que termine (uno a la vez, para no "
                          f"llenar la memoria)…\n")
                out.flush()
                told = True
            if time.time() - start > WAIT:
                raise SessionError("busy", f"el otro chequeo sigue después de {WAIT // 60} min: vuelve a intentarlo")
            time.sleep(3)
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(f"sesión {sid}, {repo}, desde las {time.strftime('%H:%M')}")
        fh.flush()
        env = {**os.environ, "NODE_OPTIONS": f"--max-old-space-size={MAX_MB}"}
        out.write(f"{repo}: npm run {script} (tope {MAX_MB // 1024} GB)…\n")
        out.flush()
        try:
            r = subprocess.run(["npm", "run", "-s", script], cwd=wt, env=env, capture_output=True, text=True,
                               timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise SessionError("timeout", f"`npm run {script}` pasó de {RUN_TIMEOUT // 60} min: lo corté")
        text = (r.stdout + r.stderr).strip()
        if "heap out of memory" in text or "JavaScript heap" in text:
            out.write(f"{text[-3000:]}\nse quedó sin memoria con el tope de {MAX_MB // 1024} GB: avísale al usuario "
                      f"(no lo subas)\n")
            return 1
        out.write((text[-20000:] + "\n") if text else "")
        out.write(f"{repo}: {'sin errores' if r.returncode == 0 else f'con errores (exit {r.returncode})'}\n")
        return r.returncode
    finally:
        fh.seek(0)
        fh.truncate()
        fh.flush()
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()
