# server/ide_server/gh_discussion.py
"""Estado, comentarios y discusiones de UNA PR (módulo Revisión), pedidos a GitHub a demanda."""
from __future__ import annotations
import json
import re
import subprocess
from ide_server.sessions_fs import SessionError

_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")
_AUTHOR = "author { login }"
QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) {
    url title number state isDraft reviewDecision mergeable headRefName baseRefName %(a)s
    commits(last: 1) { nodes { commit { statusCheckRollup { state contexts(first: 60) { nodes {
      __typename
      ... on CheckRun { name conclusion status detailsUrl }
      ... on StatusContext { context state targetUrl } } } } } } }
    reviewRequests(first: 20) { nodes { requestedReviewer { ... on User { login } ... on Team { name } } } }
    latestOpinionatedReviews(first: 20) { nodes { state %(a)s } }
    reviews(last: 50) { nodes { state body submittedAt url %(a)s } }
    comments(last: 50) { nodes { body createdAt url %(a)s } }
    reviewThreads(first: 100) { nodes { isResolved isOutdated path line
      comments(first: 50) { nodes { body createdAt url %(a)s } } } }
  } }
}""" % {"a": _AUTHOR}

_CHECK_OK = {"SUCCESS", "NEUTRAL", "SKIPPED"}
_CHECK_BAD = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}


def _login(n: dict) -> str:
    return (n.get("author") or {}).get("login") or "?"


def _check(c: dict) -> dict:
    if c.get("__typename") == "StatusContext":
        state = c.get("state", "")
        return {"name": c.get("context"), "url": c.get("targetUrl"),
                "state": "success" if state == "SUCCESS" else "failure" if state in ("FAILURE", "ERROR")
                else "pending"}
    concl = c.get("conclusion")
    state = ("pending" if c.get("status") != "COMPLETED" or concl is None
             else "success" if concl in _CHECK_OK else "failure" if concl in _CHECK_BAD else "pending")
    return {"name": c.get("name"), "url": c.get("detailsUrl"), "state": state}


def parse(pr: dict) -> dict:
    commit = (((pr.get("commits") or {}).get("nodes") or [{}])[-1] or {}).get("commit") or {}
    rollup = commit.get("statusCheckRollup") or {}
    checks = [_check(c) for c in (rollup.get("contexts") or {}).get("nodes", []) if c]
    reviewers: dict[str, str] = {}
    for r in pr["latestOpinionatedReviews"]["nodes"]:
        st = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes"}.get(r["state"])
        if st:
            reviewers[_login(r)] = st
    for r in pr["reviewRequests"]["nodes"]:
        rv = r.get("requestedReviewer") or {}
        if who := rv.get("login") or rv.get("name"):
            reviewers[who] = "requested"
    # conversación: reviews con veredicto o con texto + comentarios generales, por fecha
    convo = [{"kind": "review", "author": _login(r), "state": r["state"], "body": r.get("body") or "",
              "at": r.get("submittedAt"), "url": r.get("url")}
             for r in pr["reviews"]["nodes"] if r.get("body") or r["state"] in ("APPROVED", "CHANGES_REQUESTED")]
    convo += [{"kind": "comment", "author": _login(c), "state": None, "body": c.get("body") or "",
               "at": c.get("createdAt"), "url": c.get("url")} for c in pr["comments"]["nodes"]]
    convo.sort(key=lambda x: x["at"] or "")
    threads = [{"resolved": t["isResolved"], "outdated": t["isOutdated"], "path": t.get("path"),
                "line": t.get("line"),
                "comments": [{"author": _login(c), "body": c.get("body") or "", "at": c.get("createdAt"),
                              "url": c.get("url")} for c in t["comments"]["nodes"]]}
               for t in pr["reviewThreads"]["nodes"]]
    threads.sort(key=lambda t: (t["resolved"], t["path"] or "", t["line"] or 0))
    return {"url": pr["url"], "title": pr["title"], "number": pr["number"], "state": pr["state"],
            "draft": pr["isDraft"], "decision": pr.get("reviewDecision"),
            "conflict": pr.get("mergeable") == "CONFLICTING", "head": pr["headRefName"],
            "base": pr["baseRefName"], "ci": {"SUCCESS": "success", "FAILURE": "failure",
                                              "ERROR": "failure", "PENDING": "pending",
                                              "EXPECTED": "pending"}.get(rollup.get("state", "")),
            "checks": checks, "reviewers": [{"login": k, "state": v} for k, v in reviewers.items()],
            "conversation": convo, "threads": threads}


def fetch_discussion(url: str) -> dict:
    m = _URL_RE.match(url.strip())
    if not m:
        raise SessionError("bad_pr_url", f"URL de PR inválida: {url!r}")
    owner, name, number = m.group(1), m.group(2), int(m.group(3))
    out = subprocess.run(["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}",
                          "-f", f"name={name}", "-F", f"number={number}"],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise SessionError("gh_failed", f"gh: {out.stderr.strip() or out.returncode}")
    pr = (((json.loads(out.stdout).get("data") or {}).get("repository") or {}).get("pullRequest"))
    if pr is None:
        raise SessionError("unknown_pr", f"no encontré la PR {url}")
    return parse(pr)


def fetch_body(url: str) -> dict:
    """Descripción (markdown) de una PR, fresca de GitHub."""
    if not _URL_RE.match(url.strip()):
        raise SessionError("bad_pr_url", f"URL de PR inválida: {url!r}")
    out = subprocess.run(["gh", "pr", "view", url, "--json", "body,title,state"],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise SessionError("gh_failed", f"gh: {out.stderr.strip() or out.returncode}")
    data = json.loads(out.stdout)
    return {"body": data.get("body") or "", "state": data.get("state")}


def save_body(url: str, body: str) -> None:
    """Reemplaza la descripción de la PR en GitHub (`gh pr edit --body-file -`)."""
    if not _URL_RE.match(url.strip()):
        raise SessionError("bad_pr_url", f"URL de PR inválida: {url!r}")
    out = subprocess.run(["gh", "pr", "edit", url, "--body-file", "-"], input=body,
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise SessionError("gh_failed", f"gh pr edit: {out.stderr.strip() or out.returncode}")
