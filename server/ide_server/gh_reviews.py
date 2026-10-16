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
from ide_server import gh_deps
from ide_server.sessions_fs import slugify
from ide_server.workspace import discover_repos

log = logging.getLogger(__name__)

_FIELDS = """... on PullRequest { url title number isDraft updatedAt reviewDecision headRefName baseRefName body
  isCrossRepository repository { nameWithOwner }
  stack { id size } stackEntry { position }
  mergeable commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
  repository { name } author { login }
  latestOpinionatedReviews(first: 10) { nodes { state author { login } } }
  reviewRequests(first: 10) { nodes { requestedReviewer { ... on User { login } } } } }"""
# Pendientes y conteos salen de `reviewRequests` de los PRs abiertos: la búsqueda GraphQL
# `review-requested:@me` omite PRs con review re-pedida.
# Separadas: juntas tardan ~7 s y GitHub corta con 502 cerca de los 10 s.
QUERY = """query($open: String!) {
  viewer { login }
  open: search(type: ISSUE, first: 50, query: $open) {
    issueCount pageInfo { hasNextPage endCursor } nodes { %s } }
}""" % _FIELDS
REVIEWED = """query($reviewed: String!) {
  reviewed: search(type: ISSUE, first: 50, query: $reviewed) { nodes { %s } }
}""" % _FIELDS
OPEN_PAGE = """query($open: String!, $after: String!) {
  open: search(type: ISSUE, first: 50, query: $open, after: $after) {
    issueCount pageInfo { hasNextPage endCursor } nodes { %s } }
}""" % _FIELDS
MEMBERS = """query($org: String!) { organization(login: $org) {
  membersWithRole(first: 100) { nodes { login name } } } }"""
MAX_PAGES = 20          # páginas de 50: la búsqueda de GitHub no da más de 1000 resultados
RETRIES = 3             # GraphQL pesado: GitHub corta con 502/504 cerca de los 10 s
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
    # Como Graphite: si pidieron cambios pero re-pediste review, vuelve a estar "en revisión"
    # (GitHub mantiene CHANGES_REQUESTED hasta que el revisor apruebe).
    decision = n.get("reviewDecision")
    if decision == "APPROVED":
        return "approved"
    if _requested(n):
        return "review"
    return "changes" if decision == "CHANGES_REQUESTED" else None


def compute_stacks(prs: list[dict]) -> dict[str, dict]:
    """Stacks de GitHub: una PR está en un stack si su base es la rama (head) de otra PR abierta
    del mismo repo. Devuelve url -> {id (url de la base del stack), position (1 = la de abajo),
    size}; solo PRs en stacks de 2 o más. Si el stack se ramifica, el orden es en profundidad."""
    # las PRs desde forks no apilan: su rama no está en el repo base (mismo nombre ≠ misma rama)
    prs = [n for n in prs if not n.get("isCrossRepository")]
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
    # stacks nativos de GitHub: posición y tamaño son los de GitHub (no se infieren por ramas)
    for n in prs:
        st, entry = n.get("stack"), n.get("stackEntry")
        if st and entry and (st.get("size") or 0) > 1:
            out[n["url"]] = {"id": f"native:{st['id']}", "position": entry["position"],
                             "size": st["size"], "native": True}
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
                out.setdefault(n["url"], {"id": root["url"], "position": i + 1, "size": len(order),
                                          "native": False})
    return out


def pr_reviewers(n: dict) -> list[dict]:
    """Quién revisa la PR: {login, state} con state requested (pedida, pendiente) | approved |
    changes. Una review re-pedida cuenta como requested."""
    out: dict[str, str] = {}
    for r in (n.get("latestOpinionatedReviews") or {}).get("nodes", []):
        login = (r.get("author") or {}).get("login")
        state = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes"}.get(r.get("state", ""))
        if login and state:
            out[login] = state
    for login in _requested(n):
        out[login] = "requested"
    return [{"login": k, "state": v} for k, v in out.items()]


def ci_state(n: dict) -> str | None:
    """success | failure | pending | None (sin checks). Un conflicto con la base es failure."""
    if n.get("mergeable") == "CONFLICTING":
        return "failure"
    commits = (n.get("commits") or {}).get("nodes") or [{}]
    rollup = ((commits[-1] or {}).get("commit") or {}).get("statusCheckRollup") or {}
    return {"SUCCESS": "success", "FAILURE": "failure", "ERROR": "failure",
            "PENDING": "pending", "EXPECTED": "pending"}.get(rollup.get("state", ""))


