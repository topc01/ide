# server/ide_server/devs.py
"""Desarrollos en la base (`.ide/ide.db`): fuente de verdad de su estado + historial.

- Un desarrollo con sesión es una fila de `devs` (id = id de la sesión). Su `status` vive acá: lo
  cambian el IDE y las sesiones con `ide status <estado>` (se refleja en SESSION.md
  para quien lo lea). Si una sesión todavía edita el `status:` del archivo a mano, el sync lo
  adopta y lo deja en el historial ("archivo").
- Los desarrollos que son solo PRs (tuyas o pendientes de revisar, sin sesión) salen de GitHub.
- `events`: historial de lo que hace el IDE, las sesiones y lo que pasa en GitHub."""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from ide_server.db import Db
from ide_server.sessions_fs import (
    SessionError, list_sessions, parse_frontmatter, read_session, session_path, state_file, write_frontmatter,
)

# Estado del desarrollo (uno solo, unificado con el de la PR): una FASE que avanza y, encima, un
# BLOQUEO opcional. Con PRs fuera de draft la fase la da GitHub (en testeo = sin revisores, en revisión,
# cambios pedidos, aprobada, mergeando, mergeada; la calcula la UI). Cualquier fase se puede poner a
# mano: si se pone desde la UI guarda la fase de GitHub de ese momento (`gh`) y gana hasta que GitHub
# cambie. El bloqueo (con nota) tapa la fase sin borrarla: `unblock` vuelve a la fase en que estaba.
PHASES = ("investigating", "developing", "ready-for-review", "testing", "in-review", "changes-requested",
          "approved", "merged")
BLOCKS = ("waiting-input", "blocked", "paused")
DEV_STATES = PHASES + BLOCKS
# los de antes (sesiones viejas, TICKET.md a mano): se aceptan y se traducen
LEGACY = {"analyzing": "investigating", "ready": "investigating", "in-progress": "developing",
          "done": "ready-for-review", "ready-to-develop": "investigating", "questions": "waiting-input",
          "blocked-definitions": "blocked", "blocked-client": "blocked", "blocked-dev": "blocked",
          "needs-reviewers": "testing"}
# los "bloqueado por …" de antes pasan a `blocked` con el motivo en la nota
LEGACY_NOTE = {"blocked-definitions": "por definiciones", "blocked-client": "por el cliente",
               "blocked-dev": "por otro desarrollo"}
STATUSES = {
    "ticket": DEV_STATES + ("unblock",),
    # approved / changes-requested: el veredicto publicado (por la sesión o con los botones del IDE);
    # suggests-*: veredicto todavía sin publicar
    # + las pausas (encima del veredicto): p.ej. `waiting-input` con el veredicto listo, esperando tu OK
    "review": ("reviewing", "suggests-approve", "suggests-changes", "approved", "changes-requested")
              + BLOCKS + ("unblock",),
}


REVIEW_LEGACY = {"commented": "reviewing"}


def normalize(kind: str | None, status: str | None) -> str | None:
    if kind == "review":
        return REVIEW_LEGACY.get(status or "", status)
    return LEGACY.get(status or "", status) if kind == "ticket" else status


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _archived(root: Path, sid: str) -> bool:
    return (root / ".ide" / "archive" / "sessions" / sid).exists()


