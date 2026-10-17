"""Subcomandos `ide session|repo|script`. Disco in-process; procesos vía HTTP al server."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import TextIO
import httpx
from ide_server import instances, seeds
from ide_server.devs import STATUSES
from ide_server.handoff import handoff
from ide_server.repos_fs import add_repo, rm_repo, require_session
from ide_server.scripts import run_script
from ide_server.session_ops import delete_session
from ide_server.sessions_fs import SessionError, list_sessions, normalize_id, sessions_dir
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
    r = sub.add_parser("repo").add_subparsers(dest="cmd", required=True)
    ra = r.add_parser("add"); ra.add_argument("repo"); ra.add_argument("--branch")
    ra.add_argument("--session")
    st = sub.add_parser("status", help="cambia el estado de la sesión (queda en la base y en el historial)")
    st.add_argument("status"); st.add_argument("-m", "--note"); st.add_argument("--session")
    dv = sub.add_parser("dev").add_subparsers(dest="cmd", required=True)
    dls = dv.add_parser("ls"); dls.add_argument("--json", action="store_true")
    dsh = dv.add_parser("show"); dsh.add_argument("id"); dsh.add_argument("--json", action="store_true")
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
            f"{' draft' if p.get('draft') else ''}{deps}  {p['title']}" + (f"  [{who}]" if who else ""))


def _dev_cmd(a, url: str | None, http, out: TextIO, env: dict) -> int:
    from urllib.parse import quote
    if a.group == "status":
        sid = a.session or env.get("IDE_SESSION_ID")
        if not sid:
            raise SessionError("no_session", "no estoy dentro de una sesión: usa --session <id>")
        actor = f"claude:{env['IDE_SESSION_ID']}" if env.get("IDE_SESSION_ID") else "cli"
        data = _post(http, url, f"/api/devs/{quote(sid, safe='')}/status",
                     {"status": a.status, "note": a.note, "actor": actor})
        out.write(f"{sid}\t{data['dev']['status']}\n")
        return 0
    if a.cmd == "ls":
        devs = _get(http, url, "/api/devs")["devs"]
        if a.json:
            out.write(json.dumps(devs, ensure_ascii=False, indent=2) + "\n")
            return 0
        for d in devs:
            title = f"{d['name']} ({d['title']})" if d.get("name") else d["title"] or ""
            n = f"#{d['index']}" if d.get("index") else "-"
            out.write(f"{n}\t{d['id']}\t{d['kind']}\t{d['status'] or '-'}\t{d['process'] or '-'}\t{title}\n")
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
                if x.get("state") != "MERGED" and not x.get("together"):
                    out.write(f"      ⏸ espera a {x['repo']}#{x['number']} ({x['state']})\n")
    out.write("historial:\n")
    for e in d.get("events") or []:
        extra = " ".join(f"{k}={v}" for k, v in (e.get("data") or {}).items())
        out.write(f"  {e['at']}  {e['actor']:<16} {e['kind']:<10} {extra}\n")
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
        if a.group == "handoff":
            return _handoff(a, root, home, out)
        sid = current_session(root, env=env, cwd=cwd, explicit=a.session)
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
            repos = [p.name for p in require_session(root, sid).iterdir() if p.is_symlink()]
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
