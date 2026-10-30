# server/ide_server/merge_all.py
"""«Mergear todo» de un desarrollo: saca de draft todas sus PRs y las mergea en orden, de abajo hacia
arriba en cada stack y respetando las dependencias entre repos (`## Dependencias` / `ide dep`), a medida
que pasan el CI y quedan aprobadas. Cada PR la mergea `Merger` (squash, rebase solo si hace falta,
chequeo de migraciones, restack de las de arriba); stacks independientes avanzan en paralelo.

Si el CI de una PR falla, se le avisa a la sesión del desarrollo (una vez por commit) para que lo arregle
y suba: el desarrollo espera y sigue solo cuando el CI pasa. Se **detiene** (card en rojo + aviso a la
sesión) si a una PR le piden cambios o su merge falla (conflicto que no se resolvió solo, migraciones);
el usuario lo reanuda desde la card. El trabajo vive en la base (`mergeall:<clave del desarrollo>`)."""
from __future__ import annotations
import asyncio
import json
import logging
import subprocess
import threading
from datetime import datetime
from typing import Callable
from ide_server.db import Db
from ide_server.sessions_fs import SessionError

log = logging.getLogger(__name__)
ACTIVE_MERGE = {"rebasing", "waiting", "waiting_ci", "merging", "restacking"}
TICK = 20


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class MergeAll:
    def __init__(self, db: Db, merger, stacks: Callable[[], dict], on_change: Callable[[], None]) -> None:
        self._db, self._merger, self._stacks, self._on_change = db, merger, stacks, on_change
        self._lock = threading.RLock()
        # le habla a la sesión de un desarrollo (lo conecta folder_sessions): (clave, título, texto)
        self.tell: Callable[[str, str, str], None] = lambda _key, _title, _text: None
        self.on_done: Callable[[str, list[str]], None] = lambda _key, _urls: None

    # -- estado -------------------------------------------------------------------------------------
    def _jobs(self) -> dict[str, dict]:
        return dict(self._db.with_prefix("mergeall:"))

    def _save(self, key: str, job: dict) -> None:
        self._db.set(f"mergeall:{key}", job)

    def public(self) -> dict[str, dict]:
        return {k: {f: j.get(f) for f in ("state", "total", "done", "error", "current", "waiting", "at")}
                for k, j in self._jobs().items() if j.get("state") != "dismissed"}

    def _cards(self) -> dict[str, dict]:
        st = self._stacks() or {}
        return {c["url"]: c for lst in [*(st.get("mine") or {}).values(), *(st.get("stacks") or {}).values()]
                for c in lst}

    # -- acciones -----------------------------------------------------------------------------------
    def start(self, key: str, urls: list[str]) -> dict:
        me = (self._stacks() or {}).get("me")
        cards = self._cards()
        mine = [u for u in dict.fromkeys(urls) if u in cards and cards[u].get("author") == f"@{me}"]
        if not mine:
            raise SessionError("no_prs", "el desarrollo no tiene PRs tuyas abiertas para mergear")
        if (self._jobs().get(key) or {}).get("state") == "running":
            raise SessionError("merge_pending", "ya se está mergeando este desarrollo")
        drafts = [u for u in mine if cards[u].get("draft")]
        failed = []
        for u in drafts:                          # 1. todas fuera de draft (el CI corre apenas puede)
            out = subprocess.run(["gh", "pr", "ready", u], capture_output=True, text=True, timeout=60)
            if out.returncode != 0:
                failed.append(f"{u}: {out.stderr.strip()}")
        job = {"state": "running", "urls": mine, "total": len(mine), "done": 0, "error": None, "current": [],
               "waiting": None, "ci_told": {}, "at": _now()}
        self._save(key, job)
        self._db.event(_now(), "ide", "merge-all", dev=key[2:] if key.startswith("s:") else None,
                       data={"prs": mine, "undrafted": len(drafts) - len(failed)})
        if failed:
            log.warning("merge-all %s: no pude sacar de draft %s", key, failed)
        self._on_change()
        return self.public()[key]

    def resume(self, key: str) -> None:
        job = self._jobs().get(key)
        if not job or job.get("state") not in ("stopped", "error"):
            raise SessionError("no_merge", "no hay un «Mergear todo» detenido para reanudar")
        for u in job["urls"]:                   # el merge de una PR que falló: se reintenta
            if (self._merger.jobs.get(u) or {}).get("state") == "error":
                try:
                    self._merger.retry(u)
                except SessionError:
                    pass
        self._save(key, {**job, "state": "running", "error": None})
        self._on_change()

    def stop(self, key: str) -> None:
        job = self._jobs().get(key)
        if not job:
            raise SessionError("no_merge", "no hay un «Mergear todo» en este desarrollo")
        self._save(key, {**job, "state": "stopped", "error": "detenido por ti"})
        self._on_change()

    def dismiss(self, key: str) -> None:
        self._db.delete(f"mergeall:{key}")
        self._on_change()

    # -- el vigilante -------------------------------------------------------------------------------
    def _halt(self, key: str, job: dict, why: str, *, tell: bool = True) -> None:
        self._save(key, {**job, "state": "error", "error": why})
        self._db.event(_now(), "ide", "merge-all-stopped", dev=key[2:] if key.startswith("s:") else None,
                       data={"why": why})
        if tell:
            self.tell(key, "«Mergear todo» se detuvo", f"[Aviso del IDE] «Mergear todo» de tu desarrollo se detuvo: {why}. "
                      "Si lo puedes arreglar tú (sin cambiar el comportamiento), arréglalo y súbelo, y dile al usuario que lo "
                      "reanude desde la card; si no, pregúntale qué hacer. Cuéntale en una línea qué hiciste.")

    def _ci_failure(self, url: str) -> str:
        out = subprocess.run(["gh", "pr", "checks", url, "--json", "name,state,link"], capture_output=True, text=True, timeout=60)
        try:
            bad = [c for c in json.loads(out.stdout or "[]") if c.get("state") in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED")]
        except ValueError:
            bad = []
        return "; ".join(f"{c['name']} ({c.get('link') or 'sin link'})" for c in bad[:3]) or "ver los checks de la PR"

    def tick(self) -> None:
        cards = self._cards()
        for key, job in self._jobs().items():
            if job.get("state") != "running":
                continue
            with self._lock:
                self._tick_one(key, job, cards)
        self._on_change()

    def _tick_one(self, key: str, job: dict, cards: dict[str, dict]) -> None:
        remaining = [u for u in job["urls"] if u in cards]
        active = [u for u in job["urls"] if (self._merger.jobs.get(u) or {}).get("state") in ACTIVE_MERGE]
        job = {**job, "done": len(job["urls"]) - len(remaining), "current": active}
        if not remaining and not active:
            self._save(key, {**job, "state": "done", "waiting": None})
            self._db.event(_now(), "ide", "merge-all-done", dev=key[2:] if key.startswith("s:") else None)
            self.on_done(key, job["urls"])
            return
        ref = lambda c: f"{c['repo']}#{c['number']}"   # noqa: E731
        for u in remaining:
            c = cards[u]
            if c.get("review") == "changes":
                return self._halt(key, job, f"le pidieron cambios a {ref(c)}")
            mj = self._merger.jobs.get(u) or {}
            if mj.get("state") == "error":
                # el Merger ya le avisó a la sesión si fue un conflicto o las migraciones
                return self._halt(key, job, f"el merge de {ref(c)} falló: {mj.get('error')}",
                                  tell=not any(w in str(mj.get("error")) for w in ("conflicto", "migraciones")))
            sha = c.get("headSha") or c.get("updatedAt")
            if c.get("ci") == "failure" and job["ci_told"].get(u) != sha:     # una vez por commit
                job["ci_told"][u] = sha
                self.tell(key, f"El CI de {ref(c)} falló", f"[Aviso del IDE] «Mergear todo» está esperando: el CI de {ref(c)} "
                          f"falló ({self._ci_failure(u)}). Revisa el log; si lo puedes arreglar tú (un test, un lint, una "
                          "migración renumerada con `ide migrations renumber`) sin cambiar el comportamiento, arréglalo y "
                          "súbelo: el merge sigue solo cuando el CI pase. Si no, o si el arreglo cambia el comportamiento, "
                          "pregúntale al usuario. Cuéntale en una línea qué hiciste.")
        waiting = []
        for u in remaining:
            c = cards[u]
            if (self._merger.jobs.get(u) or {}).get("state") in ACTIVE_MERGE:
                continue
            if c.get("stack") and c["stack"].get("position", 1) != 1:
                continue                            # espera a que se mergeen las de abajo
            pend = [d for d in c.get("deps") or [] if d.get("state") != "MERGED" and not d.get("together")]
            if pend:
                waiting.append(f"{ref(c)} espera " + ", ".join(f"{d.get('repo')}#{d.get('number')}" for d in pend))
                continue
            if c.get("ci") == "failure":
                waiting.append(f"{ref(c)}: CI fallido (la sesión lo está viendo)")
                continue
            try:
                self._merger.merge(u)
            except SessionError as exc:
                if exc.code in ("ci_failed",):
                    waiting.append(f"{ref(c)}: {exc}")
                    continue
                return self._halt(key, job, f"no pude armar el merge de {ref(c)}: {exc}")
        self._save(key, {**job, "waiting": "; ".join(waiting) or None})

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), TICK)
            except asyncio.TimeoutError:
                pass
            try:
                await asyncio.to_thread(self.tick)
            except Exception:  # noqa: BLE001
                log.exception("«Mergear todo» falló; sigue en el próximo")