def sync_from_disk(root: Path, db: Db, sessions: list[dict] | None = None) -> None:
    """Registra sesiones nuevas, adopta cambios hechos a mano en los archivos y marca archivadas."""
    sessions = list_sessions(root) if sessions is None else sessions
    known = {d["id"]: d for d in db.devs(include_archived=True)}
    seen = set()
    for s in sessions:
        sid = s["id"]
        seen.add(sid)
        row = known.get(sid)
        disk = {"kind": s["kind"], "title": s.get("title"), "notionUrl": (s.get("meta") or {}).get("notion_url"),
                "prUrl": s.get("prUrl"), "status": s.get("status")}
        if row is None:
            db.put_dev({"id": sid, **disk, "created": s.get("created") or now(), "updated": now()})
            if disk["kind"] not in ("main", "ide"):
                db.dev_index(f"s:{sid}")
            db.event(now(), "ide", "created", dev=sid, pr_url=disk["prUrl"],
                     data={"kind": disk["kind"], "title": disk["title"], "status": disk["status"]})
            continue
        changes = {k: v for k, v in disk.items() if k != "status" and v is not None and row.get(k) != v}
        disk["status"] = normalize(disk["kind"], disk["status"])
        if row.get("status") in LEGACY and row.get("kind") == "ticket":  # estados de antes: se migran
            changes["status"] = LEGACY[row["status"]]
            _mirror(root, sid, "ticket", changes["status"])
            disk["status"] = changes["status"]
            db.event(now(), "ide", "status", dev=sid, data={"from": row["status"], "to": changes["status"], "note": "migrado"})
            row = {**row, "status": changes["status"]}
        if disk["status"] and disk["status"] != row.get("status"):   # editado a mano en el archivo
            changes["status"] = disk["status"]
            db.event(now(), "archivo", "status", dev=sid, data={"from": row.get("status"), "to": disk["status"]})
        if row.get("archived"):
            changes["archived"] = 0
        if changes:
            db.put_dev({**row, **changes, "updated": now()})
    for sid, row in known.items():
        if sid not in seen and not row.get("archived") and _archived(root, sid):
            db.put_dev({**row, "archived": 1, "updated": now()})
            db.event(now(), "ide", "archived", dev=sid)


def _mirror(root: Path, sid: str, kind: str | None, status: str) -> None:
    """Reflejo del estado en SESSION.md (lo leen personas y sesiones viejas); la base manda."""
    f = session_path(root, sid) / (state_file(kind) or "")
    if f.is_file():
        meta, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        f.write_text(write_frontmatter({**meta, "status": status}, body), encoding="utf-8")


def _state(db: Db, key: str, row_status: str | None = None) -> dict:
    """{phase, block, note, since} guardado (o deducido del estado de la sesión / formato viejo)."""
    cur = dict(db.get(f"devstate:{key}") or {})
    if cur.get("block") in LEGACY_NOTE and not cur.get("note"):
        cur["note"] = LEGACY_NOTE[cur["block"]]
    for f in ("phase", "block", "status"):
        if cur.get(f) in LEGACY:
            cur[f] = LEGACY[cur[f]]
    row_status = LEGACY.get(row_status or "", row_status)
    if "phase" not in cur and "block" not in cur:
        old = cur.pop("status", None) or row_status
        cur["phase"] = old if old in PHASES else (None if old in BLOCKS else cur.get("phase"))
        cur["block"] = old if old in BLOCKS else None
    if row_status in BLOCKS and cur.get("block") != row_status:      # editado a mano en el archivo
        cur["block"] = row_status
    elif row_status in PHASES and (cur.get("block") or cur.get("phase") != row_status):
        cur["phase"], cur["block"] = row_status, None
    return cur


_KEEP = object()


