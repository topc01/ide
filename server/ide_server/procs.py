# server/ide_server/procs.py
"""`ide procs`: qué consume el computador y de qué desarrollo es, sin IA (lo usa la sesión Recursos y
el vigilante del server).

Junta `ps`, `docker ps/stats` y los servidores del IDE (`.ide/runs`) y los asocia a su lugar (sesión
o `wt-<repo>-<n>`) por el worktree: los contenedores por la etiqueta `working_dir` de compose. Cada
recurso del IDE se marca **abandonado** (se puede cortar sin preguntar) cuando:
- es un contenedor sin el servidor del IDE que lo levantó (huérfano),
- su sesión ya no existe (archivada) o su desarrollo está mergeado o pausado, o
- nadie lo usa hace `idle_hours`: ni el claude de su sesión (último cambio de su conversación) ni el
  servidor (último cambio de su log, que crece con cada request)."""
from __future__ import annotations
import json
import re
import subprocess
import time
from pathlib import Path
from ide_server.sessions_fs import read_toml, session_cwd, session_path

RECURSOS = "recursos"            # la sesión fija Recursos (pestaña junto a la manager y la IDE)
DEFAULTS = {"idle_hours": 12, "watch_seconds": 300, "cpu_alert": 150}
DONE = {"merged", "paused", "approved", "changes-requested", "closed"}


def config(root: Path) -> dict:
    """`[recursos]` de config.toml: `idle_hours`, `watch_seconds` (0 = no vigila), `cpu_alert` (% de CPU)."""
    from ide_server.config import load_workspace_config
    cfg = load_workspace_config(root).get("recursos", {})
    return {k: type(v)(cfg.get(k, v)) for k, v in DEFAULTS.items()}


def _run(argv: list[str], timeout: float = 30) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def processes() -> list[dict]:
    out = []
    for line in _run(["ps", "-Ao", "pid=,pgid=,pcpu=,rss=,etime=,command="]).splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6:
            pid, pgid, cpu, rss, etime, cmd = parts
            out.append({"pid": int(pid), "pgid": int(pgid), "cpu": float(cpu), "mb": int(rss) // 1024,
                        "etime": etime, "command": cmd})
    return out


def _mem_mb(s: str) -> int:
    m = re.match(r"([\d.]+)\s*([KMG]i?B)", s.split("/")[0].strip())
    if not m:
        return 0
    return int(float(m.group(1)) * {"K": 1 / 1024, "M": 1, "G": 1024}[m.group(2)[0]])


def containers() -> list[dict]:
    fmt = '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.project.working_dir"}}\t{{.RunningFor}}'
    rows = {}
    for line in _run(["docker", "ps", "--format", fmt], 20).splitlines():
        name, project, wd, since = (line.split("\t") + ["", "", ""])[:4]
        rows[name] = {"name": name, "project": project, "workdir": wd, "since": since, "cpu": 0.0, "mb": 0}
    if rows:
        for line in _run(["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"], 30).splitlines():
            name, cpu, mem = (line.split("\t") + ["", ""])[:3]
            if name in rows:
                rows[name]["cpu"] = float(cpu.rstrip("%") or 0)
                rows[name]["mb"] = _mem_mb(mem)
    return list(rows.values())


def battery() -> str:
    lines = _run(["pmset", "-g", "batt"], 5).splitlines()
    return lines[-1].split("\t", 1)[-1].strip() if len(lines) > 1 else ""


def _place_of(root: Path, path: str) -> tuple[str, str] | None:
    try:
        rel = Path(path).resolve().relative_to((root / ".ide" / "worktrees").resolve())
    except ValueError:
        return None
    return (rel.parts[0], rel.parts[1]) if len(rel.parts) >= 2 else None


def _last_claude(root: Path, sid: str, home: Path) -> float | None:
    """Cuándo cambió por última vez la conversación de claude de la sesión."""
    try:
        cwd = session_cwd(root, sid)
    except Exception:  # noqa: BLE001
        return None
    d = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9-]", "-", str(cwd))
    times = [f.stat().st_mtime for f in d.glob("*.jsonl")] if d.is_dir() else []
    return max(times) if times else None


def _place_info(root: Path, place: str, statuses: dict[str, str | None], home: Path) -> dict:
    if place.startswith("wt-"):
        return {"kind": "pr", "exists": True, "status": None, "lastClaude": None}
    toml = session_path(root, place) / ".session.toml"
    if not toml.is_file():
        return {"kind": None, "exists": False, "status": None, "lastClaude": None}
    data = read_toml(toml)
    return {"kind": data.get("kind"), "exists": True, "status": statuses.get(place) or data.get("status"),
            "lastClaude": _last_claude(root, place, home)}


