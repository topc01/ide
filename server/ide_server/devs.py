# server/ide_server/devs.py
"""Desarrollos en la base (`.ide/ide.db`): fuente de verdad de su estado + historial.

- Un desarrollo con sesión es una fila de `devs` (id = id de la sesión). Su `status` vive acá: lo
  cambian el IDE y las sesiones con `ide status <estado>` (se refleja en SESSION.md
  para quien lo lea). Si una sesión todavía edita el `status:` del archivo a mano, el sync lo
  adopta y lo deja en el historial ("archivo").
- Los desarrollos que son solo PRs (tuyas o pendientes de revisar, sin sesión) salen de GitHub.
- `events`: historial de lo que hace el IDE, las sesiones y lo que pasa en GitHub."""
from __future__ import annotations
import json
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


# los nombres de la pantalla (ui/src/modules/sessions/devStates.ts), para los mensajes
LABEL = {"investigating": "investigando", "developing": "desarrollando", "ready-for-review": "listo para revisión",
         "testing": "en testeo", "in-review": "en revisión", "changes-requested": "cambios pedidos",
         "approved": "aprobado", "merging": "mergeando", "merged": "mergeado"}


# una nota de bloqueo que en realidad espera al usuario (su decisión, su OK): eso es «te espera»
_USER_RE = re.compile(r"\b(tom[aá]s|el usuario|del usuario|tu (ok|decisi[oó]n|visto bueno|respuesta|confirmaci[oó]n|input)"
                      r"|visto bueno|que (decidas|confirmes|me digas))\b", re.I)


def _asks_user(note: str | None) -> bool:
    return bool(note and _USER_RE.search(note))


def _edited_after(s: dict, row: dict) -> bool:
    """El SESSION.md de la sesión se modificó después del último cambio de su fila en la base."""
    from datetime import datetime
    try:
        mtime = (Path(s["path"]) / "SESSION.md").stat().st_mtime
        return mtime > datetime.fromisoformat(str(row.get("updated"))).timestamp() + 1
    except (OSError, ValueError, KeyError, TypeError):
        return True


def _backwards(before: str | None, status: str | None) -> bool:
    """Volver a «investigando» desde una fase posterior: lo puedes hacer tú o la manager; la sesión misma (o
    su archivo) no."""
    return status == "investigating" and before not in (None, "investigating")


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
            if disk["kind"] not in ("main", "ide", "recursos", "plugins"):
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
        # editado a mano en el archivo: solo si el archivo cambió después del último guardado en la base
        # (si no, es el SESSION.md de antes de que el IDE le copiara el estado nuevo: volvería atrás)
        if disk["status"] and disk["status"] != row.get("status") and _edited_after(s, row) \
                and not _backwards(row.get("status"), disk["status"]):
            changes["status"] = disk["status"]
            db.event(now(), "archivo", "status", dev=sid, data={"from": row.get("status"), "to": disk["status"]})
        if row.get("archived"):
            changes["archived"] = 0
        if changes:
            db.put_dev({**row, **changes, "updated": now()})
    for sid, row in known.items():
        if sid not in seen and not row.get("archived"):
            # archivada (está en .ide/archive) o borrada (`ide session rm`, o la carpeta ya no existe): sale del
            # tablero; antes una borrada quedaba en la base y `ide dev ls` / el árbol fallaban buscando su sesión
            gone = not _archived(root, sid)
            db.put_dev({**row, "archived": 1, "updated": now()})
            db.event(now(), "ide", "removed" if gone else "archived", dev=sid)


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
    if status == "blocked" and actor.startswith("claude:") and _asks_user(note):
        raise SessionError("not_blocked", "eso no es un bloqueo: si falta una decisión o un OK del usuario, el "
                                          "desarrollo queda en «te espera» solo. Termina el turno con la pregunta "
                                          "para él (clara, en el último mensaje). «Bloqueado» es solo para lo que "
                                          "depende de afuera: otra persona, producto, el cliente u otro desarrollo")
    # tú (UI, terminal) y la manager pueden volverlo a «investigando»; la sesión misma no se devuelve sola
    if _backwards(phase, status) and actor == f"claude:{key[2:]}":
        raise SessionError("backwards", "una sesión no se devuelve sola a «investigando»: este desarrollo ya "
                                        f"pasó a «{LABEL.get(phase, phase)}» (si está frenado, márcalo bloqueado o "
                                        "pausado; volverlo a investigando lo hace el usuario o la manager)")
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
        _notify_mac(f"{key[2:] if key.startswith('s:') else 'Un desarrollo'} te espera" + (f": {note}" if note else ""),
                    focus=key[2:] if key.startswith("s:") else None)
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