def _apply(db: Db, key: str, status: str | None, note: str | None, actor: str, row_status: str | None = None,
           gh=_KEEP) -> tuple[str | None, str | None]:
    """Aplica `status` (fase, bloqueo, `unblock` o None = nada) y devuelve (efectivo antes, después).
    `gh`: la fase de GitHub cuando se puso una fase a mano desde la UI (la fase puesta gana mientras
    GitHub siga en esa); una fase puesta sin `gh` (sesiones) deja mandar a GitHub."""
    cur = _state(db, key, row_status)
    phase, block = cur.get("phase"), cur.get("block")
    pinned = "gh" in cur
    pin = cur.get("gh")
    before = block or phase
    if status in PHASES:
        phase, block = status, None
        pinned, pin = gh is not _KEEP, None if gh is _KEEP else gh
    elif status in BLOCKS:
        block = status
    elif status == "unblock":
        block = None
    elif status is None:
        phase, block = None, None
    after = block or phase
    since = cur.get("since") if after == before and cur.get("since") else now()
    if after is None:
        db.delete(f"devstate:{key}")
    else:
        db.set(f"devstate:{key}", {"phase": phase, "block": block, "note": note if status != "unblock" else None,
                                   "since": since, "actor": actor, **({"gh": pin} if pinned else {})})
    if block == "waiting-input" and before != "waiting-input" and actor != "ide":
        _notify_mac(f"{key[2:] if key.startswith('s:') else 'Un desarrollo'} te espera" + (f": {note}" if note else ""))
    return before, after


def set_status(root: Path, db: Db, sid: str, status: str, *, actor: str, note: str | None = None, gh=_KEEP) -> dict:
    sync_from_disk(root, db)
    row = db.dev(sid)
    if row is None or row.get("archived"):
        raise SessionError("unknown_session", f"no existe la sesión {sid}")
    allowed = STATUSES.get(row.get("kind") or "")
    status = normalize(row.get("kind"), status)
    if not allowed:
        raise SessionError("no_status", f"la sesión {sid} ({row.get('kind')}) no tiene estado")
    if status not in allowed:
        raise SessionError("bad_status", f"estado inválido para {row['kind']}: {status!r} ({' | '.join(allowed)})")
    prev = row.get("status")
    effective = status
    if row["kind"] == "ticket":
        _, effective = _apply(db, f"s:{sid}", status, note, actor, prev, gh)
        effective = effective or "investigating"
    elif status in BLOCKS or status == "unblock":   # revisión: la pausa va aparte, el veredicto queda
        _apply(db, f"s:{sid}", status, note, actor)
        db.event(now(), actor, "status", dev=sid, pr_url=row.get("prUrl"),
                 data={"from": prev, "to": status, **({"note": note} if note else {})})
        return db.dev(sid)
    elif db.get(f"devstate:s:{sid}"):           # revisión con veredicto nuevo: se destraba
        _apply(db, f"s:{sid}", "unblock", None, actor)
    db.put_dev({**row, "status": effective, "updated": now()})
    _mirror(root, sid, row["kind"], effective)
    db.event(now(), actor, "status", dev=sid, pr_url=row.get("prUrl"),
             data={"from": prev, "to": status, **({"note": note} if note else {})})
    return db.dev(sid)


def _notify_mac(message: str) -> None:
    import subprocess
    import sys
    import threading
    if sys.platform != "darwin":
        return
    # el texto va como argumento (no se interpreta como AppleScript)
    argv = ["osascript", "-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "IDE"',
            "-e", "end run", message[:200]]
    threading.Thread(target=lambda: subprocess.run(argv, capture_output=True), daemon=True).start()


def set_dev_state(root: Path, db: Db, key: str, status: str | None, *, actor: str, note: str | None = None,
                  gh=_KEEP) -> None:
    """Desde la UI, para cualquier desarrollo: una fase, un bloqueo, `unblock`, o None (PRs sin sesión:
    sin estado puesto). Sesión de ticket = `set_status`; PRs sin sesión: solo en la base."""
    if status is not None and status not in STATUSES["ticket"]:
        raise SessionError("bad_status", f"estado inválido: {status!r} ({' | '.join(STATUSES['ticket'])})")
    if key.startswith("s:"):
        set_status(root, db, key[2:], status or "unblock", actor=actor, note=note, gh=gh)
        return
    before, after = _apply(db, key, status, note, actor, gh=gh)
    db.event(now(), actor, "status", data={"key": key, "from": before, "to": after, **({"note": note} if note else {})})