def _hours(ts: float | None) -> float | None:
    return round((time.time() - ts) / 3600, 1) if ts else None


def snapshot(root: Path, *, home: Path | None = None, with_docker: bool = True) -> dict:
    from ide_server.db import Db
    from ide_server.runs import Runner, runs_dir
    home, root = home or Path.home(), root.resolve()
    cfg = config(root)
    statuses = {d["id"]: d["status"] for d in Db(root).devs()}
    procs = processes()
    by_pgid: dict[int, list[dict]] = {}
    for p in procs:
        by_pgid.setdefault(p["pgid"], []).append(p)
    infos: dict[str, dict] = {}

    def info(place: str) -> dict:
        if place not in infos:
            infos[place] = _place_info(root, place, statuses, home)
        return infos[place]

    def verdict(place: str, last_use: list[float | None]) -> str | None:
        """Por qué está abandonado (None = en uso)."""
        i = info(place)
        if not i["exists"]:
            return "su sesión ya no existe"
        if i["status"] in DONE:
            return f"el desarrollo está {i['status']}"
        if i["kind"] in ("main", "ide", "recursos", "plugins"):
            return None
        uses = [t for t in last_use if t]
        if uses and time.time() - max(uses) > cfg["idle_hours"] * 3600:
            return f"sin uso hace {_hours(max(uses))} h"
        return None

    servers, server_pgids = [], set()
    for r in Runner(root).list():
        if r["state"] not in ("running", "stopping"):
            continue
        group = by_pgid.get(r["pid"] or -1, [])
        log = runs_dir(root) / r["place"] / r["repo"] / r["name"] / "log"
        last_log = log.stat().st_mtime if log.is_file() else None
        server_pgids.add(r["pid"])
        servers.append({"id": f"run:{r['place']}/{r['repo']}/{r['name']}", "place": r["place"], "repo": r["repo"],
                        "name": r["name"], "cpu": round(sum(p["cpu"] for p in group), 1),
                        "mb": sum(p["mb"] for p in group), "started": r["started"], "lastLogH": _hours(last_log),
                        "lastClaudeH": _hours(info(r["place"])["lastClaude"]),
                        "abandoned": verdict(r["place"], [last_log, info(r["place"])["lastClaude"]])})
    docker = []
    if with_docker:
        for c in containers():
            at = _place_of(root, c["workdir"]) if c["workdir"] else None
            row = {"id": f"docker:{c['project']}" if c["project"] else f"docker:{c['name']}", **c,
                   "place": at[0] if at else None, "repo": at[1] if at else None, "abandoned": None}
            if at:      # el de su servidor (el que lo levantó); sin servidor, huérfano
                mine = [x for x in servers if (x["place"], x["repo"]) == at]
                row["abandoned"] = (next((x["abandoned"] for x in mine if x["abandoned"]), None) if mine
                                    else "huérfano: ningún servidor del IDE lo tiene levantado")
                row["server"] = mine[0]["id"] if mine else None
            docker.append(row)
    claude = [p for p in procs if re.match(r"(\S*/)?claude(\s|$)", p["command"])]
    others = sorted((p for p in procs if p["cpu"] >= 5 and p["pgid"] not in server_pgids), key=lambda p: -p["cpu"])[:15]
    # recorridos abiertos (node + su Chrome): la memoria es la de su node y todo lo que lanzó
    from ide_server import tour as tour_mod
    kids: dict[int, list[int]] = {}
    for line in _run(["ps", "-Ao", "pid=,ppid="]).splitlines():
        a, _, b = line.strip().partition(" ")
        if a.isdigit() and b.strip().isdigit():
            kids.setdefault(int(b), []).append(int(a))
    mb_of = {p["pid"]: p["mb"] for p in procs}
    tours = []
    for t in tour_mod.open_tours():
        tree, todo = set(), [t["pid"]]
        while todo:
            x = todo.pop()
            if x not in tree:
                tree.add(x)
                todo += kids.get(x, [])
        age = _hours(t["started"])
        tours.append({"id": f"tour:{t['pid']}", "pid": t["pid"], "sid": t["sid"], "hours": age,
                      "mb": sum(mb_of.get(x, 0) for x in tree),
                      "abandoned": None if age is not None and age < 2 else
                      (f"abierto hace {age} h" if age is not None else "de antes: sin registro de cuándo se abrió")})
    return {"battery": battery(), "config": cfg, "servers": servers, "docker": docker, "tours": tours,
            "claude": {"count": len(claude), "cpu": round(sum(p["cpu"] for p in claude), 1),
                       "mb": sum(p["mb"] for p in claude)},
            "top": others, "places": {k: {**v, "lastClaude": _hours(v["lastClaude"])} for k, v in infos.items()}}


