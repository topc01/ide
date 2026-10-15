# server/ide_server/gh_reviews.py
"""PRs abiertos de la org donde te pidieron review (pendientes) o donde tu última review pidió
cambios. Un solo `gh api graphql` por ciclo; no depende de la sesión abierta."""
from __future__ import annotations
import asyncio
import json
import logging
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from ide_server.pr_poller import GhRunner, _default_gh
from ide_server.sessions_fs import slugify
from ide_server.workspace import discover_repos

log = logging.getLogger(__name__)

_FIELDS = """... on PullRequest { url title number isDraft updatedAt
  repository { name } author { login }
  latestReviews(first: 30) { nodes { state author { login } } }
  reviewRequests(first: 20) { nodes { requestedReviewer { ... on User { login } } } } }"""
# Pendientes y conteos salen de `reviewRequests` de los PRs abiertos: la búsqueda GraphQL
# `review-requested:@me` omite PRs con review re-pedida.
QUERY = """query($reviewed: String!, $open: String!) {
  viewer { login }
  reviewed: search(type: ISSUE, first: 50, query: $reviewed) { nodes { %s } }
  open: search(type: ISSUE, first: 100, query: $open) {
    issueCount pageInfo { hasNextPage endCursor } nodes { %s } }
}""" % (_FIELDS, _FIELDS)
OPEN_PAGE = """query($open: String!, $after: String!) {
  open: search(type: ISSUE, first: 100, query: $open, after: $after) {
    issueCount pageInfo { hasNextPage endCursor } nodes { %s } }
}""" % _FIELDS
MAX_PAGES = 10          # la búsqueda de GitHub no da más de 1000 resultados
_REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/")


def workspace_orgs(root: Path) -> list[str]:
    """Owners de GitHub de los `origin` de los repos del workspace."""
    orgs: set[str] = set()
    for r in discover_repos(root):
        out = subprocess.run(["git", "-C", str(root / r["id"]), "remote", "get-url", "origin"],
                             capture_output=True, text=True)
        if out.returncode == 0 and (m := _REMOTE_RE.search(out.stdout)):
            orgs.add(m.group(1))
    return sorted(orgs)


def _card(n: dict) -> dict:
    return {"url": n["url"], "title": n["title"], "number": n["number"],
            "repo": n["repository"]["name"], "author": "@" + ((n.get("author") or {}).get("login") or "?"),
            "draft": bool(n.get("isDraft")), "updatedAt": n.get("updatedAt"),
            # mismo id que `ide session new --review` (para cruzar la card con su sesión)
            "sessionId": slugify(f"pr-{n['repository']['name']}-{n['number']}")}


def _requested(n: dict) -> list[str]:
    nodes = (n.get("reviewRequests") or {}).get("nodes", [])
    return [l for r in nodes if (l := (r.get("requestedReviewer") or {}).get("login"))]


def parse_result(data: dict) -> dict:
    d = data["data"]
    me = d["viewer"]["login"]
    open_prs = [n for n in d["open"]["nodes"] if n]
    pending = [_card(n) for n in open_prs if me in _requested(n)]
    seen = {p["url"] for p in pending}
    changes = []
    for n in d["reviewed"]["nodes"]:
        if not n or n["url"] in seen:
            continue
        mine = [r for r in n["latestReviews"]["nodes"] if (r.get("author") or {}).get("login") == me]
        if mine and mine[-1]["state"] == "CHANGES_REQUESTED":
            changes.append(_card(n))
    # revisiones pendientes por revisor (solo personas; los pedidos a equipos no cuentan)
    counts: dict[str, int] = {}
    for n in open_prs:
        for login in _requested(n):
            counts[login] = counts.get(login, 0) + 1
    reviewers = [{"login": k, "count": v}
                 for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]
    return {"pending": pending, "changesRequested": changes, "me": me, "reviewers": reviewers,
            "reviewersTruncated": d["open"]["issueCount"] > len(d["open"]["nodes"])}


async def fetch_all(gh: GhRunner, reviewed: str, open_q: str) -> dict:
    """Primera página (viewer + reviewed + open) y el resto de `open` paginado."""
    code, out, err = await gh(["api", "graphql", "-f", f"query={QUERY}",
                               "-f", f"reviewed={reviewed}", "-f", f"open={open_q}"])
    if code != 0:
        raise RuntimeError(err.strip() or f"gh exit {code}")
    data = json.loads(out)
    page = data["data"]["open"]
    for _ in range(MAX_PAGES - 1):
        if not page["pageInfo"]["hasNextPage"]:
            break
        code, out, err = await gh(["api", "graphql", "-f", f"query={OPEN_PAGE}", "-f", f"open={open_q}",
                                   "-f", f"after={page['pageInfo']['endCursor']}"])
        if code != 0:
            raise RuntimeError(err.strip() or f"gh exit {code}")
        page = json.loads(out)["data"]["open"]
        data["data"]["open"]["nodes"] += page["nodes"]
    return data


class GithubReviews:
    def __init__(self, root: Path, *, interval: int, org: str | None = None,
                 run_gh: GhRunner | None = None, on_change: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._root, self._interval, self._org = root, interval, org
        self._gh = run_gh or _default_gh
        self._on_change = on_change or (lambda: None)
        self._clock = clock
        self.state: dict = {"pending": [], "changesRequested": [], "me": None, "reviewers": [],
                            "reviewersTruncated": False, "error": None, "lastOk": None, "orgs": []}

    async def poll_once(self) -> None:
        orgs = [self._org] if self._org else await asyncio.to_thread(workspace_orgs, self._root)
        prev = self.state
        if not orgs:
            self.state = {**prev, "error": "no hay org de GitHub: configura [reviews] github_org"}
        else:
            scope = " ".join(f"org:{o}" for o in orgs)
            base = f"is:pr is:open archived:false {scope}"
            try:
                data = await fetch_all(self._gh, f"{base} reviewed-by:@me", base)
            except RuntimeError as exc:
                self.state = {**prev, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 — queda marcado, nunca silencioso
                self.state = {**prev, "error": f"respuesta inválida de gh: {exc}"}
            else:
                try:
                    res = parse_result(data)
                    ts = datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(timespec="seconds")
                    self.state = {**res, "error": None, "lastOk": ts, "orgs": orgs}
                except Exception as exc:  # noqa: BLE001 — queda marcado, nunca silencioso
                    self.state = {**prev, "error": f"respuesta inválida de gh: {exc}"}
        if {k: v for k, v in self.state.items() if k != "lastOk"} != \
           {k: v for k, v in prev.items() if k != "lastOk"}:
            self._on_change()

    async def run(self, stop: asyncio.Event) -> None:
        if self._interval <= 0:
            return
        while not stop.is_set():
            try:
                await self.poll_once()
            except Exception:
                log.exception("el poller de revisiones de GitHub falló; sigue en el próximo")
            try:
                await asyncio.wait_for(stop.wait(), self._interval)
            except asyncio.TimeoutError:
                pass