def dev_states(db: Db) -> dict[str, dict]:
    """clave → {phase, block, note, since}: sesiones de ticket, revisiones pausadas y PRs sin sesión."""
    out = {}
    for k in db.with_prefix("devstate:"):
        if not k.startswith("s:"):
            out[k] = _state(db, k)
    for r in db.devs():
        if r.get("kind") == "ticket" and r.get("status"):
            out[f"s:{r['id']}"] = _state(db, f"s:{r['id']}", r["status"])
        elif r.get("kind") == "review" and (cur := db.get(f"devstate:s:{r['id']}")) and cur.get("block"):
            out[f"s:{r['id']}"] = _state(db, f"s:{r['id']}")   # revisión pausada (p.ej. esperando tu OK)
    return {k: {**{x: v.get(x) for x in ("phase", "block", "note", "since", "actor")}, **({"gh": v["gh"]} if "gh" in v else {})}
            for k, v in out.items()}


# -- lectura para la sesión principal (ide dev ls / show) -----------------------------------------

def _pr_summary(c: dict) -> dict:
    return {k: c.get(k) for k in ("url", "repo", "number", "title", "author", "review", "ci", "draft",
                                  "head", "base", "stack", "depsPending")} | {
        "reviewers": c.get("reviewers") or [], "deps": [
            {"url": d.get("url"), "repo": d.get("repo"), "number": d.get("number"), "state": d.get("state"),
             "together": d.get("together"), "via": d.get("via")}
            for d in (c.get("deps") or [])]}


def _cards(gh: dict) -> dict[str, dict]:
    lists = [gh.get("pending") or [], gh.get("changesRequested") or [],
             *(gh.get("mine") or {}).values(), *(gh.get("stacks") or {}).values()]
    return {c["url"]: c for lst in lists for c in lst}


