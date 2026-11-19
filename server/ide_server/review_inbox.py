# server/ide_server/review_inbox.py
"""`ide review inbox`: lo que te pidieron en las PRs abiertas de tu desarrollo, en un solo comando. Por PR: los
cambios pedidos (la última review de cada revisor que pide cambios, con su texto), los hilos sin resolver donde
la última palabra no es tuya (con el id del comentario para responder y el del hilo para resolver) y los
comentarios generales de otros después de tu última palabra en la PR. Sin tener que recorrer PR por PR con `gh`."""
from __future__ import annotations
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import TextIO

from ide_server.gh_discussion import fetch_discussion


def _me() -> str | None:
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None


def _when(at: str | None) -> str:
    """La hora de GitHub (UTC) en la hora local: `18-11 15:37`."""
    from datetime import datetime
    try:
        return datetime.fromisoformat((at or "").replace("Z", "+00:00")).astimezone().strftime("%d-%m %H:%M")
    except ValueError:
        return at or "?"


def _indent(text: str, pad: str = "      ") -> str:
    return "\n".join(pad + line for line in (text.strip() or "(sin texto)").splitlines())


def pending(d: dict, me: str | None) -> dict:
    """Lo pendiente de una PR (ya parseada por `gh_discussion.parse`): lo que te toca (`reviews`, `threads`,
    `comments`) y lo que ya atendiste y espera al revisor (`answered`: cambios pedidos de un revisor al que **le
    volviste a pedir la revisión**; `waiting`: hilos sin resolver donde la última palabra es tuya). Un commit después de
    la review no cuenta como respuesta (puede ser un rebase o un re-apilado que no toca nada de lo pedido)."""
    last: dict[str, dict] = {}
    for c in d["conversation"]:          # el último veredicto de cada revisor (por fecha)
        if c["kind"] == "review" and c["state"] in ("APPROVED", "CHANGES_REQUESTED") and c["author"] != me:
            last[c["author"]] = c
    asked = [r for r in last.values() if r["state"] == "CHANGES_REQUESTED"]
    rerequested = {r["login"] for r in d["reviewers"] if r["state"] == "requested"}
    open_t = [t for t in d["threads"] if not t["resolved"] and t["comments"]]
    # mi última palabra en la PR (comentario o respuesta en un hilo): los comentarios de otros después, te tocan
    mine = [c["at"] or "" for c in d["conversation"] if c["author"] == me] + \
           [c["at"] or "" for t in d["threads"] for c in t["comments"] if c["author"] == me]
    my_last = max(mine, default="")
    return {"reviews": [r for r in asked if r["author"] not in rerequested],
            "answered": [r for r in asked if r["author"] in rerequested],
            "threads": [t for t in open_t if not me or t["comments"][-1]["author"] != me],
            "waiting": [t for t in open_t if me and t["comments"][-1]["author"] == me],
            "comments": [c for c in d["conversation"] if c["kind"] == "comment" and c["author"] != me
                         and not c["author"].endswith("[bot]") and (c["at"] or "") > my_last]}


def todo(p: dict) -> int:
    return len(p["reviews"]) + len(p["threads"]) + len(p["comments"])


def render(d: dict, p: dict, out: TextIO, *, full: bool = True) -> None:
    flags = [f"review={ {'CHANGES_REQUESTED': 'cambios', 'APPROVED': 'aprobada', 'REVIEW_REQUIRED': 'pendiente'}.get(d['decision'] or '', d['decision'] or '-') }",
             f"ci={d['ci'] or '-'}"] + (["CONFLICTO"] if d["conflict"] else []) + (["draft"] if d["draft"] else [])
    repo = d["url"].split("/")[-3]
    n = todo(p)
    out.write(f"{repo}#{d['number']}  {d['title']}\n  {' '.join(flags)}  · "
              f"{f'{n} pendiente(s)' if n else 'nada pendiente'}  {d['url']}\n")
    wait = [f"cambios de @{r['author']} ({_when(r['at'])}): ya le volviste a pedir la revisión" for r in p["answered"]]
    if p["waiting"]:
        wait.append(f"{len(p['waiting'])} hilo(s) sin resolver con tu respuesta")
    if wait:
        out.write(f"  esperando al revisor: {'; '.join(wait)}\n")
    if not full:
        return
    for r in p["reviews"]:
        out.write(f"  ▸ cambios pedidos por @{r['author']} ({_when(r['at'])}; atiéndelos y vuelve a pedirle la revisión) "
                  f"{r['url']}\n{_indent(r['body'])}\n")
    for t in p["threads"]:
        first = t["comments"][0]
        where = f"{t['path']}:{t['line']}" if t.get("line") else f"{t['path']} (desactualizado)" if t["outdated"] else t["path"]
        out.write(f"  ▸ hilo sin resolver en {where}{' (desactualizado)' if t['outdated'] and t.get('line') else ''}"
                  f" — responder: comentario {first['id']}, resolver: {t['id']}\n")
        for c in t["comments"]:
            out.write(f"    @{c['author']}:\n{_indent(c['body'])}\n")
    for c in p["comments"]:
        out.write(f"  ▸ comentario de @{c['author']} ({_when(c['at'])}) {c['url']}\n{_indent(c['body'])}\n")


def inbox(urls: list[str], out: TextIO, *, show_all: bool = False) -> int:
    if not urls:
        out.write("el desarrollo no tiene PRs abiertas\n")
        return 0
    me = _me()
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda u: _safe(u), urls))
    quiet = []
    for url, d, err in res:
        if err:
            out.write(f"{url}: no pude leerla ({err})\n")
            continue
        p = pending(d, me)
        if todo(p) or show_all:
            render(d, p, out)
            out.write("\n")
        else:
            quiet.append((d, p))
    if quiet:
        out.write("sin pendientes:\n" if not show_all else "")
        for d, p in quiet:
            render(d, p, out, full=False)
    out.write("\nresponder en un hilo: `ide review reply <pr> <comentario> \"texto\"` (o `--file -`); resolverlo: "
              "`ide review resolve <hilo>`; pedir revisión: `ide review add-reviewer <pr> <login>`\n")
    return 0


def _safe(url: str) -> tuple[str, dict | None, str | None]:
    try:
        return url, fetch_discussion(url), None
    except Exception as exc:  # noqa: BLE001
        return url, None, str(exc)