def stop(root: Path, rid: str) -> str:
    """Corta un recurso del IDE por su id de `ide procs` (`run:<lugar>/<repo>/<script>` o `docker:<proyecto>`)."""
    from ide_server.runs import Runner
    from ide_server.sessions_fs import SessionError
    kind, _, rest = rid.partition(":")
    if kind == "run" and rest.count("/") == 2:
        place, repo, name = rest.split("/")
        Runner(root).stop(place, repo, name)
        deadline = time.time() + 20
        while time.time() < deadline and Runner(root).status(place, repo, name)["state"] in ("running", "stopping"):
            time.sleep(0.5)
        return f"parado {rest}"
    if kind == "docker" and re.fullmatch(r"[\w.-]+", rest):
        r = subprocess.run(["docker", "compose", "-p", rest, "stop"], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise SessionError("docker_failed", r.stderr.strip() or f"docker compose -p {rest} stop falló")
        return f"contenedores de {rest} parados"
    if kind == "tour" and rest.isdigit():
        from ide_server import tour as tour_mod
        try:
            tour_mod.stop_tour(int(rest))
        except ValueError as exc:
            raise SessionError("unknown", str(exc)) from exc
        return f"recorrido {rest} cerrado (y su Chrome)"
    raise SessionError("bad_request", f"id inválido: {rid} (los de `ide procs`: run:…, docker:… o tour:…)")


def snapshot_json(root: Path) -> str:
    return json.dumps(snapshot(root), ensure_ascii=False, indent=2)


def _battery_pct(s: str) -> tuple[int, bool] | None:
    m = re.search(r"(\d+)%;\s*(\w+)", s)
    return (int(m.group(1)), m.group(2) == "discharging") if m else None


class Watcher:
    """El vigilante (sin IA): cada `watch_seconds` toma una foto y avisa con una notificación de macOS
    cuando algo pasa `cpu_alert` % de CPU dos fotos seguidas, o la batería baja 10 puntos en media hora.
    Un mismo culpable avisa a lo más cada 2 h. Los avisos quedan en `.ide/sessions/recursos/alertas.log`
    (la sesión Recursos los lee)."""

    def __init__(self, root: Path, notify) -> None:
        self.root, self.notify = root, notify
        self._hot: set[str] = set()
        self._told: dict[str, float] = {}
        self._batt: list[tuple[float, int]] = []

    def _alert(self, key: str, msg: str) -> None:
        now = time.time()
        if now - self._told.get(key, 0) < 2 * 3600:
            return
        self._told[key] = now
        self.notify(f"Recursos: {msg}", RECURSOS)    # el click abre la sesión Recursos
        log = session_path(self.root, RECURSOS) / "alertas.log"
        if log.parent.is_dir():
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M')} {msg}\n")

    def tick(self) -> None:
        cfg = config(self.root)
        snap = snapshot(self.root)
        hot = {}
        for c in snap["docker"]:
            if c["cpu"] >= cfg["cpu_alert"]:
                where = f" (sesión {c['place']})" if c["place"] else ""
                hot[f"docker:{c['name']}"] = f"el contenedor {c['name']}{where} está al {c['cpu']:.0f}% de CPU"
        for p in snap["top"]:
            if p["cpu"] >= cfg["cpu_alert"] and "OrbStack" not in p["command"] and "com.docker" not in p["command"]:
                name = Path(p["command"].split(" -")[0]).name[:40]
                hot[f"pid:{p['pid']}"] = f"{name} (pid {p['pid']}) está al {p['cpu']:.0f}% de CPU"
        for key in hot.keys() & self._hot:          # dos fotos seguidas: no es un pico
            self._alert(key, hot[key])
        self._hot = set(hot)
        b = _battery_pct(snap["battery"])
        now = time.time()
        if b and b[1]:
            self._batt = [(t, v) for t, v in self._batt if now - t <= 1800] + [(now, b[0])]
            drop = max(v for _, v in self._batt) - b[0]
            if drop >= 10:
                self._alert("battery", f"la batería bajó {drop} puntos en media hora (va en {b[0]}%): `ide procs` dice qué consume")
        else:
            self._batt = []

    async def run(self, stop) -> None:
        import asyncio
        import logging
        while not stop.is_set():
            secs = config(self.root)["watch_seconds"]
            try:
                await asyncio.wait_for(stop.wait(), max(secs, 60))
            except asyncio.TimeoutError:
                pass
            if secs <= 0 or stop.is_set():
                continue
            try:
                await asyncio.to_thread(self.tick)
            except Exception:  # noqa: BLE001
                logging.getLogger(__name__).exception("el vigilante de recursos falló")
