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

_FIELDS = """... on PullRequest { url title number isDraft updatedAt reviewDecision headRefName baseRefName
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
MEMBERS = """query($org: String!) { organization(login: $org) {
  membersWithRole(first: 100) { nodes { login name } } } }"""
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


def review_state(n: dict) -> str | None:
    """approved | changes | review (con reviews pedidas pendientes) | None (sin review)."""
    decision = n.get("reviewDecision")
    if decision == "APPROVED":
        return "approved"
    if decision == "CHANGES_REQUESTED":
        return "changes"
    return "review" if _requested(n) else None


def compute_stacks(prs: list[dict]) -> dict[str, dict]:
    """Stacks de GitHub: una PR está en un stack si su base es la rama (head) de otra PR abierta
    del mismo repo. Devuelve url -> {id (url de la base del stack), position (1 = la de abajo),
    size}; solo PRs en stacks de 2 o más. Si el stack se ramifica, el orden es en profundidad."""
    by_head = {(n["repository"]["name"], n["headRefName"]): n for n in prs if n.get("headRefName")}
    children: dict[str, list[dict]] = {}
    roots = []
    for n in prs:
        parent = by_head.get((n["repository"]["name"], n.get("baseRefName")))
        if parent is not None and parent is not n:
            children.setdefault(parent["url"], []).append(n)
        else:
            roots.append(n)
    out: dict[str, dict] = {}
    for root in roots:
        order, todo, seen = [], [root], set()
        while todo:
            n = todo.pop()
            if n["url"] in seen:                # ciclo de bases: se corta
                continue
            seen.add(n["url"])
            order.append(n)
            todo.extend(sorted(children.get(n["url"], []), key=lambda c: -c["number"]))
        if len(order) > 1:
            for i, n in enumerate(order):
                out[n["url"]] = {"id": root["url"], "position": i + 1, "size": len(order)}
    return out


def _card(n: dict, stacks: dict[str, dict] | None = None) -> dict:
    return {"url": n["url"], "title": n["title"], "number": n["number"],
            "repo": n["repository"]["name"], "author": "@" + ((n.get("author") or {}).get("login") or "?"),
            "draft": bool(n.get("isDraft")), "updatedAt": n.get("updatedAt"),
            # mismo id que `ide session new --review` (para cruzar la card con su sesión)
            "sessionId": slugify(f"pr-{n['repository']['name']}-{n['number']}"),
            "head": n.get("headRefName"), "base": n.get("baseRefName"), "review": review_state(n),
            "stack": (stacks or {}).get(n["url"])}


def _requested(n: dict) -> list[str]:
    nodes = (n.get("reviewRequests") or {}).get("nodes", [])
    return [l for r in nodes if (l := (r.get("requestedReviewer") or {}).get("login"))]


def selection_file(root: Path) -> Path:
    return root / ".ide" / "reviews.json"


def read_selection(root: Path) -> list[str] | None:
    """Revisores elegidos para los chips (`.ide/reviews.json`); None = todos los con pendientes."""
    f = selection_file(root)
    if not f.is_file():
        return None
    try:
        sel = json.loads(f.read_text(encoding="utf-8")).get("reviewers")
    except (OSError, ValueError, AttributeError) as exc:
        raise ValueError(f"{f} inválido: {exc}") from exc
    return [str(x) for x in sel] if isinstance(sel, list) else None


def write_selection(root: Path, logins: list[str]) -> None:
    f = selection_file(root)
    data = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    data["reviewers"] = sorted({str(x) for x in logins}, key=str.lower)
    f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


MY_GROUPS = ("returned", "waiting", "missing", "draft", "approved")


def my_pr_group(n: dict) -> str:
    """Estado de una PR propia, como el inbox de Graphite."""
    if n.get("isDraft"):
        return "draft"
    decision = n.get("reviewDecision")
    if decision == "APPROVED":
        return "approved"
    if decision == "CHANGES_REQUESTED":
        return "returned"
    return "waiting" if _requested(n) else "missing"


def parse_result(data: dict, members: set[str] | None = None) -> dict:
    d = data["data"]
    me = d["viewer"]["login"]
    open_prs = [n for n in d["open"]["nodes"] if n]
    stack_info = compute_stacks(open_prs)
    card = lambda n: _card(n, stack_info)  # noqa: E731
    pending = [card(n) for n in open_prs if me in _requested(n)]
    seen = {p["url"] for p in pending}
    changes = []
    for n in d["reviewed"]["nodes"]:
        if not n or n["url"] in seen:
            continue
        mine = [r for r in n["latestReviews"]["nodes"] if (r.get("author") or {}).get("login") == me]
        if mine and mine[-1]["state"] == "CHANGES_REQUESTED":
            changes.append(card(n))
    # revisiones pendientes por revisor (solo personas; los pedidos a equipos no cuentan)
    counts: dict[str, int] = {}
    for n in open_prs:
        for login in _requested(n):
            if members is None or login in members:     # solo gente de la org
                counts[login] = counts.get(login, 0) + 1
    reviewers = [{"login": k, "count": v}
                 for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]
    mine: dict[str, list] = {g: [] for g in MY_GROUPS}
    for n in open_prs:
        if (n.get("author") or {}).get("login") == me:
            mine[my_pr_group(n)].append(card(n))
    stacks: dict[str, list] = {}
    for n in open_prs:
        if (info := stack_info.get(n["url"])) is not None:
            stacks.setdefault(info["id"], []).append(card(n))
    for prs in stacks.values():
        prs.sort(key=lambda c: c["stack"]["position"])
    return {"pending": pending, "changesRequested": changes, "me": me, "reviewers": reviewers,
            "mine": mine, "stacks": stacks,
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
                            "mine": {g: [] for g in MY_GROUPS}, "stacks": {},
                            "reviewersTruncated": False, "members": [], "selected": None,
                            "error": None, "lastOk": None, "orgs": []}

    async def _members(self, orgs: list[str]) -> list[dict]:
        out: dict[str, dict] = {}
        for org in orgs:
            code, raw, err = await self._gh(["api", "graphql", "-f", f"query={MEMBERS}", "-f", f"org={org}"])
            if code != 0:
                raise RuntimeError(f"no pude listar los miembros de {org}: {err.strip() or code}")
            org_data = json.loads(raw)["data"]["organization"]
            if org_data is None:
                raise RuntimeError(f"{org} no es una organización de GitHub")
            for m in org_data["membersWithRole"]["nodes"]:
                out[m["login"]] = {"login": m["login"], "name": m.get("name")}
        return sorted(out.values(), key=lambda m: m["login"].lower())

    async def set_selection(self, logins: list[str]) -> None:
        await asyncio.to_thread(write_selection, self._root, logins)
        self.state = {**self.state, "selected": await asyncio.to_thread(read_selection, self._root)}
        self._on_change()

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
                members = await self._members(orgs)
                selected = await asyncio.to_thread(read_selection, self._root)
            except RuntimeError as exc:
                self.state = {**prev, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 — queda marcado, nunca silencioso
                self.state = {**prev, "error": f"respuesta inválida de gh: {exc}"}
            else:
                try:
                    res = parse_result(data, {m["login"] for m in members})
                    ts = datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(timespec="seconds")
                    self.state = {**res, "members": members, "selected": selected,
                                  "error": None, "lastOk": ts, "orgs": orgs}
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
