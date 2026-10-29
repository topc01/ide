"""Subcomandos `ide session|repo|script`. Disco in-process; procesos vía HTTP al server."""
from __future__ import annotations
import argparse
import json
import re
import sys
from urllib.parse import quote
from pathlib import Path
from typing import TextIO
import httpx
from ide_server import instances, seeds
from ide_server.devs import STATUSES
from ide_server.handoff import handoff
from ide_server.push import push
from ide_server.repos_fs import add_repo, rm_repo, require_session
from ide_server.scripts import run_script
from ide_server.session_ops import delete_session
from ide_server.sessions_fs import SessionError, list_sessions, normalize_id, repo_links, sessions_dir
from ide_server.workspace import find_workspace_root
from ide_server.worktrees import BranchOccupied, WorktreeError

NO_SERVER = "No hay `ide run` activo para este workspace (levántalo con `ide run`)."
TIMEOUT = "el server no respondió a tiempo (¿sigue procesando?)"


def find_server_url(root: Path, env: dict, home: Path) -> str | None:
    if env.get("IDE_URL"):
        return env["IDE_URL"]
    for inst in instances.list_instances(home):
        if Path(inst.get("workspace", "")).resolve() == root.resolve():
            return inst["url"]
    return None


def current_session(root: Path, *, env: dict, cwd: Path, explicit: str | None = None) -> str:
    if explicit:
        return normalize_id(explicit)
    if env.get("IDE_SESSION_ID"):
        return env["IDE_SESSION_ID"]
    sdir, wdir = sessions_dir(root).resolve(), (root / ".ide" / "worktrees").resolve()
    for p in [cwd.resolve(), *cwd.resolve().parents]:
        if p.parent in (sdir, wdir):
            return p.name
    raise SessionError("no_session", "no estoy dentro de una sesión: usa --session <id>")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ide")
    sub = ap.add_subparsers(dest="group", required=True)
    s = sub.add_parser("session").add_subparsers(dest="cmd", required=True)
    new = s.add_parser("new")
    new.add_argument("--id"); new.add_argument("--main", action="store_true")
    new.add_argument("--title"); new.add_argument("--template")
    new.add_argument("--var", action="append", default=[])
    new.add_argument("--prompt"); new.add_argument("--prompt-file")
    new.add_argument("--permissions", choices=["analyze", "full", "default"])
    new.add_argument("--review")
    new.add_argument("--notion", help="URL del ticket en Notion (deriva el id: n-<8 hex>)")
    new.add_argument("--vars-file", help="JSON con variables de la plantilla ('-' = stdin)")
    new.add_argument("--if-missing", action="store_true", help="si ya existe, no hace nada")
    new.add_argument("--dry-run", action="store_true", help="valida y muestra, sin crear")
    ls = s.add_parser("ls"); ls.add_argument("--json", action="store_true")
    for name in ("open", "stop"):
        s.add_parser(name).add_argument("id")
    rm = s.add_parser("rm"); rm.add_argument("id"); rm.add_argument("--force", action="store_true")
    sd = s.add_parser("send", help="encola un prompt a la sesión de un desarrollo (id o #número)")
    sd.add_argument("id"); sd.add_argument("--prompt"); sd.add_argument("--prompt-file", help="'-' = stdin")
    rs = s.add_parser("review-stack", help="una sesión que revisa un stack de PRs que te pidieron revisar (de abajo hacia arriba)")
    rs.add_argument("urls", nargs="+", help="URLs de las PRs; con una sola, todas las pendientes de su stack")
    sp = s.add_parser("propose", help="propone por Telegram mandarle un prompt a una sesión (se manda con tu Sí)")
    sp.add_argument("id"); sp.add_argument("--prompt"); sp.add_argument("--prompt-file", help="'-' = stdin")
    r = sub.add_parser("repo").add_subparsers(dest="cmd", required=True)
    ra = r.add_parser("add"); ra.add_argument("repo"); ra.add_argument("--branch")
    ra.add_argument("--session")
    db = sub.add_parser("db", help="una consulta de solo lectura a la base de prod o staging (vía db-connect.sh)")
    db.add_argument("env", choices=("prod", "staging")); db.add_argument("sql", help="la consulta SQL (sin comandos de psql: nada con \\\\)")
    pr_ = sub.add_parser("procs", help="qué consume el computador y de qué desarrollo es (servidores, contenedores, claude)")
    pr_.add_argument("--json", action="store_true")
    prs_ = pr_.add_subparsers(dest="cmd")
    prs_.add_parser("stop", help="corta un servidor o contenedores del IDE por su id de `ide procs`").add_argument("id")
    br = sub.add_parser("browser", help="perfiles de navegador del workspace: uno por cuenta, todos abiertos a la vez").add_subparsers(dest="cmd", required=True)
    br.add_parser("ls")
    bn = br.add_parser("new"); bn.add_argument("name"); bn.add_argument("url", help="donde inicia sesión (p.ej. http://localhost:5173 o https://tech.finnecto.com)")
    bn.add_argument("--note", default="", help="qué cuenta es (p.ej. 'aprobador de Acme, usuario juan@…')")
    br.add_parser("rm").add_argument("name")
    br.add_parser("login", help="abre la ventana para iniciar sesión; al cerrarla se guarda").add_argument("name")
    up = sub.add_parser("update", help="pone al día tu rama sobre su base SOLO si hay conflicto o su madre del stack se mergeó")
    up.add_argument("repo", nargs="?", help="solo este repo (sin él: todos los de la sesión)")
    up.add_argument("--dry-run", action="store_true", help="solo dice qué haría")
    up.add_argument("--session")
    pu = sub.add_parser("push", help="sube a origin la rama de cada worktree de la sesión (sin cd; nunca la principal)")
    pu.add_argument("repo", nargs="?", help="solo este repo (sin él: todos los de la sesión)")
    pu.add_argument("--branch", action="append", help="otra rama local del repo en vez de la actual (repetible; p.ej. las de un stack)")
    pu.add_argument("--force", action="store_true", help="--force-with-lease (después de un rebase)")
    pu.add_argument("--session")
    st = sub.add_parser("status", help="cambia el estado de la sesión (queda en la base y en el historial)")
    st.add_argument("status"); st.add_argument("-m", "--note"); st.add_argument("--session")
    ev = sub.add_parser("evidencias", help="pasos de prueba con capturas (módulo Evidencias)").add_subparsers(dest="cmd", required=True)
    es = ev.add_parser("set", help="crea una corrida con los pasos (markdown: un ítem de lista por paso; 📸 o [captura] = lleva captura)")
    es.add_argument("--label", default="PR"); es.add_argument("--file", default="-", help="markdown ('-' = stdin)")
    es.add_argument("--session")
    el = ev.add_parser("ls", help="las corridas con sus pasos y capturas"); el.add_argument("--json", action="store_true")
    el.add_argument("--session")
    eh = ev.add_parser("shot", help="adjunta captura(s) a un paso (lo marca hecho)")
    eh.add_argument("step", type=int, help="número del paso (1, 2, …)"); eh.add_argument("files", nargs="+")
    ed = ev.add_parser("done", help="marca un paso como hecho (sin captura)")
    ed.add_argument("step", type=int); ed.add_argument("--undo", action="store_true", help="desmarcarlo")
    for x in (eh, ed):
        x.add_argument("--label", help="corrida por su nombre (default: la última)"); x.add_argument("--session")
    sub.add_parser("hook", help="(lo llaman los hooks de claude) le avisa al IDE si la sesión trabaja o te espera")
    lt = sub.add_parser("later", help="pendientes para después (preguntas/temas que el usuario verá otro día)").add_subparsers(dest="cmd", required=True)
    la = lt.add_parser("add", help="deja un pendiente en el desarrollo de la sesión")
    la.add_argument("text"); la.add_argument("-m", "--context", help="contexto: qué se necesita y por qué")
    la.add_argument("--session")
    ll = lt.add_parser("ls", help="pendientes abiertos de todos los desarrollos")
    ll.add_argument("--json", action="store_true"); ll.add_argument("--all", action="store_true", help="también respondidos/descartados")
    ll.add_argument("--mine", action="store_true", help="solo los del desarrollo de esta sesión")
    ld = lt.add_parser("done", help="marca un pendiente como resuelto (p.ej. se resolvió en el chat)")
    ld.add_argument("id"); ld.add_argument("-m", "--note", help="cómo se resolvió")
    sv = sub.add_parser("server", help="servidores de tu desarrollo por bloque (stack de un repo), como el módulo Servidores").add_subparsers(dest="cmd", required=True)
    sl = sv.add_parser("ls", help="bloques: PRs, rama, dónde corre, scripts y su estado"); sl.add_argument("--json", action="store_true")
    ss = sv.add_parser("start", help="corre un script de un bloque (crea el worktree aparte si hace falta)")
    ss.add_argument("block", help="una PR del bloque (api#4897) o el repo (admin) si tiene un solo bloque"); ss.add_argument("script")
    ss.add_argument("--api", help="front: el bloque de la api a la que apunta (default: la de su dependencia)")
    ss.add_argument("--no-api", action="store_true", help="front: la api de su .env.local")
    st_ = sv.add_parser("stop", help="para un script de un bloque"); st_.add_argument("block"); st_.add_argument("script")
    sg = sv.add_parser("log", help="lo último del log de un script"); sg.add_argument("block"); sg.add_argument("script")
    sg.add_argument("-n", "--lines", type=int, default=60)
    for x in (sl, ss, st_, sg):
        x.add_argument("--dev", help="otro desarrollo (#n o id); default: el de tu sesión")
    dp = sub.add_parser("dep", help="dependencias entre PRs (además de la sección ## Dependencias)").add_subparsers(dest="cmd", required=True)
    da = dp.add_parser("add", help="la PR depende de estas"); da.add_argument("pr"); da.add_argument("deps", nargs="+")
    dr = dp.add_parser("rm", help="saca dependencias agregadas en el IDE")
    dr.add_argument("pr"); dr.add_argument("deps", nargs="+")
    dr.add_argument("--ignore", action="store_true", help="también ignorar las que declara la descripción")
    dl = dp.add_parser("ls", help="dependencias directas de la PR y de dónde salen"); dl.add_argument("pr")
    dl.add_argument("--json", action="store_true")
    dv = sub.add_parser("dev").add_subparsers(dest="cmd", required=True)
    dls = dv.add_parser("ls"); dls.add_argument("--json", action="store_true")
    dsh = dv.add_parser("show"); dsh.add_argument("id"); dsh.add_argument("--json", action="store_true")
    for name, what in (("link", "asigna PRs a un desarrollo (pisa la asignación que tuvieran)"),
                       ("unlink", "saca PRs de un desarrollo (no vuelven por rama hasta un link)")):
        x = dv.add_parser(name, help=what)
        x.add_argument("id", help="desarrollo: #n o id de sesión"); x.add_argument("prs", nargs="+", help="URL o repo#n")
    rr = r.add_parser("rm"); rr.add_argument("repo"); rr.add_argument("--force", action="store_true")
    rr.add_argument("--session")
    ho = sub.add_parser("handoff", help="traspasa un worktree de otra herramienta (Conductor) a una sesión del IDE")
    ho.add_argument("--from", dest="src", help="raíz del worktree a traspasar (se MUEVE al IDE)")
    ho.add_argument("--notion", help="id (32 hex) o URL del ticket: si hay sesión de ese ticket, se agrega ahí")
    ho.add_argument("--title", help="título de la sesión nueva (o la primera línea '# …' del resumen)")
    ho.add_argument("--session", help="sesión del IDE que lo recibe (si no: la del ticket o una nueva)")
    ho.add_argument("--status", help="estado inicial: " + " | ".join(STATUSES["ticket"]))
    ho.add_argument("--summary-file", help="resumen de traspaso en markdown ('-' = stdin)")
    ho.add_argument("--force", action="store_true", help="mover aunque haya procesos corriendo desde ahí")
    ho.add_argument("--install-skill", action="store_true",
                    help="instala la skill /ide-handoff en ~/.claude/skills (para las sesiones de Conductor)")
    rp = sub.add_parser("reply", help="la principal le responde al usuario por Telegram")
    rp.add_argument("text", nargs="?"); rp.add_argument("--prompt-file", help="'-' = stdin")
    tg = sub.add_parser("telegram", help="conectar Telegram con la sesión manager").add_subparsers(dest="cmd", required=True)
    tg.add_parser("setup", help="guarda el token del bot en el llavero y da el código para vincular tu chat")
    tg.add_parser("status")
    fb = sub.add_parser("feedback", help="revisión de feedback (sesión manager)").add_subparsers(dest="cmd", required=True)
    fc = fb.add_parser("collect", help="correcciones anotadas + mensajes del usuario de cada sesión desde --since")
    fc.add_argument("--since", help="ISO (AAAA-MM-DD[THH:MM]); default: hace 7 días"); fc.add_argument("--json", action="store_true")
    fb.add_parser("run", help="pedirle ya la revisión nocturna a la sesión principal")
    sc = sub.add_parser("script"); sc.add_argument("name"); sc.add_argument("repo", nargs="?")
    sc.add_argument("--session")
    return ap