def split_parallel(root: Path, db: Db, sessions: list[dict], gh: dict) -> list[str]:
    """Un desarrollo tiene **una línea por repo** (la rama de su worktree y lo apilado sobre ella). Si
    una sesión abre una PR tuya con su prefijo (`<login>/d<n>-…`) en otra rama de un repo que ya tiene
    (una línea paralela), esa línea pasa a un **desarrollo nuevo**: sesión con el worktree en la PR de
    más arriba de esa línea, las PRs asignadas ahí y un SESSION.md que dice de dónde salió. Si una PR
    de otro repo del desarrollo original depende de esa línea, queda un pendiente para decidir si va
    con ella. Devuelve las sesiones creadas. Las PRs ya asignadas a mano (`link`) no se tocan."""
    import io
    from ide_server import later as later_mod
    from ide_server.repos_fs import add_repo
    from ide_server.session_ops import create_session
    from ide_server.worktrees import BranchOccupied
    me = gh.get("me")
    if not me:
        return []
    mine = [c for lst in (gh.get("mine") or {}).values() for c in lst]
    links = db.dev_prs()
    idx = db.with_prefix("devidx:")
    created = []
    for s in sessions:
        n = idx.get(f"s:{s['id']}")
        if s.get("kind") != "ticket" or n is None:
            continue
        prefix = f"{me}/d{n}-"
        repos = {r["name"]: r.get("branch") for r in s.get("repos") or [] if r.get("branch")}
        # la línea de cada repo: la rama del worktree y todo su stack
        line: dict[str, set] = {}
        for repo, branch in repos.items():
            sid_stack = next(((c.get("stack") or {}).get("id") for c in mine if c["repo"] == repo and c.get("head") == branch), None)
            line[repo] = {branch} | {c.get("head") for c in mine if sid_stack and (c.get("stack") or {}).get("id") == sid_stack}
        parallel = [c for c in mine if c["repo"] in repos and (c.get("head") or "").startswith(prefix)
                    and c.get("head") not in line[c["repo"]] and c["url"] not in links]
        stacks: dict[str, list[dict]] = {}
        for c in parallel:
            stacks.setdefault((c.get("stack") or {}).get("id") or c["url"], []).append(c)
        for prs in stacks.values():
            prs.sort(key=lambda c: (c.get("stack") or {}).get("position", 0))
            top = prs[-1]
            new = re.sub(r"[^a-z0-9-]+", "-", f"d{n}-{top['head'][len(prefix):]}".lower()).strip("-")[:60]
            if session_path(root, new).exists():
                continue
            try:
                # la de origen como `caller`: hereda sus permisos (nunca más, nunca full)
                create_session(root, {"id": new, "title": f"{top['title']} (sale del #{n})", "caller": s["id"]})
                add_repo(root, new, top["repo"], branch=top["head"], out=io.StringIO())
            except BranchOccupied:
                continue                                    # la rama está en otro worktree: se intenta después
            now_ = now()
            for c in prs:
                db.link_pr(c["url"], new)
                for dev in (s["id"], new):
                    db.event(now_, "ide", "pr-moved", dev=dev, pr_url=c["url"],
                             data={"from": s["id"], "to": new, "note": "línea paralela: desarrollo nuevo"})
            urls = {c["url"] for c in prs}
            nums = " → ".join(f"{c['repo']}#{c['number']}" for c in prs)
            (session_path(root, new) / "SESSION.md").write_text(
                f"---\nstatus: developing\ntitle: {top['title']} (sale del #{n})\n---\n## Origen\n\n"
                f"Línea paralela de {top['repo']} ({nums}) que se separó sola del desarrollo **#{n}** (sesión "
                f"`{s['id']}`): un desarrollo tiene una sola línea por repo. El contexto está en "
                f"`../{s['id']}/SESSION.md`.\n", encoding="utf-8")
            # PRs de otros repos del desarrollo original que dependen de esta línea: decidir juntos
            for c in mine:
                if c["url"] in urls or c["repo"] == top["repo"]:
                    continue
                if any(d.get("url") in urls for d in c.get("deps") or []):
                    later_mod.add(db, f"s:{s['id']}", f"¿{c['repo']}#{c['number']} se va al desarrollo nuevo `{new}`?",
                                  f"Depende de {nums}, que se separó a `{new}` (línea paralela). Si van juntas, "
                                  f"muévela con `ide dev link <#n de {new}> {c['repo']}#{c['number']}`.", "ide")
            created.append(new)
    return created


def link_prs(db: Db, sessions: list[dict], gh: dict) -> bool:
    """Recuerda qué PRs tuyas están en la rama de un worktree de cada sesión de ticket: quedan en
    ese desarrollo aunque después el worktree cambie de rama. Devuelve si agregó alguna."""
    links = db.dev_prs()
    mine = [c for lst in (gh.get("mine") or {}).values() for c in lst]
    added = False
    for s in sessions:
        if s.get("kind") != "ticket":
            continue
        for c in mine:
            if c["url"] in links:
                continue
            if any(r.get("branch") and r["name"] == c.get("repo") and r["branch"] == c.get("head")
                   for r in s.get("repos", [])):
                db.link_pr(c["url"], s["id"])
                links[c["url"]] = {"sid": s["id"]}
                added = True
    return added


def _belongs(c: dict, s: dict, links: dict[str, dict]) -> bool:
    """La PR es del desarrollo de la sesión: vinculada (y no sacada), o en la rama de un worktree
    si no está vinculada a otra sesión ni sacada de esta."""
    link = links.get(c["url"])
    if link:
        return link["sid"] == s["id"] and not link.get("out")
    return any(r.get("branch") and r["name"] == c.get("repo") and r["branch"] == c.get("head")
               for r in s.get("repos", []))


def _name(names: dict[str, str], key: str, prs: list[dict]) -> str | None:
    """El nombre puesto en el IDE; si el desarrollo cambió de clave (una PR que ahora tiene sesión),
    el de su stack o sus PRs."""
    if key in names:
        return names[key]
    for c in prs:
        for k in ([f"st:{c['stack']['id']}"] if c.get("stack") else []) + [f"p:{c['url']}"]:
            if k in names:
                return names[k]
    return None