NOTIFY_URL: str | None = None             # la URL del IDE (la pone app.py): el click en el aviso la abre


def _notify_mac(message: str, focus: str | None = None) -> None:
    """Notificación de macOS. Con `terminal-notifier` (brew), un click abre el IDE enfocado en la sesión
    `focus` (`<url>#<id>`); si no está, con osascript (sin click)."""
    import shutil
    import subprocess
    import sys
    import threading
    if sys.platform != "darwin":
        return
    tn = shutil.which("terminal-notifier") or next(
        (p for p in ("/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier") if Path(p).is_file()), None)
    # el texto va como argumento (no se interpreta como AppleScript)
    plain = ["osascript", "-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "IDE"',
             "-e", "end run", message[:200]]
    if tn:
        from urllib.parse import quote
        url = f"{NOTIFY_URL}/#{quote(focus)}" if NOTIFY_URL and focus else NOTIFY_URL
        import shlex
        # el click lleva a la pestaña del IDE que ya está abierta en Chrome (cambia el #, no recarga); si no
        # hay ninguna, abre una nueva
        script = Path(__file__).parent / "assets" / "focus_tab.applescript"
        app = Path.home() / "Applications" / "Chrome Apps.localized" / "Agentic IDE.app"   # el IDE instalado (PWA)
        if url and NOTIFY_URL and focus:
            # 1) el IDE le dice a sus ventanas abiertas que enfoquen la sesión (sin recargar); 2) al frente la app
            # instalada si está, si no la pestaña de Chrome, y si no hay ninguna, una pestaña nueva
            tell = (f"curl -s -m 3 -X POST -H 'Content-Type: application/json' "
                    f"-d {shlex.quote(json.dumps({'id': focus}))} {shlex.quote(NOTIFY_URL + '/api/ui/focus')} >/dev/null; ")
            front = (f"open -a {shlex.quote(str(app))}" if app.is_dir() else
                     f"/usr/bin/osascript {shlex.quote(str(script))} {shlex.quote(url)} {shlex.quote(NOTIFY_URL + '/')} "
                     f"| grep -q ok || open {shlex.quote(url)}")
            click = ["-execute", tell + front]
        else:
            click = ["-open", url] if url else []
        argv = [tn, "-title", "IDE", "-message", message[:200], *click,
                *(["-group", f"ide-{focus}"] if focus else [])]

        def send() -> None:
            # sin permiso de notificaciones (macOS), terminal-notifier falla: el aviso sale igual por osascript
            if subprocess.run(argv, capture_output=True).returncode != 0:
                subprocess.run(plain, capture_output=True)
        threading.Thread(target=send, daemon=True).start()
        return
    threading.Thread(target=lambda: subprocess.run(plain, capture_output=True), daemon=True).start()


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