def _read_vars_file(path: str) -> dict:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionError("bad_vars_file", f"no se pudo leer --vars-file: {exc}")
    if not isinstance(data, dict):
        raise SessionError("bad_vars_file", "--vars-file debe ser un objeto JSON {\"clave\": \"valor\"}")
    return {str(k): "" if v is None else str(v) for k, v in data.items()}


def _new_payload(a, env: dict) -> dict:
    body: dict = {}
    if env.get("IDE_SESSION_ID"):                # lo pide una sesión: el server valida permisos
        body["caller"] = env["IDE_SESSION_ID"]
    for key in ("id", "title", "template", "permissions", "review", "notion"):
        if getattr(a, key):
            body[key] = getattr(a, key)
    for flag in ("main", "if_missing", "dry_run"):
        if getattr(a, flag):
            body[flag] = True
    variables = _read_vars_file(a.vars_file) if a.vars_file else {}
    if a.var:
        bad = [v for v in a.var if "=" not in v]
        if bad:
            raise SessionError("bad_var", f"--var debe ser k=v (recibido: {', '.join(bad)})")
        variables.update(v.split("=", 1) for v in a.var)
    if variables:
        body["vars"] = variables
    if a.prompt_file:
        try:
            body["prompt"] = Path(a.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise SessionError("bad_prompt_file", f"no se pudo leer --prompt-file: {exc}")
    elif a.prompt:
        body["prompt"] = a.prompt
    return body


def _post(http, url: str | None, path: str, body: dict | None = None, *,
          timeout: float = 120) -> dict:
    if url is None:
        raise SessionError("no_server", NO_SERVER)
    try:
        r = http.post(f"{url}{path}", json=body or {}, timeout=timeout)
    except httpx.TimeoutException:
        raise SessionError("timeout", TIMEOUT)
    except httpx.HTTPError:
        raise SessionError("no_server", NO_SERVER)
    try:
        data = r.json()
    except ValueError:
        raise SessionError("server_error", f"respuesta inválida del server (HTTP {r.status_code})")
    if r.status_code >= 400:
        raise SessionError(data.get("code", "server_error"), data.get("message", str(data)))
    return data


def _get(http, url: str | None, path: str, *, timeout: float = 60) -> dict:
    if url is None:
        raise SessionError("no_server", NO_SERVER)
    try:
        r = http.get(f"{url}{path}", timeout=timeout)
    except httpx.TimeoutException:
        raise SessionError("timeout", TIMEOUT)
    except httpx.HTTPError:
        raise SessionError("no_server", NO_SERVER)
    try:
        data = r.json()
    except ValueError:
        raise SessionError("server_error", f"respuesta inválida del server (HTTP {r.status_code})")
    if r.status_code >= 400:
        raise SessionError(data.get("code", "server_error"), data.get("message", str(data)))
    return data


def _pr_line(p: dict) -> str:
    stack = f" ◫{p['stack']['position']}/{p['stack']['size']}" if p.get("stack") else ""
    who = ", ".join(f"{r['login']}:{r['state']}" for r in p.get("reviewers") or [])
    deps = f" ⏸{p['depsPending']}" if p.get("depsPending") else ""
    return (f"    {p['repo']}#{p['number']}{stack} review={p.get('review') or '-'} ci={p.get('ci') or '-'}"
            f"{' draft' if p.get('draft') else ''}{deps}  {p['title']}" + (f"  de {p['author']}" if p.get("author") else "")
            + (f"  [{who}]" if who else ""))


def _evidence_cmd(a, root: Path, url: str | None, http, out: TextIO, env: dict) -> int:
    from urllib.parse import quote
    sid = a.session or env.get("IDE_SESSION_ID")
    if not sid:
        raise SessionError("no_session", "no estoy dentro de una sesión: usa --session <id>")
    path = f"/api/sessions/{quote(normalize_id(sid), safe='')}/evidence"
    if a.cmd == "set":
        try:
            md = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise SessionError("bad_file", f"no se pudo leer --file: {exc}")
        run = _post(http, url, path, {"label": a.label, "markdown": md})["run"]
        out.write(f"{run['id']}\t{run['label']}\t{len(run['steps'])} pasos\n")
        if not run["steps"]:
            out.write("aviso: no encontré pasos (un ítem de lista por paso: '1. …' o '- …')\n")
        return 0
    runs = _get(http, url, path)["runs"]
    if a.cmd in ("shot", "done"):
        pick = [r for r in runs if not a.label or r["label"].lower() == a.label.lower()]
        if not pick:
            raise SessionError("not_found", f"no hay corrida {a.label!r}" if a.label else "no hay evidencias: ide evidencias set")
        run = pick[-1]
        if not 1 <= a.step <= len(run["steps"]):
            raise SessionError("bad_request", f"la corrida {run['label']} tiene {len(run['steps'])} pasos")
        step = run["steps"][a.step - 1]
        if a.cmd == "done":
            step["done"] = not a.undo
            _post(http, url, path + "/save", {"run": run})
            out.write(f"{run['label']}\tpaso {a.step}\t{'hecho' if step['done'] else 'pendiente'}\n")
            return 0
        import base64
        for f in a.files:
            try:
                raw = Path(f).read_bytes()
            except OSError as exc:
                raise SessionError("bad_file", f"no se pudo leer {f}: {exc}")
            _post(http, url, path + "/shot", {"run": run["id"], "step": step["id"], "name": Path(f).name,
                                              "data": base64.b64encode(raw).decode()}, timeout=120)
            out.write(f"{run['label']}\tpaso {a.step}\t{Path(f).name}\n")
        return 0
    if a.json:
        out.write(json.dumps(runs, ensure_ascii=False, indent=2) + "\n")
        return 0
    att = root / ".ide" / "sessions" / normalize_id(sid) / "attachments"
    for r in runs:
        out.write(f"# {r['label']} ({r['id']})\n")
        for n, st in enumerate(r["steps"], 1):
            out.write(f"{n}. [{'x' if st['done'] else ' '}] {st['title']}\n")
            for shot in st["shots"]:
                out.write(f"     {att / shot}\n")
    if not runs:
        out.write("(sin evidencias)\n")
    return 0


def _server_cmd(a, url: str | None, http, out: TextIO, env: dict) -> int:
    from urllib.parse import quote
    dev = a.dev or env.get("IDE_SESSION_ID")
    if not dev:
        raise SessionError("no_session", "no estoy dentro de una sesión: usa --dev <#n|id>")
    base = f"/api/devs/{quote(dev, safe='')}/servers"
    if a.cmd == "ls":
        bl = _get(http, url, base)["blocks"]
        if a.json:
            out.write(json.dumps(bl, ensure_ascii=False, indent=2) + "\n")
            return 0
        for b in bl:
            where = {"session": "worktree de la sesión", "pr": "worktree aparte" if b["exists"] else "worktree aparte (se crea al correr)"}[b["where"]]
            out.write(f"{b['name']}\t{b.get('chain') or ' → '.join(b['prs']) or 'sin PR'}\trama {b['branch'] or '?'}\t{where}"
                      + (f"\tapi: {b['api'] or 'su .env.local'}" if b["front"] else "") + "\n")
            for sc in b["scripts"]:
                st = sc.get("state") or "sin correr"
                if st == "exited":
                    st = "terminó" if sc.get("exitCode") == 0 else f"falló (exit {sc.get('exitCode')})"
                if sc.get("error"):
                    st = f"error: {sc['error']}"
                out.write(f"    {sc['name']:<10} {st}" + (f"  {' '.join(sc['urls'])}" if sc.get("urls") and sc.get("state") == "running" and not sc.get("error") else "") + "\n")
        if not bl:
            out.write("(sin bloques: el desarrollo no tiene repos ni PRs)\n")
        return 0
    body = {"block": a.block, "name": a.script}
    if a.cmd == "start":
        body.update(api=a.api, noApi=a.no_api)
    if a.cmd == "log":
        body["lines"] = a.lines
    d = _post(http, url, f"{base}/{a.cmd}", body, timeout=600)
    if a.cmd == "log":
        r = d.get("run") or {}
        out.write(f"# {d['block']} {a.script}: {r.get('state') or 'sin correr'}\n{d['log']}\n")
    elif a.cmd == "start":
        out.write(f"{d['block']}\t{a.script}\tcorriendo en {d['place']} (rama {d['branch'] or '?'})"
                  + (f"\tapi: {d['api']}" if d.get("api") else "") + "\n"
                  + f"log: ide server log {d['block']} {a.script}\n")
    else:
        out.write(f"{d['block']}\t{a.script}\t{(d.get('run') or {}).get('state')}\n")
    return 0


def _dep_cmd(a, url: str | None, http, out: TextIO, env: dict) -> int:
    from urllib.parse import quote
    actor = f"claude:{env['IDE_SESSION_ID']}" if env.get("IDE_SESSION_ID") else "cli"
    if a.cmd == "ls":
        d = _get(http, url, f"/api/deps?pr={quote(a.pr, safe='')}")
    else:
        d = _post(http, url, f"/api/deps/{a.cmd}", {"pr": a.pr, "deps": a.deps, "actor": actor,
                                                    "ignore": bool(getattr(a, "ignore", False))})
    if getattr(a, "json", False):
        out.write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
        return 0
    short = lambda u: re.sub(r"^https://github\.com/[^/]+/([^/]+)/pull/(\d+)$", r"\1#\2", u)  # noqa: E731
    out.write(f"{short(d['pr'])} depende de:\n")
    for u in d["effective"]:
        src = "descripción" if u in d["description"] else "ide"
        out.write(f"  {short(u)}\t({src})\n")
    for u in d["ignored"]:
        out.write(f"  {short(u)}\t(ignorada: está en la descripción)\n" if u in d["description"] else f"  {short(u)}\t(ignorada)\n")
    if not d["effective"] and not d["ignored"]:
        out.write("  (ninguna)\n")
    if a.cmd == "rm" and not a.ignore:
        left = [u for u in a_urls(d, a.deps) if u in d["description"] and u not in d["ignored"]]
        if left:
            out.write("aviso: " + ", ".join(short(u) for u in left) + " sigue en la descripción de la PR: "
                      "para que el IDE la ignore, `ide dep rm … --ignore`\n")
    if not d.get("known"):
        out.write("aviso: no conozco esa PR abierta (no leí su descripción)\n")
    return 0


def a_urls(d: dict, raw: list[str]) -> list[str]:
    """Las URLs de `raw` (URL o repo#n) que aparecen en las listas de `d`."""
    every = [*d["description"], *d["added"], *d["ignored"]]
    out = []
    for r in raw:
        m = re.fullmatch(r"([\w.-]+)#(\d+)", r.strip())
        out += [u for u in every if (m and u.endswith(f"/{m.group(1)}/pull/{m.group(2)}")) or u == r.strip()]
    return out


def _hook(url: str | None, http, env: dict) -> int:
    """Hook de Claude Code: lee el evento por stdin y se lo pasa al IDE. Nunca falla (exit 0): un hook
    que falla molesta a claude."""
    from urllib.parse import quote
    try:
        sid = env.get("IDE_SESSION_ID")
        ev = json.loads(sys.stdin.read() or "{}")
        if ev.get("hook_event_name") == "UserPromptSubmit":
            # lo que imprime este hook le llega a claude como contexto: Claude Code le da la fecha pero
            # no la hora, y la adivina de lo que lee (GitHub y los logs vienen en UTC)
            import time as _time
            sys.stdout.write(f"Hora local del usuario: {_time.strftime('%H:%M del %a %d-%m-%Y')} "
                             f"({_time.strftime('%Z, UTC%z')}). Los horarios de GitHub, de los logs y de las "
                             "bases suelen venir en UTC: conviértelos a esta hora antes de mencionarlos.\n")
        if sid and url:
            http.post(f"{url}/api/sessions/{quote(sid, safe='')}/activity", timeout=3, json={
                "event": ev.get("hook_event_name"), "notification_type": ev.get("notification_type"),
                "message": ev.get("message"), "transcript_path": ev.get("transcript_path")})
    except Exception:  # noqa: BLE001
        pass
    return 0


def _later_cmd(a, url: str | None, http, out: TextIO, env: dict) -> int:
    if a.cmd == "add":
        sid = a.session or env.get("IDE_SESSION_ID")
        if not sid:
            raise SessionError("no_session", "no estoy dentro de una sesión: usa --session <id>")
        actor = f"claude:{env['IDE_SESSION_ID']}" if env.get("IDE_SESSION_ID") else "cli"
        data = _post(http, url, "/api/later", {"sid": sid, "text": a.text, "context": a.context, "actor": actor})
        out.write(f"pendiente {data['item']['id']} en {sid}\n")
        return 0
    if a.cmd == "done":
        from urllib.parse import quote
        actor = f"claude:{env['IDE_SESSION_ID']}" if env.get("IDE_SESSION_ID") else "cli"
        _post(http, url, f"/api/later/{quote(a.id, safe='')}/resolve", {"note": a.note, "actor": actor})
        out.write(f"{a.id}\tresuelto\n")
        return 0
    items = _get(http, url, "/api/later" + ("?all=true" if a.all else ""))["items"]
    if a.mine:
        sid = env.get("IDE_SESSION_ID")
        if not sid:
            raise SessionError("no_session", "--mine: no estoy dentro de una sesión")
        items = [it for it in items if it["key"] == f"s:{sid}"]
    if a.json:
        out.write(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
        return 0
    for it in items:
        out.write(f"{it['id']}\t{it['created'][:10]}\t{it['key']}\t{it['status']}\t{it['text']}"
                  + (f"\t({it['context']})" if it.get("context") else "") + "\n")
    if not items:
        out.write("(ninguno)\n")
    return 0


def _dev_cmd(a, url: str | None, http, out: TextIO, env: dict) -> int:
    from urllib.parse import quote
    if a.group == "status":
        sid = a.session or env.get("IDE_SESSION_ID")
        if not sid:
            raise SessionError("no_session", "no estoy dentro de una sesión: usa --session <id>")
        actor = f"claude:{env['IDE_SESSION_ID']}" if env.get("IDE_SESSION_ID") else "cli"
        data = _post(http, url, f"/api/devs/{quote(sid, safe='')}/status",
                     {"status": a.status, "note": a.note, "actor": actor})
        out.write(f"{sid}\t{data['dev']['status']}\n" + (f"{data['message']}\n" if data.get("message") else ""))
        return 0
    if a.cmd in ("link", "unlink"):
        body = {"prs": a.prs, "token": env.get("IDE_MANAGER_TOKEN", ""), "from_session": bool(env.get("IDE_SESSION_ID")),
                "actor": f"claude:{env['IDE_SESSION_ID']}" if env.get("IDE_SESSION_ID") else "cli"}
        data = _post(http, url, f"/api/devs/{quote(a.id, safe='')}/{a.cmd}", body)
        for m in data["moved"]:
            out.write(f"{m['pr']}\t{m['from']} → {m['to']}\n")
            if m.get("warning"):
                out.write(f"  aviso: {m['warning']}\n")
        return 0
    if a.cmd == "ls":
        devs = _get(http, url, "/api/devs")["devs"]
        if a.json:
            out.write(json.dumps(devs, ensure_ascii=False, indent=2) + "\n")
            return 0
        for d in devs:
            title = f"{d['name']} ({d['title']})" if d.get("name") else d["title"] or ""
            n = f"#{d['index']}" if d.get("index") else "-"
            proc = {"waiting": "TE ESPERA", "working": "trabajando"}.get(d.get("activity") or "", d["process"] or "-")
            out.write(f"{n}\t{d['id']}\t{d['kind']}\t{d['status'] or '-'}\t{proc}\t{title}\n")
            if d.get("activity") == "waiting" and d.get("activityNote"):
                out.write(f"    › {d['activityNote']}\n")
            for p in d["prs"]:
                out.write(_pr_line(p) + "\n")
        return 0
    d = _get(http, url, f"/api/devs/{quote(a.id, safe='')}")["dev"]
    if a.json:
        out.write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
        return 0
    out.write(f"{'#' + str(d['index']) + '  ' if d.get('index') else ''}{d['id']}  {d['kind']}  status={d['status'] or '-'}  claude={d['process'] or '-'}\n"
              + (f"nombre: {d['name']}\n" if d.get("name") else "") + f"{d['title'] or ''}\n")
    if d.get("notionUrl"):
        out.write(f"notion: {d['notionUrl']}\n")
    for r in d.get("repos") or []:
        out.write(f"  repo {r['name']} @ {r['branch'] or '(detached)'}\n")
    if d["prs"]:
        out.write("PRs:\n")
        for p in d["prs"]:
            out.write(_pr_line(p) + "\n")
            for x in p.get("deps") or []:
                if x.get("state") == "MERGED":
                    continue
                via = re.search(r"/([^/]+)/pull/(\d+)$", x.get("via") or "")
                via = f", vía {via.group(1)}#{via.group(2)}" if via else ""
                what = "va junto con" if x.get("together") else "⏸ espera a"
                out.write(f"      {what} {x['repo']}#{x['number']} ({x['state']}{via})\n")
    out.write("historial:\n")
    for e in d.get("events") or []:
        extra = " ".join(f"{k}={v}" for k, v in (e.get("data") or {}).items())
        out.write(f"  {e['at']}  {e['actor']:<16} {e['kind']:<10} {extra}\n")
    return 0


def _procs(a, root: Path, env, out: TextIO) -> int:
    from ide_server import procs
    caller = env.get("IDE_SESSION_ID")
    if a.cmd == "stop":
        if caller and caller != procs.RECURSOS:
            raise SessionError("forbidden", "solo la sesión Recursos (o el usuario desde su terminal) corta procesos")
        snap = procs.snapshot(root)
        row = next((r for r in snap["servers"] + snap["docker"] if r["id"] == a.id), None)
        if row is None:
            raise SessionError("unknown", f"{a.id} no está en `ide procs`")
        if caller and not row["abandoned"]:     # la sesión Recursos: solo lo abandonado
            raise SessionError("forbidden", f"{a.id} está en uso: no lo cortes, propónselo al usuario "
                                            "(él lo corta desde Servidores o con `ide procs stop` en su terminal)")
        # unos contenedores levantados por un servidor del IDE: se para el servidor (Servidores lo ve parado)
        out.write(procs.stop(root, row.get("server") or a.id) + "\n")
        return 0
    snap = procs.snapshot(root)
    if a.json:
        out.write(json.dumps(snap, ensure_ascii=False, indent=2) + "\n")
        return 0
    h = lambda v: "-" if v is None else f"{v}h"   # noqa: E731
    out.write(f"batería: {snap['battery'] or '?'}\n")
    out.write(f"claude: {snap['claude']['count']} procesos, {snap['claude']['cpu']}% CPU, {snap['claude']['mb']} MB\n")
    out.write(f"\nSERVIDORES DEL IDE (abandonado = sin uso hace {snap['config']['idle_hours']} h, desarrollo cerrado o sesión archivada)\n")
    for r in sorted(snap["servers"], key=lambda r: (not r["abandoned"], -r["cpu"])):
        out.write(f"{r['id']}\t{r['cpu']}% {r['mb']}MB\tlog {h(r['lastLogH'])} claude {h(r['lastClaudeH'])}\t"
                  f"{'ABANDONADO: ' + r['abandoned'] if r['abandoned'] else 'en uso'}\n")
    out.write("\nCONTENEDORES\n")
    for r in sorted(snap["docker"], key=lambda r: -r["cpu"]):
        where = f"{r['place']}/{r['repo']}" if r["place"] else "compartido (no es de una sesión)"
        out.write(f"{r['id']}\t{r['name']}\t{r['cpu']}% {r['mb']}MB\t{where}\t"
                  f"{'ABANDONADO: ' + r['abandoned'] if r['abandoned'] else 'en uso' if r['place'] else ''}\n")
    out.write("\nOTROS PROCESOS (≥5% CPU)\n")
    for p in snap["top"]:
        out.write(f"{p['pid']}\t{p['cpu']}% {p['mb']}MB\t{p['etime']}\t{p['command'][:100]}\n")
    return 0


def _browser(a, root: Path, env, out: TextIO) -> int:
    from ide_server import browsers
    if a.cmd == "ls":
        ps = browsers.list_profiles(root)
        out.write(f"local\t(sin cuenta)\tlocal\tsiempre está\tmcp__{browsers.LOCAL_SERVER}__*\tel navegador para probar en localhost\n")
        for p in ps:
            out.write(f"{p['name']}\t{p['url']}\t{'local' if p['local'] else 'REAL'}\t"
                      f"{'con sesión' if p['logged'] else 'sin sesión (ide browser login)'}\t"
                      f"mcp__{p['server']}__*\t{p['note']}\n")
        if not ps:
            out.write("sin perfiles con cuenta (ide browser new <nombre> <url>)\n")
        return 0
    if env.get("IDE_SESSION_ID") and a.cmd != "ls":
        raise SessionError("forbidden", "los perfiles de navegador los maneja el usuario desde su terminal "
                                        "(el login es suyo): pídeselo con el comando exacto")
    if a.cmd == "new":
        p = browsers.new(root, a.name, a.url, a.note)
        out.write(f"perfil {p['name']} creado; inicia sesión con: ide browser login {p['name']}\n"
                  "(las sesiones que ya corrían lo ven al relanzar su claude)\n")
    elif a.cmd == "rm":
        browsers.remove(root, a.name)
        out.write(f"perfil {a.name} borrado\n")
    else:
        out.write("se abre Chrome: inicia sesión y cierra la ventana para guardarla\n")
        out.flush()
        rc = browsers.login(root, a.name)
        browsers.write_mcp_config(root)
        out.write("sesión guardada (un navegador de ese perfil ya abierto en una sesión la toma al cerrarlo y volver a abrirlo)\n" if rc == 0 else f"falló ({rc})\n")
        return rc
    return 0


def _telegram(a, root: Path, url: str | None, http, out: TextIO) -> int:
    import getpass
    import secrets as _secrets
    import time as _time
    from ide_server.db import Db
    from ide_server.telegram import get_token, set_token
    db = Db(root)
    if a.cmd == "status":
        out.write(f"token en el llavero: {'sí' if get_token() else 'no'}\nchat vinculado: {'sí' if db.get('telegram:chat') else 'no'}\n")
        return 0
    token = getpass.getpass("Token del bot (de @BotFather; no se muestra): ").strip()
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{30,}", token):
        raise SessionError("bad_request", "eso no parece un token de bot (formato 123456:ABC…)")
    set_token(token)
    code = _secrets.token_hex(4)
    db.set("telegram:pair", {"code": code, "until": _time.time() + 600})
    db.delete("telegram:chat")
    out.write("Token guardado en el llavero (servicio ide-telegram).\n"
              f"Ahora, en Telegram, mándale a tu bot:  /start {code}\n"
              "(el código vale 10 minutos; el IDE tiene que estar corriendo). Te responde \"Listo\" al vincular.\n")
    return 0


def _feedback(a, root: Path, home: Path, url: str | None, http, out: TextIO) -> int:
    if a.cmd == "run":
        data = _post(http, url, "/api/manager/nightly")
        out.write(f"revisión pedida a {data['id']} ({data['delivered']})\n")
        return 0
    from datetime import datetime
    from ide_server.feedback import as_markdown, collect
    try:
        since = datetime.fromisoformat(a.since) if a.since else None
    except ValueError:
        raise SessionError("bad_request", f"--since inválido: {a.since!r} (AAAA-MM-DD[THH:MM])")
    data = collect(root, home, since)
    out.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n" if a.json else as_markdown(data))
    return 0


def _handoff(a, root: Path, home: Path, out: TextIO) -> int:
    if a.install_skill:
        dest = home / ".claude" / "skills" / "ide-handoff" / "SKILL.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(seeds.skill_handoff(root), encoding="utf-8")
        out.write(f"skill instalada: {dest}\n")
        return 0
    if not a.src or not a.summary_file:
        raise SessionError("bad_request", "faltan --from y --summary-file (o usa --install-skill)")
    try:
        summary = sys.stdin.read() if a.summary_file == "-" else Path(a.summary_file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SessionError("bad_request", f"no se pudo leer --summary-file: {exc}")
    r = handoff(root, Path(a.src), summary=summary, home=home, notion=a.notion, title=a.title,
                session=a.session, status=a.status, force=a.force)
    out.write(f"sesión {r['session']} ({'nueva' if r['created'] else 'existente'}): {r['repo']} @ "
              f"{r['branch'] or '(detach)'} → {r['path']}\n")
    if not r["transcripts"]:
        out.write("aviso: no encontré transcripts de la sesión anterior\n")
    return 0


def _db_query(env_name: str, sql: str, home: Path, out: TextIO, err: TextIO) -> int:
    """Solo el SQL llega a psql: nada de otros argumentos ni comandos de psql (`\\!` corre comandos
    del sistema, `\\o`/`\\copy` escriben archivos), que el usuario read-only de la base no frena."""
    import subprocess
    if "\\" in sql:
        raise SessionError("bad_request", "la consulta no puede tener \\ (comandos de psql como \\!, \\o, \\copy)")
    if not sql.strip():
        raise SessionError("bad_request", "falta la consulta")
    script = home / ".claude" / "skills" / "db-connect.sh"
    if not script.is_file():
        raise SessionError("no_script", f"no está {script} (lo instala la skill db-prod)")
    r = subprocess.run([str(script), env_name, "-c", sql], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       timeout=600)
    out.write(r.stdout); err.write(r.stderr)
    return r.returncode


def main(argv: list[str], *, cwd: Path, env: dict, home: Path, http=httpx,
         out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> int:
    a = _parser().parse_args(argv)
    root = Path(env["IDE_WORKSPACE"]) if env.get("IDE_WORKSPACE") else find_workspace_root(cwd)
    if root is None:
        err.write("error: no hay workspace (.ide/) aquí ni arriba; ejecuta `ide init`\n")
        return 1
    url = find_server_url(root, env, home)
    try:
        if a.group == "session":
            return _session(a, root, url, http, out, err, env)
        if a.group in ("status", "dev"):
            return _dev_cmd(a, url, http, out, env)
        if a.group == "server":
            return _server_cmd(a, url, http, out, env)
        if a.group == "dep":
            return _dep_cmd(a, url, http, out, env)
        if a.group == "hook":
            return _hook(url, http, env)
        if a.group == "later":
            return _later_cmd(a, url, http, out, env)
        if a.group == "evidencias":
            return _evidence_cmd(a, root, url, http, out, env)
        if a.group == "handoff":
            return _handoff(a, root, home, out)
        if a.group == "feedback":
            return _feedback(a, root, home, url, http, out)
        if a.group == "reply":
            text = sys.stdin.read() if a.prompt_file == "-" else (Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else a.text)
            if not text or not text.strip():
                raise SessionError("bad_request", "falta el texto (argumento o --prompt-file -)")
            _post(http, url, "/api/telegram/reply", {"text": text, "token": env.get("IDE_MANAGER_TOKEN", "")})
            out.write("enviado por Telegram\n")
            return 0
        if a.group == "telegram":
            return _telegram(a, root, url, http, out)
        if a.group == "db":
            return _db_query(a.env, a.sql, home, out, err)
        if a.group == "browser":
            return _browser(a, root, env, out)
        if a.group == "procs":
            return _procs(a, root, env, out)
        sid = current_session(root, env=env, cwd=cwd, explicit=a.session)
        if a.group == "update":
            caller = env.get("IDE_SESSION_ID")
            if caller is None:
                try:
                    caller = current_session(root, env={}, cwd=cwd)
                except SessionError:
                    caller = None
            if caller and sid != caller:
                raise SessionError("forbidden", f"desde la sesión {caller} no se actualizan ramas de {sid}")
            from ide_server.update_branch import update
            return update(root, sid, a.repo, dry_run=a.dry_run, out=out)
        if a.group == "push":
            # una sesión solo sube lo suyo (el permiso `ide push` no le da las ramas de otras)
            # (barrera contra errores, no de seguridad: el permiso que importa es el de claude)
            caller = env.get("IDE_SESSION_ID")
            if caller is None:
                try:
                    caller = current_session(root, env={}, cwd=cwd)
                except SessionError:
                    caller = None
            if caller and sid != caller:
                raise SessionError("forbidden", f"desde la sesión {caller} no se suben ramas de {sid}")
            return push(root, sid, a.repo, branches=a.branch, force=a.force, out=out)
        if a.group == "repo" and a.cmd == "add":
            info = add_repo(root, sid, a.repo, branch=a.branch, out=out)
            out.write(f"{info['name']}\t{info['branch'] or '(detached)'}\tIDE_PORT={info['port']}\t"
                      f"{info['path']}\n")
            return 0
        if a.group == "repo":
            rm_repo(root, sid, a.repo, force=a.force, out=out)
            return 0
        repo = a.repo
        if repo is None:
            repos = [p.name for p in repo_links(require_session(root, sid))]
            if len(repos) != 1:
                raise SessionError("ambiguous_repo",
                                   f"la sesión tiene {len(repos)} repos: indica cuál ({', '.join(repos)})")
            repo = repos[0]
        return run_script(root, sid, repo, a.name, out=out)
    except BranchOccupied as exc:
        err.write(f"error: branch ocupada: {exc.branch}. Usa --branch <otra>\n")
    except (SessionError, WorktreeError) as exc:
        err.write(f"error: {exc}\n")
    return 1


def _stop(http, url: str | None):
    """Callback para delete_session: para el proceso sólo después de validar que se puede borrar."""
    def stop(sid: str) -> None:
        try:
            _post(http, url, f"/api/sessions/{sid}/stop")
        except SessionError as exc:
            if exc.code != "no_server":
                raise
    return stop


def _session(a, root: Path, url: str | None, http, out: TextIO, err: TextIO,
             env: dict) -> int:
    if a.cmd == "new":
        data = _post(http, url, "/api/sessions", _new_payload(a, env),
                     timeout=600 if a.review else 120)     # review: gh + fetch + setup
        sid = data["session"]["id"]
        if data.get("dryRun"):
            state = "dry-run (ya existe)" if data.get("existed") else "dry-run"
            out.write(f"{sid}\t{state}\n{data.get('prompt', '')}\n")
            return 0
        state = "existe" if data.get("existed") else data["process"]
        out.write(f"{sid}\t{state}\t{data['session'].get('path', '')}\n")
        if data.get("log"):
            out.write(data["log"])
        return 0
    if a.cmd == "review-stack":
        body = {"urls": a.urls, "token": env.get("IDE_MANAGER_TOKEN", "")}   # solo la principal lo tiene
        data = _post(http, url, "/api/reviews/stack", body, timeout=600)   # gh + fetch + setup
        out.write(f"{data['id']}\t{'creada' if data['created'] else 'existe'}\t{data['process']}\n")
        return 0
    if a.cmd in ("send", "propose"):
        try:
            text = (sys.stdin.read() if a.prompt_file == "-" else Path(a.prompt_file).read_text(encoding="utf-8")) \
                if a.prompt_file else a.prompt
        except (OSError, UnicodeDecodeError) as exc:
            raise SessionError("bad_prompt_file", f"no se pudo leer --prompt-file: {exc}")
        if not text or not text.strip():
            raise SessionError("bad_request", "falta el texto: --prompt-file - (stdin) o --prompt")
        sid = a.id if a.id.lstrip("#").isdigit() else normalize_id(a.id)
        body = {"text": text, "token": env.get("IDE_MANAGER_TOKEN", "")}   # solo la principal lo tiene
        data = _post(http, url, f"/api/sessions/{quote(sid, safe='')}/{a.cmd}", body)
        if a.cmd == "propose":
            out.write(f"{data['id']}\tpropuesto por Telegram (se manda cuando el usuario diga Sí)\n")
        else:
            out.write(f"{data['id']}\t{data['delivered']}\t{data['process']}\n")
        return 0
    if a.cmd in ("open", "stop", "rm"):
        a.id = normalize_id(a.id)
    if a.cmd in ("open", "stop"):
        data = _post(http, url, f"/api/sessions/{a.id}/{a.cmd}")
        out.write(f"{a.id}\t{data.get('process', 'stopped')}\n")
        return 0
    if a.cmd == "rm":
        delete_session(root, a.id, force=a.force, stop=_stop(http, url))
        return 0
    sessions = list_sessions(root)
    procs: dict[str, str] = {}
    if url is not None:
        try:
            tree = http.get(f"{url}/api/sessions", timeout=10).json()
            procs = {s["id"]: s.get("process", "?") for s in tree.get("sessions", [])}
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            err.write(f"aviso: no se pudo consultar el server: {exc}\n")
            procs = {}
    for s in sessions:
        s["process"] = procs.get(s["id"], "?")
    if a.json:
        out.write(json.dumps(sessions, ensure_ascii=False, indent=2) + "\n")
        return 0
    for s in sessions:
        repos = ",".join(r["name"] for r in s["repos"]) or "-"
        out.write(f"{s['id']}\t{s['kind']}\t{s['status'] or '-'}\t{s['process']}\t"
                  f"{s['title'] or ''}\t{repos}{'  ⚠ ' + s['error'] if s['error'] else ''}\n")
    return 0