def list_devs(root: Path, db: Db, sessions: list[dict], gh: dict) -> list[dict]:
    """Todos los desarrollos: los de sesión (estado de la base) y los que son solo PRs."""
    cards = _cards(gh)
    names = db.dev_names()
    links = db.dev_prs()
    by_sid = {s["id"]: s for s in sessions}
    me = gh.get("me")
    taken: set[str] = set()
    out = []
    for row in db.devs():
        s = by_sid.get(row["id"], {})
        if s.get("stackPrs"):                   # revisión de varias PRs (stack o movidas ahí)
            prs = [cards[u] for u in s["stackPrs"] if u in cards]
        elif row.get("prUrl"):
            prs = [cards[row["prUrl"]]] if row["prUrl"] in cards else []
        else:
            prs = [c for c in cards.values() if _belongs(c, s, links)]
            stacks = {c["stack"]["id"] for c in prs if c.get("stack")}
            # el stack trae a sus compañeras, salvo las asignadas a otro desarrollo o sacadas (el stack
            # es lo último en la precedencia: explícita > pegajosa > por rama > stack)
            prs += [c for c in cards.values() if c.get("stack") and c["stack"]["id"] in stacks
                    and c.get("author") == f"@{me}" and c not in prs
                    and not (links.get(c["url"]) and (links[c["url"]]["sid"] != row["id"] or links[c["url"]].get("out")))]
        taken |= {c["url"] for c in prs}
        out.append({"id": row["id"], "kind": row["kind"], "name": _name(names, f"s:{row['id']}", prs),
                    "title": row["title"], "status": row["status"],
                    "notionUrl": row["notionUrl"], "process": s.get("process"),
                    # trabajando / esperando al usuario (hooks de claude), con la 1ª línea de su último mensaje
                    "activity": (s.get("activity") or {}).get("state") if s.get("process") == "running" else None,
                    "activityNote": (s.get("activity") or {}).get("note") if s.get("process") == "running" else None,
                    "repos": [{"name": r["name"], "branch": r.get("branch")} for r in s.get("repos", [])],
                    # una revisión de varias PRs: en su orden (el stack de abajo arriba, las movidas al final)
                    "prs": [_pr_summary(c) for c in (prs if s.get("stackPrs") else
                                                     sorted(prs, key=lambda c: (c.get("stack") or {}).get("position", 0)))]})
    # solo PRs: las mías (por stack) y las que me pidieron revisar, sin sesión
    groups: dict[str, list[dict]] = {}
    for c in cards.values():
        if c["url"] in taken:
            continue
        mine = c.get("author") == f"@{me}"
        pending = any(p["url"] == c["url"] for p in gh.get("pending") or [])
        changes = any(p["url"] == c["url"] for p in gh.get("changesRequested") or [])
        if not (mine or pending or changes):
            continue
        key = f"stack:{c['stack']['id']}" if c.get("stack") and mine else c["url"]
        groups.setdefault(key, []).append(c)
    for key, prs in groups.items():
        prs.sort(key=lambda c: (c.get("stack") or {}).get("position", 0))
        first = prs[0]
        out.append({"id": f"{first['repo']}#{first['number']}", "kind": "pr" if first.get("author") == f"@{me}"
                    else "review-pending" if any(p["url"] == first["url"] for p in gh.get("pending") or [])
                    else "review-changes", "name": _name(names, f"st:{first['stack']['id']}" if key.startswith("stack:")
                                                         else f"p:{first['url']}", prs), "title": first["title"], "status": None, "notionUrl": None,
                    "process": None, "repos": [], "prs": [_pr_summary(c) for c in prs]})
    return with_index(db, out)