def add_extra_worktrees(root: Path, sessions: list[dict], repo_names: list[str]) -> None:
    """Los worktrees que una sesión armó aparte de los suyos (en su carpeta de worktrees con otro nombre,
    dentro de su carpeta o en el scratchpad de su claude): `s["extra"]` = [{name, branch, path}]. Sus
    PRs son del desarrollo de la sesión (o una línea paralela, ver `split_parallel`)."""
    import subprocess
    by_sid = {s["id"]: s for s in sessions}
    for s_ in sessions:
        s_["extra"] = []
    base = root.resolve() / ".ide"
    scratch = {re.sub(r"[^A-Za-z0-9-]", "-", str((base / "sessions" / sid).resolve())): sid for sid in by_sid}
    own = {(base / "sessions" / s_["id"] / r["name"]).resolve() for s_ in sessions for r in s_.get("repos") or []}
    for repo in repo_names:
        if not (root / repo / ".git").is_dir():     # un worktree de otro repo (comparten la lista)
            continue
        try:
            out = subprocess.run(["git", "-C", str(root / repo), "worktree", "list", "--porcelain"],
                                 capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        path = None
        for line in out.splitlines():
            if line.startswith("worktree "):
                path = Path(line[9:]).resolve()
            elif line.startswith("branch refs/heads/") and path is not None:
                sid = None
                for kind in ("worktrees", "sessions"):
                    try:
                        rel = path.relative_to(base / kind)
                        sid = rel.parts[0] if rel.parts else None
                    except ValueError:
                        pass
                    if sid:
                        break
                sid = sid or next((scratch[d.name] for d in path.parents
                                   if d.name in scratch and d.parent.name.startswith("claude-")), None)
                s_ = by_sid.get(sid or "")
                if s_ is None or path in own:      # el worktree propio de una sesión
                    continue
                s_["extra"].append({"name": repo, "branch": line[18:], "path": str(path)})


def _parallel(c: dict, s: dict, me: str | None, n: int | None) -> bool:
    """Una PR en una línea paralela de la sesión (otro worktree, mismo repo, rama con su prefijo): va a un
    desarrollo nuevo (`split_parallel`), no a este."""
    return bool(me and n is not None and c.get("repo") in {r["name"] for r in s.get("repos") or []}
                and (c.get("head") or "").startswith(f"{me}/d{n}-")
                and not any(r["name"] == c["repo"] and r.get("branch") == c.get("head") for r in s.get("repos") or []))


def _on_branch(c: dict, s: dict, me: str | None = None, n: int | None = None) -> bool:
    """La rama de la PR está en un worktree de la sesión: los suyos, o uno extra salvo que sea una
    línea paralela."""
    own = any(r.get("branch") and r["name"] == c.get("repo") and r["branch"] == c.get("head")
              for r in s.get("repos", []))
    return own or (any(r["name"] == c.get("repo") and r["branch"] == c.get("head") for r in s.get("extra") or [])
                   and not _parallel(c, s, me, n))


def split_parallel(root: Path, db: Db, sessions: list[dict], gh: dict) -> list[str]:
    """Un desarrollo tiene **una línea por repo** (la rama de su worktree y lo apilado sobre ella). Si
    una sesión abre una PR tuya con su prefijo (`<login>/d<n>-…`) en otra rama de un repo que ya tiene
    que sale de la rama base del repo (una línea paralela: ni apilada sobre una rama del desarrollo ni
    contenida en la rama del worktree), esa línea pasa a un **desarrollo nuevo**: sesión con el worktree en la PR de
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
            # los stacks de la línea: el de la PR de la rama del worktree y el de las PRs que ya son de esta
            # sesión en ese repo (si la rama del worktree todavía no tiene PR —la sesión abre las PRs de un
            # stack de a una—, las de abajo ya vinculadas dicen cuál es su stack)
            stacks_ = {(c.get("stack") or {}).get("id") for c in mine if c["repo"] == repo
                       and (c.get("head") == branch or (links.get(c["url"]) or {}).get("sid") == s["id"])} - {None}
            line[repo] = {branch} | {c.get("head") for c in mine if c["repo"] == repo
                                     and (c.get("stack") or {}).get("id") in stacks_}
        parallel = [c for c in mine if c["repo"] in repos and (c.get("head") or "").startswith(prefix)
                    and c.get("head") not in line[c["repo"]] and c["url"] not in links]
        stacks: dict[str, list[dict]] = {}
        for c in parallel:
            stacks.setdefault((c.get("stack") or {}).get("id") or c["url"], []).append(c)
        for prs in stacks.values():
            prs.sort(key=lambda c: (c.get("stack") or {}).get("position", 0))
            # paralela de verdad = sale de la rama base del repo (develop/main): si la de abajo está apilada sobre
            # una rama de este desarrollo, o alguna de sus ramas ya está en la rama del worktree (la sesión abre
            # las PRs de un stack de a una y la de arriba todavía no tiene PR), es su stack, no otra línea
            base = prs[0].get("base") or ""
            if (base in line[prs[0]["repo"]] or base.startswith(prefix)
                    or any(_in_worktree(session_path(root, s["id"]) / c["repo"], c.get("head")) for c in prs)):
                continue
            # tampoco es otro trabajo (spec: hotfix + backport van en un mismo desarrollo) si:
            # (1) va junto con una PR del desarrollo («van juntas», en cualquier sentido);
            # (2) es el par main/develop de una PR del desarrollo en el mismo repo (hotfix y su backport);
            # (3) su rama está en un worktree extra que armó la propia sesión (la está trabajando ella)
            own = [c for c in mine if c["url"] not in {x["url"] for x in prs} and c["repo"] in repos
                   and (c.get("head") in line[c["repo"]] or (links.get(c["url"]) or {}).get("sid") == s["id"])]
            own_urls = {c["url"] for c in own}
            cand = {c["url"] for c in prs}
            together = any(d.get("together") and d.get("url") in own_urls for c in prs for d in c.get("deps") or []) \
                or any(d.get("together") and d.get("url") in cand for c in own for d in c.get("deps") or [])
            pair = any(c["repo"] == prs[0]["repo"] and {c.get("base"), base} in ({"main", "develop"}, {"master", "develop"})
                       for c in own)
            extra = any(e.get("name") == c["repo"] and e.get("branch") == c.get("head")
                        for c in prs for e in s.get("extra") or [])
            if together or pair or extra:
                continue
            top = prs[-1]
            nums = " → ".join(f"{c['repo']}#{c['number']}" for c in prs)
            # dónde está tomada la rama (un worktree extra de la sesión de origen): se avisa en vez de fallar
            busy = next((e["path"] for e in s.get("extra") or [] if e["name"] == top["repo"] and e["branch"] == top["head"]), None)
            prompt = (f"Este desarrollo se separó solo del #{n} (sesión `{s['id']}`): es una línea paralela de "
                      f"{top['repo']} ({nums}), y un desarrollo tiene una sola línea por repo. El contexto está en "
                      f"`../{s['id']}/SESSION.md`. Lee eso y la PR, y sigue desde ahí.")
            # la de origen como `caller`: hereda sus permisos (nunca más, nunca full). Su id es su número (#n);
            # no se vuelve a crear porque sus PRs quedan vinculadas a ella justo abajo
            new = create_session(root, {"title": f"{top['title']} (sale del #{n})", "caller": s["id"], "prompt": prompt})["session"]["id"]
            try:
                add_repo(root, new, top["repo"], branch=top["head"], out=io.StringIO())
            except BranchOccupied:
                busy = busy or "otro worktree"
            db.set(f"splitfrom:{new}", s["id"])   # la card dice «sale del #n» y la manager se entera
            now_ = now()
            for c in prs:
                db.link_pr(c["url"], new)
                for dev in (s["id"], new):
                    db.event(now_, "ide", "pr-moved", dev=dev, pr_url=c["url"],
                             data={"from": s["id"], "to": new, "note": "línea paralela: desarrollo nuevo"})
            urls = {c["url"] for c in prs}
            free = (f"\n\nLa rama `{top['head']}` sigue tomada en `{busy}` (de la sesión `{s['id']}`), así que este "
                    f"desarrollo todavía no tiene worktree de {top['repo']}. Cuando se libere: "
                    f"`ide repo add {top['repo']} --branch {top['head']}`.") if busy else ""
            (session_path(root, new) / "SESSION.md").write_text(
                f"---\nstatus: developing\ntitle: {top['title']} (sale del #{n})\n---\n## Origen\n\n"
                f"Línea paralela de {top['repo']} ({nums}) que se separó sola del desarrollo **#{n}** (sesión "
                f"`{s['id']}`): un desarrollo tiene una sola línea por repo. El contexto está en "
                f"`../{s['id']}/SESSION.md`.{free}\n", encoding="utf-8")
            if busy:
                later_mod.add(db, f"s:{s['id']}", f"La rama {top['head']} pasó al desarrollo nuevo `{new}`",
                              f"{nums} se separó a `{new}` (línea paralela), pero la rama sigue en tu worktree "
                              f"`{busy}`. Sácala de ahí (`git worktree remove`) para que `{new}` la tome con "
                              f"`ide repo add {top['repo']} --branch {top['head']}`.", "ide")
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


def _in_worktree(wt: Path, branch: str | None) -> bool:
    """¿La rama (local o de origin) ya está contenida en la rama del worktree? (git, sin esperar a GitHub)"""
    import subprocess
    if not branch or not wt.exists():
        return False
    for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):
        try:
            r = subprocess.run(["git", "-C", str(wt), "merge-base", "--is-ancestor", ref, "HEAD"],
                               capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if r.returncode == 0:
            return True
    return False


def link_prs(db: Db, sessions: list[dict], gh: dict) -> bool:
    """Recuerda qué PRs tuyas están en la rama de un worktree de cada sesión de ticket (también uno
    extra suyo, salvo las líneas paralelas): quedan en ese desarrollo aunque después el worktree cambie
    de rama. Devuelve si agregó alguna."""
    links = db.dev_prs()
    idx = db.with_prefix("devidx:")
    me = gh.get("me")
    mine = [c for lst in (gh.get("mine") or {}).values() for c in lst]
    added = False
    for s in sessions:
        if s.get("kind") != "ticket":
            continue
        for c in mine:
            if c["url"] in links:
                continue
            if _on_branch(c, s, me, idx.get(f"s:{s['id']}")):
                db.link_pr(c["url"], s["id"])
                links[c["url"]] = {"sid": s["id"]}
                added = True
    return added


def _belongs(c: dict, s: dict, links: dict[str, dict], me: str | None = None, n: int | None = None) -> bool:
    """La PR es del desarrollo de la sesión: vinculada (y no sacada), o en la rama de un worktree
    si no está vinculada a otra sesión ni sacada de esta."""
    link = links.get(c["url"])
    if link:
        return link["sid"] == s["id"] and not link.get("out")
    return _on_branch(c, s, me, n)


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


def github_phase(prs: list[dict], merged: int) -> str | None:
    """La fase según GitHub (la misma regla que la card, `githubPhase` de ui/.../devStates.ts): mergeado si no
    quedan abiertas y hay mergeadas; si no, la peor de las que cuentan (fuera de draft, o en draft con
    revisores o revisión)."""
    if not prs:
        return "merged" if merged else None
    open_ = [p for p in prs if not p.get("draft") or p.get("review") or p.get("reviewers")]
    if not open_:
        return None
    if any(p.get("review") == "changes" for p in open_):
        return "changes-requested"
    if any(not p.get("review") and not p.get("reviewers") for p in open_):
        return "testing"
    if any(p.get("review") != "approved" for p in open_):
        return "in-review"
    return "approved"


def effective_state(db: Db, key: str, row_status: str | None, prs: list[dict], merged: int) -> str:
    """El estado que muestra la card (`devStateOf`): el bloqueo si hay; si no, la fase puesta a mano mientras
    GitHub siga en la de ese momento, o la de GitHub, o la puesta, o la deducida."""
    cur = _state(db, key, row_status)
    manual = cur.get("phase") if cur.get("phase") in PHASES else None
    block = cur.get("block") if cur.get("block") in BLOCKS else None
    gh = github_phase(prs, merged)
    pinned = bool(manual) and "gh" in cur and cur.get("gh") == gh
    stale = manual == "investigating" and bool(prs) and not pinned
    phase = (manual if pinned else gh or (None if stale else manual)) or ("developing" if prs else "investigating")
    return block or phase


def _ticket(db: Db, row: dict, open_prs: list, merged: int) -> dict | None:
    """El ticket de Notion de un desarrollo de ticket: Status (de la caché), los de pendientes, y si no calza
    con el desarrollo (`mismatch`). None para los que no llevan ticket (revisiones, manager…)."""
    if row.get("kind") != "ticket":
        return None
    from ide_server import notion_tickets as notion
    info = notion.cached(db, row.get("notionUrl")) or {}
    st = info.get("status")
    mismatch = None
    if st and not open_prs and merged and st in ("Backlog", "In progress", "PR Review"):
        mismatch = f"sus PRs están mergeadas y el ticket sigue en «{st}»"
    elif st == "Backlog" and open_prs:
        mismatch = "tiene PRs abiertas y el ticket sigue en «Backlog»"
    return {"url": row.get("notionUrl"), "status": st, "error": info.get("error"), "mismatch": mismatch,
            "pending": [],                      # los de pendientes ahora son subtickets
            "subs": [{"url": u, "status": (notion.cached(db, u) or {}).get("status"),
                      "title": (notion.cached(db, u) or {}).get("title")}
                     for u in notion.subs(db, row["id"], row.get("notionUrl"))]}


# lo que pasó en una PR después de que la sesión te dejó esperando y que deja viejo su último mensaje
# (no cuentan los saltos automáticos de estado: van y vuelven solos varias veces por hora)
_OUTDATING = {("ide", "review-approve"), ("github", "review"), ("github", "merged"), ("github", "closed")}


def _local(at: str) -> datetime | None:
    """La hora local (naive) de un evento: los de GitHub vienen en UTC (`Z`), los del IDE en hora local."""
    try:
        d = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def outdated_wait(db: Db, activity: dict | None, urls: set[str], me: str | None = None) -> dict | None:
    """Si la sesión te espera pero después de su último mensaje aprobaste / pidieron cambios / se mergeó o
    cerró alguna de sus PRs: {"what": qué pasó, "at": HH:MM}. Si no, None."""
    if not activity or activity.get("state") != "waiting" or activity.get("reason") == "launch" or not urls:
        return None
    since = _local(str(activity.get("since") or ""))
    if since is None:
        return None
    for e in db.events(pr_urls=sorted(urls), limit=60):     # el más nuevo primero
        if (e["actor"], e["kind"]) not in _OUTDATING:
            continue
        at = _local(e["at"])
        if at is None or at <= since:
            continue
        m = re.search(r"/([^/]+)/pull/(\d+)", e["prUrl"] or "")
        ref = f"{m.group(1).removeprefix('finnecto-')}#{m.group(2)}" if m else "una PR"
        d = e["data"] or {}
        if e["kind"] == "review-approve":
            what = f"aprobaste {ref}"
        elif e["kind"] == "review":
            mine = bool(me) and d.get("by") == me
            verb = {"approved": ("aprobaste", "aprobó"), "changes": ("pediste cambios en", "pidió cambios en")}.get(
                d.get("state"), ("revisaste", "revisó"))
            what = f"{verb[0]} {ref}" if mine else f"{d.get('by') or 'alguien'} {verb[1]} {ref}"
        else:
            what = f"se {'mergeó' if e['kind'] == 'merged' else 'cerró'} {ref}"
        return {"what": what, "at": at.strftime("%H:%M")}
    return None


def session_pr_urls(db: Db, s: dict, prs: list[dict] | None = None) -> set[str]:
    """Las PRs de una sesión: la suya, las de su stack, las enlazadas (también mergeadas) y las de su card."""
    urls = {u for u in [s.get("prUrl"), *(s.get("stackPrs") or [])] if u}
    urls |= {u for u, l in db.dev_prs().items() if l.get("sid") == s["id"] and not l.get("out")}
    urls |= {p["url"] for p in prs or [] if p.get("url")}
    return urls


def list_devs(root: Path, db: Db, sessions: list[dict], gh: dict) -> list[dict]:
    """Todos los desarrollos: los de sesión (estado de la base) y los que son solo PRs."""
    cards = _cards(gh)
    names = db.dev_names()
    links = db.dev_prs()
    by_sid = {s["id"]: s for s in sessions}
    me = gh.get("me")
    idx = db.with_prefix("devidx:")
    taken: set[str] = set()
    merged_by_sid: dict[str, int] = {}
    for u, c in db.with_prefix("prclosed:").items():
        if c.get("merged") and (links.get(u) or {}).get("sid") and not links[u].get("out"):
            merged_by_sid[links[u]["sid"]] = merged_by_sid.get(links[u]["sid"], 0) + 1
    out = []
    for row in db.devs():
        s = by_sid.get(row["id"])
        if s is None:                           # su sesión ya no está en disco (la próxima sync la cierra)
            continue
        if s.get("stackPrs"):                   # revisión de varias PRs (stack o movidas ahí)
            prs = [cards[u] for u in s["stackPrs"] if u in cards]
        elif row.get("prUrl"):
            prs = [cards[row["prUrl"]]] if row["prUrl"] in cards else []
        else:
            prs = [c for c in cards.values() if _belongs(c, s, links, me, idx.get(f"s:{row['id']}"))]
            stacks = {c["stack"]["id"] for c in prs if c.get("stack")}
            # el stack trae a sus compañeras, salvo las asignadas a otro desarrollo o sacadas (el stack
            # es lo último en la precedencia: explícita > pegajosa > por rama > stack)
            prs += [c for c in cards.values() if c.get("stack") and c["stack"]["id"] in stacks
                    and c.get("author") == f"@{me}" and c not in prs
                    and not (links.get(c["url"]) and (links[c["url"]]["sid"] != row["id"] or links[c["url"]].get("out")))]
        taken |= {c["url"] for c in prs}
        outdated = outdated_wait(db, s.get("activity"), session_pr_urls(db, s, prs), me) \
            if s.get("process") == "running" else None
        out.append({"id": row["id"], "kind": row["kind"], "name": _name(names, f"s:{row['id']}", prs),
                    "title": row["title"],
                    # el de la card (sale de GitHub); `stored`: el guardado en la base
                    "status": effective_state(db, f"s:{row['id']}", row["status"], [_pr_summary(c) for c in prs],
                                              merged_by_sid.get(row["id"], 0)) if row["kind"] == "ticket" else row["status"],
                    "stored": row["status"],
                    "notionUrl": row["notionUrl"], "ticket": _ticket(db, row, prs, merged_by_sid.get(row["id"], 0)),
                    "process": s.get("process"),
                    # trabajando / esperando al usuario (hooks de claude), con la 1ª línea de su último mensaje
                    "activity": ("outdated" if outdated else (s.get("activity") or {}).get("state"))
                    if s.get("process") == "running" else None,
                    # te esperaba, pero después pasó algo en sus PRs (aprobada, mergeada…): su mensaje quedó viejo
                    "activityOutdated": outdated,
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
    hidden = set(db.hidden_devs())
    for d in devs:
        d["index"] = idx.get(_ui_key(d)) or next((idx[k] for k in _alt_keys(d["prs"]) if k in idx), None)
        d["key"] = _ui_key(d)
        d["hidden"] = d["key"] in hidden
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
        if d["kind"] in ("main", "ide", "recursos", "plugins"):
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
        if info.get("kind") in (None, "main", "ide", "recursos", "plugins"):
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


def dev_relations(db: Db, sessions: list[dict], devs: list[dict]) -> dict[str, list[dict]]:
    """`s:<id>` → avisos de que ese desarrollo cuelga de otro: `ticket` (el mismo ticket de Notion que otro
    desarrollo abierto), `stacked` (una PR suya apilada sobre una rama de otro desarrollo) y `split` (el IDE
    lo separó de otro como línea paralela). Cada uno: {kind, dev (id de la otra sesión), n (su número)}."""
    idx = db.with_prefix("devidx:")
    tickets = {s["id"]: s for s in sessions if s.get("kind") == "ticket"}
    out: dict[str, list[dict]] = {}

    def add(sid: str, kind: str, other: str, **extra) -> None:
        if other == sid or other not in tickets:
            return
        rel = {"kind": kind, "dev": other, "n": idx.get(f"s:{other}"), **extra}
        if rel not in out.setdefault(f"s:{sid}", []):
            out[f"s:{sid}"].append(rel)

    def ticket_id(url: str | None) -> str | None:
        m = re.search(r"[0-9a-f]{32}", (url or "").replace("-", ""))
        return m.group(0) if m else None

    by_ticket: dict[str, list[str]] = {}
    for s in tickets.values():
        if t := ticket_id((s.get("meta") or {}).get("notion_url")):
            by_ticket.setdefault(t, []).append(s["id"])
    for ids in by_ticket.values():
        for a in ids:
            for b in ids:
                add(a, "ticket", b)
    # de quién es cada rama: las de sus PRs y las de sus worktrees
    owner: dict[tuple, str] = {}
    for s in tickets.values():
        for r in s.get("repos") or []:
            if r.get("branch"):
                owner[(r["name"], r["branch"])] = s["id"]
    for d in devs:
        if d["id"] in tickets:
            for c in d.get("prs") or []:
                if c.get("head"):
                    owner.setdefault((c.get("repo"), c["head"]), d["id"])
    for d in devs:
        if d["id"] not in tickets:
            continue
        for c in d.get("prs") or []:
            o = owner.get((c.get("repo"), c.get("base")))
            if o and o != d["id"]:
                add(d["id"], "stacked", o, pr=f"{c.get('repo')}#{c.get('number')}")
    for k, origin in db.with_prefix("splitfrom:").items():
        add(k, "split", origin)
    return out