def _card(n: dict, stacks: dict[str, dict] | None = None) -> dict:
    return {"url": n["url"], "title": n["title"], "number": n["number"],
            "repo": n["repository"]["name"], "author": "@" + ((n.get("author") or {}).get("login") or "?"),
            "draft": bool(n.get("isDraft")), "updatedAt": n.get("updatedAt"),
            # mismo id que `ide session new --review` (para cruzar la card con su sesión)
            "sessionId": slugify(f"pr-{n['repository']['name']}-{n['number']}"),
            "head": n.get("headRefName"), "base": n.get("baseRefName"), "review": review_state(n),
            "fullRepo": n["repository"].get("nameWithOwner"), "fork": bool(n.get("isCrossRepository")),
            "stack": (stacks or {}).get(n["url"]), "reviewers": pr_reviewers(n),
            "ci": ci_state(n), "conflict": n.get("mergeable") == "CONFLICTING"}


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
    return {"approved": "approved", "review": "waiting", "changes": "returned"}.get(
        review_state(n) or "", "missing")


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
        # opinionated: una respuesta en un hilo (review COMMENTED) no tapa el pedido de cambios
        mine = [r for r in n["latestOpinionatedReviews"]["nodes"]
                if (r.get("author") or {}).get("login") == me]
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


async def _graphql(gh: GhRunner, args: list[str]) -> str:
    """`gh api graphql` con reintentos ante errores transitorios de GitHub (502/504/timeout)."""
    for attempt in range(RETRIES):
        code, out, err = await gh(["api", "graphql", *args])
        if code == 0:
            return out
        msg = err.strip() or f"gh exit {code}"
        if attempt == RETRIES - 1 or not any(t in msg for t in ("502", "503", "504", "timeout", "Timeout")):
            raise RuntimeError(msg)
        await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError("inalcanzable")


async def fetch_all(gh: GhRunner, reviewed: str, open_q: str) -> dict:
    """Primera página (viewer + reviewed + open) y el resto de `open` paginado."""
    data = json.loads(await _graphql(gh, ["-f", f"query={QUERY}", "-f", f"open={open_q}"]))
    data["data"]["reviewed"] = json.loads(await _graphql(
        gh, ["-f", f"query={REVIEWED}", "-f", f"reviewed={reviewed}"]))["data"]["reviewed"]
    page = data["data"]["open"]
    for _ in range(MAX_PAGES - 1):
        if not page["pageInfo"]["hasNextPage"]:
            break
        out = await _graphql(gh, ["-f", f"query={OPEN_PAGE}", "-f", f"open={open_q}",
                                  "-f", f"after={page['pageInfo']['endCursor']}"])
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

    async def _annotate_deps(self, res: dict, data: dict) -> None:
        """Agrega a cada card `deps` (cadena de dependencias declaradas) y `depsPending`."""
        prs = [n for n in data["data"]["open"]["nodes"] if n]
        by_key = {(n["repository"]["nameWithOwner"].lower(), n["number"]): n for n in prs}
        info = {n["url"]: {"repo": n["repository"]["name"], "number": n["number"], "title": n["title"],
                           "state": "OPEN"} for n in prs}
        refs = {n["url"]: gh_deps.parse_deps(n.get("body"), *n["repository"]["nameWithOwner"].split("/", 1),
                                             n["number"]) for n in prs}
        unknown = sorted({(full, num) for lst in refs.values() for full, num in lst
                          if (full.lower(), num) not in by_key})
        found = await gh_deps.resolve(self._gh, unknown) if unknown else {}
        url_of = {k: n["url"] for k, n in by_key.items()}
        for (full, num), pr in found.items():
            url_of[(full, num)] = pr["url"]
            info[pr["url"]] = {"repo": full.split("/", 1)[1], "number": pr["number"],
                               "title": pr["title"], "state": pr["state"]}
        direct = {u: [url_of[(f.lower(), n)] for f, n in lst if (f.lower(), n) in url_of]
                  for u, lst in refs.items()}
        cards = [*res["pending"], *res["changesRequested"], *(c for l in res["mine"].values() for c in l),
                 *(c for l in res["stacks"].values() for c in l)]
        for c in cards:
            c["deps"] = gh_deps.chains(direct, info, c["url"])
            c["depsPending"] = sum(1 for d in c["deps"] if d["state"] != "MERGED" and not d["together"])

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
                    await self._annotate_deps(res, data)
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
