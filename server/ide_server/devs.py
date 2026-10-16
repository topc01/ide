# server/ide_server/devs.py
"""Desarrollos en la base (`.ide/ide.db`): fuente de verdad de su estado + historial.

- Un desarrollo con sesión es una fila de `devs` (id = id de la sesión). Su `status` vive acá: lo
  cambian el IDE y las sesiones con `ide status <estado>` (se refleja en TICKET.md/REVIEW.md
  para quien lo lea). Si una sesión todavía edita el `status:` del archivo a mano, el sync lo
  adopta y lo deja en el historial ("archivo").
- Los desarrollos que son solo PRs (tuyas o pendientes de revisar, sin sesión) salen de GitHub.
- `events`: historial de lo que hace el IDE, las sesiones y lo que pasa en GitHub."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from ide_server.db import Db
from ide_server.sessions_fs import (
    SessionError, list_sessions, parse_frontmatter, session_path, state_file, write_frontmatter,
)

STATUSES = {
    "ticket": ("analyzing", "blocked", "questions", "ready", "in-progress", "done"),
    "review": ("reviewing", "commented", "approved", "changes-requested"),
}


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
            db.event(now(), "ide", "created", dev=sid, pr_url=disk["prUrl"],
                     data={"kind": disk["kind"], "title": disk["title"], "status": disk["status"]})
            continue
        changes = {k: v for k, v in disk.items() if k != "status" and v is not None and row.get(k) != v}
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


def set_status(root: Path, db: Db, sid: str, status: str, *, actor: str, note: str | None = None) -> dict:
    sync_from_disk(root, db)
    row = db.dev(sid)
    if row is None or row.get("archived"):
        raise SessionError("unknown_session", f"no existe la sesión {sid}")
    allowed = STATUSES.get(row.get("kind") or "")
    if not allowed:
        raise SessionError("no_status", f"la sesión {sid} ({row.get('kind')}) no tiene estado")
    if status not in allowed:
        raise SessionError("bad_status", f"estado inválido para {row['kind']}: {status!r} ({' | '.join(allowed)})")
    prev = row.get("status")
    db.put_dev({**row, "status": status, "updated": now()})
    # reflejo en el archivo (lo leen personas y sesiones viejas); la base manda
    f = session_path(root, sid) / (state_file(row["kind"]) or "")
    if f.is_file():
        meta, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        f.write_text(write_frontmatter({**meta, "status": status}, body), encoding="utf-8")
    db.event(now(), actor, "status", dev=sid, pr_url=row.get("prUrl"),
             data={"from": prev, "to": status, **({"note": note} if note else {})})
    return db.dev(sid)


# -- lectura para la sesión principal (ide dev ls / show) -----------------------------------------

def _pr_summary(c: dict) -> dict:
    return {k: c.get(k) for k in ("url", "repo", "number", "title", "author", "review", "ci", "draft",
                                  "head", "base", "stack", "depsPending")} | {
        "reviewers": c.get("reviewers") or [], "deps": [
            {"repo": d.get("repo"), "number": d.get("number"), "state": d.get("state"), "together": d.get("together")}
            for d in (c.get("deps") or [])]}


def _cards(gh: dict) -> dict[str, dict]:
    lists = [gh.get("pending") or [], gh.get("changesRequested") or [],
             *(gh.get("mine") or {}).values(), *(gh.get("stacks") or {}).values()]
    return {c["url"]: c for lst in lists for c in lst}


def list_devs(root: Path, db: Db, sessions: list[dict], gh: dict) -> list[dict]:
    """Todos los desarrollos: los de sesión (estado de la base) y los que son solo PRs."""
    cards = _cards(gh)
    by_sid = {s["id"]: s for s in sessions}
    me = gh.get("me")
    taken: set[str] = set()
    out = []
    for row in db.devs():
        s = by_sid.get(row["id"], {})
        if row.get("prUrl"):
            prs = [cards[row["prUrl"]]] if row["prUrl"] in cards else []
        else:
            prs = [c for c in cards.values() if any(r.get("branch") and r["name"] == c.get("repo")
                                                    and r["branch"] == c.get("head") for r in s.get("repos", []))]
            stacks = {c["stack"]["id"] for c in prs if c.get("stack")}
            prs += [c for c in cards.values() if c.get("stack") and c["stack"]["id"] in stacks
                    and c.get("author") == f"@{me}" and c not in prs]
        taken |= {c["url"] for c in prs}
        out.append({"id": row["id"], "kind": row["kind"], "title": row["title"], "status": row["status"],
                    "notionUrl": row["notionUrl"], "process": s.get("process"),
                    "repos": [{"name": r["name"], "branch": r.get("branch")} for r in s.get("repos", [])],
                    "prs": [_pr_summary(c) for c in sorted(prs, key=lambda c: (c.get("stack") or {}).get("position", 0))]})
    # solo PRs: las mías (por stack) y las que me pidieron revisar, sin sesión
    groups: dict[str, list[dict]] = {}
    for c in cards.values():
        if c["url"] in taken:
            continue
        mine = c.get("author") == f"@{me}"
        pending = any(p["url"] == c["url"] for p in gh.get("pending") or [])
        if not (mine or pending):
            continue
        key = f"stack:{c['stack']['id']}" if c.get("stack") and mine else c["url"]
        groups.setdefault(key, []).append(c)
    for key, prs in groups.items():
        prs.sort(key=lambda c: (c.get("stack") or {}).get("position", 0))
        first = prs[0]
        out.append({"id": f"{first['repo']}#{first['number']}", "kind": "pr" if first.get("author") == f"@{me}"
                    else "review-pending", "title": first["title"], "status": None, "notionUrl": None,
                    "process": None, "repos": [], "prs": [_pr_summary(c) for c in prs]})
    return out


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
