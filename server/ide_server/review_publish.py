"""`ide review`: las escrituras de una sesión de revisión en GitHub (publicar la review, responder un hilo,
resolverlo, pedir revisor), validadas antes de llamar a `gh`. Existe para que el permiso de las sesiones
cubra solo esto (`Bash(ide review:*)`) y no `gh api` en general: solo la org Finnecto, solo desde una
sesión de revisión y solo sobre sus propias PRs."""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from ide_server.sessions_fs import SessionError, read_session

ORG = "Finnecto"
_PR_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")
_REF_RE = re.compile(r"^([A-Za-z0-9_.-]+)#(\d+)$")
# solo pedir cambios: aprobar lo hace el usuario desde la card (una PR maliciosa podría pedirle a la sesión que
# la apruebe) y comentar sin veredicto no sirve
_EVENTS = {"REQUEST_CHANGES"}
_REVIEW_KEYS = {"body", "event", "commit_id", "comments"}
_COMMENT_KEYS = {"path", "line", "side", "start_line", "start_side", "body", "position", "subject_type"}
_LOGIN_RE = re.compile(r"^[A-Za-z0-9-]{1,39}$")


def _gh(args: list[str], stdin: str | None = None) -> str:
    out = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise SessionError("gh_failed", (out.stderr or out.stdout).strip()[:500] or "gh falló")
    return out.stdout


def _pr(ref: str) -> tuple[str, int, str]:
    """`https://github.com/Finnecto/<repo>/pull/<n>` o `<repo>#<n>` → (repo, n, url). Solo la org."""
    if m := _PR_RE.match(ref.strip()):
        owner, repo, n = m.groups()
        if owner.lower() != ORG.lower():
            raise SessionError("forbidden", f"solo PRs de {ORG} (esta es de {owner})")
    elif m := _REF_RE.match(ref.strip()):
        repo, n = m.groups()
    else:
        raise SessionError("bad_request", f"PR inválida: {ref!r} (usa la URL o <repo>#<n>)")
    return repo, int(n), f"https://github.com/{ORG}/{repo}/pull/{n}"


def _own_pr(root: Path, sid: str, ref: str) -> tuple[str, int, str]:
    """La PR tiene que ser de esta sesión de revisión (su PR o una de su stack)."""
    s = read_session(root, sid)
    if s.get("kind") != "review":
        raise SessionError("forbidden", f"`ide review` es solo para sesiones de revisión ({sid} es {s.get('kind')})")
    repo, n, url = _pr(ref)
    mine = {u.rstrip("/").lower() for u in [s.get("prUrl"), *(s.get("stackPrs") or [])] if u}
    if url.lower() not in mine:
        raise SessionError("forbidden", f"{repo}#{n} no es una PR de esta revisión ({sid})")
    return repo, n, url


def publish(root: Path, sid: str, ref: str, file: str) -> dict:
    """POST .../pulls/<n>/reviews con el JSON de `file` (body, event REQUEST_CHANGES, commit_id, comments en línea)."""
    repo, n, _ = _own_pr(root, sid, ref)
    try:
        data = json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SessionError("bad_request", f"no pude leer el JSON de la review: {exc}") from exc
    if not isinstance(data, dict) or set(data) - _REVIEW_KEYS:
        raise SessionError("bad_request", f"campos permitidos: {', '.join(sorted(_REVIEW_KEYS))}")
    if data.get("event") == "APPROVE":
        raise SessionError("forbidden", "aprobar lo hace el usuario desde la card (Aprobar): deja el veredicto "
                                        "«Aprobar» en SESSION.md y díselo")
    if data.get("event") not in _EVENTS:
        raise SessionError("bad_request", "event tiene que ser REQUEST_CHANGES (aprobar lo hace el usuario)")
    for c in data.get("comments") or []:
        if not isinstance(c, dict) or set(c) - _COMMENT_KEYS or not c.get("path") or not c.get("body"):
            raise SessionError("bad_request", f"comentario inválido (path y body obligatorios; campos: "
                                              f"{', '.join(sorted(_COMMENT_KEYS))})")
    res = json.loads(_gh(["api", f"repos/{ORG}/{repo}/pulls/{n}/reviews", "--method", "POST", "--input", "-"],
                         json.dumps(data)) or "{}")
    return {"id": res.get("id"), "state": res.get("state"), "url": res.get("html_url"),
            "body": data.get("body") or "", "sha": data.get("commit_id") or res.get("commit_id")}


def head_sha(ref: str) -> str | None:
    """El head actual de la PR (lo que la sesión acaba de revisar)."""
    _, _, url = _pr(ref)
    try:
        return json.loads(_gh(["pr", "view", url, "--json", "headRefOid"])).get("headRefOid")
    except (SessionError, ValueError):
        return None


def reply(root: Path, sid: str, ref: str, comment_id: int, body: str) -> dict:
    """Respuesta en un hilo existente: POST .../pulls/<n>/comments/<id>/replies."""
    repo, n, _ = _own_pr(root, sid, ref)
    if not body.strip():
        raise SessionError("bad_request", "falta el texto de la respuesta")
    res = json.loads(_gh(["api", f"repos/{ORG}/{repo}/pulls/{n}/comments/{int(comment_id)}/replies",
                          "--method", "POST", "-f", f"body={body}"]) or "{}")
    return {"id": res.get("id"), "url": res.get("html_url")}


def resolve(root: Path, sid: str, thread_id: str, *, undo: bool = False) -> dict:
    """Resuelve (o reabre) un hilo de review, después de verificar que es de una PR de esta revisión."""
    if not re.fullmatch(r"[A-Za-z0-9_=-]{4,100}", thread_id):
        raise SessionError("bad_request", f"id de hilo inválido: {thread_id!r}")
    q = "query($id: ID!) { node(id: $id) { ... on PullRequestReviewThread { pullRequest { url } } } }"
    node = (json.loads(_gh(["api", "graphql", "-f", f"query={q}", "-f", f"id={thread_id}"]))
            .get("data") or {}).get("node") or {}
    url = (node.get("pullRequest") or {}).get("url")
    if not url:
        raise SessionError("not_found", f"{thread_id} no es un hilo de review")
    _own_pr(root, sid, url)
    op = "unresolveReviewThread" if undo else "resolveReviewThread"
    m = f"mutation($id: ID!) {{ {op}(input: {{threadId: $id}}) {{ thread {{ isResolved }} }} }}"
    res = json.loads(_gh(["api", "graphql", "-f", f"query={m}", "-f", f"id={thread_id}"]))
    return {"resolved": (((res.get("data") or {}).get(op) or {}).get("thread") or {}).get("isResolved")}


def add_reviewer(root: Path, sid: str, ref: str, logins: list[str]) -> None:
    _, _, url = _own_pr(root, sid, ref)
    bad = [x for x in logins if not _LOGIN_RE.match(x)]
    if bad or not logins:
        raise SessionError("bad_request", f"login inválido: {', '.join(bad) or '(ninguno)'}")
    _gh(["pr", "edit", url, "--add-reviewer", ",".join(logins)])