def with_index(db: Db, devs: list[dict]) -> list[dict]:
    idx = db.with_prefix("devidx:")
    for d in devs:
        d["index"] = idx.get(_ui_key(d)) or next((idx[k] for k in _alt_keys(d["prs"]) if k in idx), None)
    return devs


def show_dev(root: Path, db: Db, dev_id: str, sessions: list[dict], gh: dict) -> dict:
    devs = list_devs(root, db, sessions, gh)
    d = next((x for x in devs if x["id"] == dev_id), None)
    if d is None:
        raise SessionError("unknown_dev", f"no existe el desarrollo {dev_id} (mira `ide dev ls`)")
    urls = [p["url"] for p in d["prs"]]
    row = db.dev(dev_id)
    if row and row.get("prUrl") and row["prUrl"] not in urls:
        urls.append(row["prUrl"])
    return {**d, "events": db.events(dev=dev_id if row else None, pr_urls=urls, limit=60)}


# -- índice de los desarrollos ----------------------------------------------------------------------
# Un número correlativo por desarrollo (`#12`), que nunca se reutiliza. Se guarda por clave de la UI
# (`s:<sesión>`, `st:<stack>`, `p:<url>`); una PR o stack con número que pasa a tener sesión le
# hereda el número a la sesión.

def _ui_key(d: dict) -> str:
    """La clave con que la UI nombra el desarrollo (misma regla que `deriveMine`)."""
    if d["kind"] not in ("pr", "review-pending", "review-changes"):
        return f"s:{d['id']}"
    prs = d["prs"]
    if len(prs) > 1 and prs[0].get("stack"):
        return f"st:{prs[0]['stack']['id']}"
    return f"p:{prs[0]['url']}"


def _alt_keys(prs: list[dict]) -> list[str]:
    return [k for c in prs for k in ([f"st:{c['stack']['id']}"] if c.get("stack") else []) + [f"p:{c['url']}"]]


def assign_indices(db: Db, devs: list[dict]) -> dict[str, int]:
    """Da número a los desarrollos que no tienen (sesiones por fecha de creación, después PRs)."""
    idx: dict[str, int] = db.with_prefix("devidx:")
    rows = {r["id"]: r for r in db.devs(include_archived=True)}
    order = sorted(devs, key=lambda d: (d["kind"] in ("pr", "review-pending", "review-changes"),
                                        (rows.get(d["id"]) or {}).get("created") or "",
                                        [p.get("number") or 0 for p in d["prs"]]))
    for d in order:
        if d["kind"] in ("main", "ide"):
            continue
        key = _ui_key(d)
        if key in idx:
            continue
        inherited = next((idx[k] for k in _alt_keys(d["prs"]) if k in idx), None)
        idx[key] = db.dev_index(key, inherited)
    return idx


def _slug(text: str, sep: str) -> str:
    return re.sub(r"[^a-z0-9]+", sep, unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()).strip(sep)


def dev_env(root: Path, sid: str) -> dict[str, str]:
    """IDE_DEV_INDEX / IDE_DEV_SLUG (`d12_rendiciones_matematica`, ≤ 32: sirve para bases de Postgres)
    / IDE_BRANCH_PREFIX (`<login de GitHub>/`) de la sesión, si ya tiene número."""
    try:
        info = read_session(root, sid)
        if info.get("kind") in (None, "main", "ide"):
            return {}
        db = Db(root)
        n = db.dev_index(f"s:{sid}")
        name = db.get(f"devname:s:{sid}") or info.get("title") or sid
        me = db.get("me")
    except Exception:  # noqa: BLE001 — sin base: los scripts siguen con lo de siempre
        return {}
    slug = f"d{n}_{_slug(name, '_')}"[:32].rstrip("_")
    return {"IDE_DEV_INDEX": str(n), "IDE_DEV_SLUG": slug,
            "IDE_DEV_BRANCH": f"{me + '/' if me else ''}d{n}-{_slug(name, '-')}"[:60].rstrip("-")}
