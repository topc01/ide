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
from ide_server.db import Db
from ide_server.sessions_fs import slugify
from ide_server.workspace import discover_repos

log = logging.getLogger(__name__)

_FIELDS = """... on PullRequest { id state url title number isDraft updatedAt reviewDecision headRefName headRefOid baseRefName body
  isCrossRepository repository { nameWithOwner }
  stack { id size } stackEntry { position }
  mergeable mergeStateStatus commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
  repository { name } author { login }
  latestOpinionatedReviews(first: 10) { nodes { state author { login } } }
  reviewRequests(first: 10) { nodes { requestedReviewer { ... on User { login } } } } }"""
# Pendientes y conteos salen de `reviewRequests` de los PRs abiertos: la búsqueda GraphQL
# `review-requested:@me` omite PRs con review re-pedida.
# Separadas: juntas tardan ~7 s y GitHub corta con 502 cerca de los 10 s.
SEARCH = """query($q: String!, $after: String) {
  viewer { login }
  s: search(type: ISSUE, first: 50, query: $q, after: $after) {
    issueCount pageInfo { hasNextPage endCursor } nodes { %s } }
}""" % _FIELDS
# Las relevantes (tuyas, las que revisas) se refrescan por ID con el estado de cada check: así se sabe
# si un CI que ya falló sigue corriendo (la búsqueda de toda la org no lo trae: sería muy pesada).
_FIELDS_FULL = _FIELDS.replace("statusCheckRollup { state }", "statusCheckRollup { state contexts(first: 100) { "
                               "nodes { __typename ... on CheckRun { name status conclusion detailsUrl "
                               "checkSuite { workflowRun { workflow { name } } } } ... on StatusContext { context state } } } }")
NODES = """query($ids: [ID!]!) { nodes(ids: $ids) { %s } }""" % _FIELDS_FULL
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
    """approved | changes | review (con reviews pedidas pendientes) | None (sin review).
    Por revisor: si **cualquiera** tiene cambios pedidos, la PR está en cambios pedidos, aunque otro siga
    pendiente o haya aprobado. Si a ese mismo revisor se le re-pidió la review, ya no cuenta como cambios
    (vuelve a "en revisión"; GitHub mantiene CHANGES_REQUESTED hasta que apruebe)."""
    states = {r["state"] for r in pr_reviewers(n)}
    decision = n.get("reviewDecision")
    if "changes" in states:
        return "changes"
    if decision == "APPROVED":
        return "approved"
    if "requested" in states or _requested(n):
        return "review"
    return "changes" if decision == "CHANGES_REQUESTED" else None


def compute_stacks(prs: list[dict]) -> dict[str, dict]:
    """Stacks de GitHub: una PR está en un stack si su base es la rama (head) de otra PR abierta
    del mismo repo. Devuelve url -> {id (url de la base del stack), position (1 = la de abajo),
    size, native, inNative}; solo PRs en stacks de 2 o más. Si el stack se ramifica, el orden es en
    profundidad. Una PR cuya base es la rama de una PR de un stack nativo de GitHub (p.ej. abierta con
    `gh pr create --base`) se suma a ese stack arriba de su madre (`inNative` false): posición y tamaño
    son del conjunto."""
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
    # stacks nativos de GitHub: el orden es el de GitHub, pero GitHub sigue contando las PRs ya
    # mergeadas (embed#2529 seguía "4 de 4" con las 3 de abajo mergeadas): posición y tamaño se
    # recalculan solo sobre las abiertas (la de abajo abierta es la 1 y la que se puede mergear).
    native: dict[str, list[dict]] = {}
    for n in prs:
        st, entry = n.get("stack"), n.get("stackEntry")
        if st and entry:
            native.setdefault(st["id"], []).append(n)
    native = {sid: sorted(m, key=lambda m: m["stackEntry"]["position"]) for sid, m in native.items() if len(m) >= 2}
    in_native = {n["url"]: sid for sid, members in native.items() for n in members}
    for sid, members in native.items():
        # en profundidad desde la de abajo: primero sus hijas nativas (en el orden de GitHub), después
        # las que se le apilaron por base; no se cruza a otro stack nativo
        pos = {n["url"]: i for i, n in enumerate(members)}
        order, todo, seen = [], [members[0]], set()
        while todo:
            n = todo.pop()
            if n["url"] in seen or in_native.get(n["url"], sid) != sid:
                continue
            seen.add(n["url"])
            order.append(n)
            kids = children.get(n["url"], [])
            todo.extend(sorted(kids, key=lambda c: (c["url"] not in pos, pos.get(c["url"], 0), c["number"]), reverse=True))
        order += [n for n in members if n["url"] not in seen]
        for i, n in enumerate(order):
            out[n["url"]] = {"id": f"native:{sid}", "position": i + 1, "size": len(order), "native": True,
                             "inNative": n["url"] in pos}
    for root in roots:
        if root["url"] in out:                  # ya está en un stack nativo (con lo que se le apila)
            continue
        order, todo, seen = [], [root], set()
        while todo:
            n = todo.pop()
            if n["url"] in seen or n["url"] in out:   # ciclo de bases, o ya es de un stack nativo
                continue
            seen.add(n["url"])
            order.append(n)
            todo.extend(sorted(children.get(n["url"], []), key=lambda c: -c["number"]))
        if len(order) > 1:
            for i, n in enumerate(order):
                out.setdefault(n["url"], {"id": root["url"], "position": i + 1, "size": len(order),
                                          "native": False, "inNative": False})
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


def _rollup(n: dict) -> dict:
    commits = (n.get("commits") or {}).get("nodes") or [{}]
    return ((commits[-1] or {}).get("commit") or {}).get("statusCheckRollup") or {}


_RUN_RE = re.compile(r"/actions/runs/(\d+)")
CHECK_OK = {"SUCCESS", "NEUTRAL", "SKIPPED"}
CHECK_BAD = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}


def latest_checks(nodes: list[dict]) -> list[dict]:
    """Solo lo vigente: cuando una corrida de un workflow reemplaza a otra en el mismo commit (el workflow cancela la
    anterior al arrancar otra), GitHub deja las dos en el rollup y lo marca FAILURE por la vieja aunque la nueva siga
    corriendo o pase. Se descartan los CheckRun de una corrida (run id del link) más vieja que la más nueva **del mismo
    workflow** (aunque la vieja dejara pasos en FAILURE que la nueva todavía no corre, como un «CI Gate» final); sin
    el nombre del workflow, solo los CANCELADOS con una corrida más nueva del mismo check. Un status externo nunca
    se descarta."""
    def run(c: dict) -> int:
        m = _RUN_RE.search(c.get("detailsUrl") or "")
        return int(m.group(1)) if m else 0
    def wf(c: dict) -> str | None:
        # GraphQL (checkSuite) o `gh pr view --json statusCheckRollup` (workflowName)
        return c.get("workflowName") or ((((c.get("checkSuite") or {}).get("workflowRun") or {}).get("workflow") or {}).get("name"))
    newest: dict[str, int] = {}
    newest_wf: dict[str, int] = {}
    for c in nodes:
        if c and c.get("__typename") == "CheckRun":
            if c.get("name"):
                newest[c["name"]] = max(newest.get(c["name"], 0), run(c))
            if wf(c):
                newest_wf[wf(c)] = max(newest_wf.get(wf(c), 0), run(c))
    def stale(c: dict) -> bool:
        if c.get("__typename") != "CheckRun" or not run(c):
            return False
        if wf(c) and run(c) < newest_wf.get(wf(c), 0):
            return True
        return c.get("conclusion") == "CANCELLED" and run(c) < newest.get(c.get("name") or "", 0)
    return [c for c in nodes if c and not stale(c)]


def checks_state(nodes: list[dict]) -> str | None:
    """success | failure | pending | None (sin checks), contando solo el último de cada check."""
    nodes = latest_checks(nodes)
    if not nodes:
        return None
    state = "success"
    for c in nodes:
        concl, st = c.get("conclusion") or "", c.get("state") or ""
        if concl in CHECK_BAD or st in ("FAILURE", "ERROR"):
            return "failure"
        if (c.get("__typename") == "CheckRun" and c.get("status") != "COMPLETED") or st in ("PENDING", "EXPECTED"):
            state = "pending"
    return state


def ci_state(n: dict) -> str | None:
    """success | failure | pending | None (sin checks). Solo los checks: un conflicto va aparte
    (`conflict` en la card). Con el detalle de los checks (PRs refrescadas por ID) se cuenta el último de
    cada uno; sin él, el estado que da GitHub."""
    nodes = ((_rollup(n).get("contexts") or {}).get("nodes")) or []
    if nodes:
        return checks_state(nodes)
    return {"SUCCESS": "success", "FAILURE": "failure", "ERROR": "failure",
            "PENDING": "pending", "EXPECTED": "pending"}.get(_rollup(n).get("state", ""))


def ci_running(n: dict) -> bool:
    """Quedan checks corriendo (GitHub marca FAILURE apenas falla uno, aunque otros sigan). Solo se
    sabe en las PRs refrescadas por ID (las que traen `contexts`)."""
    nodes = latest_checks(((_rollup(n).get("contexts") or {}).get("nodes")) or [])
    return any((c.get("__typename") == "CheckRun" and c.get("status") not in (None, "COMPLETED"))
               or c.get("state") in ("PENDING", "EXPECTED") for c in nodes if c)


def _card(n: dict, stacks: dict[str, dict] | None = None) -> dict:
    return {"url": n["url"], "title": n["title"], "number": n["number"],
            "repo": n["repository"]["name"], "author": "@" + ((n.get("author") or {}).get("login") or "?"),
            "draft": bool(n.get("isDraft")), "updatedAt": n.get("updatedAt"),
            # mismo id que `ide session new --review` (para cruzar la card con su sesión)
            "sessionId": slugify(f"pr-{n['repository']['name']}-{n['number']}"),
            "head": n.get("headRefName"), "headSha": n.get("headRefOid"), "base": n.get("baseRefName"), "review": review_state(n),
            "fullRepo": n["repository"].get("nameWithOwner"), "fork": bool(n.get("isCrossRepository")),
            "stack": (stacks or {}).get(n["url"]), "reviewers": pr_reviewers(n),
            "ci": ci_state(n), "ciRunning": ci_running(n), "conflict": n.get("mergeable") == "CONFLICTING",
            "mergeable": n.get("mergeable"),
            # atrasada respecto de su base (develop avanzó): aviso, no bloquea
            "behind": n.get("mergeStateStatus") == "BEHIND"}


def _requested(n: dict) -> list[str]:
    nodes = (n.get("reviewRequests") or {}).get("nodes", [])
    return [l for r in nodes if (l := (r.get("requestedReviewer") or {}).get("login"))]


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


async def search_all(gh: GhRunner, q: str) -> tuple[str | None, list[dict], int]:
    """(login del viewer, nodos, total) de una búsqueda de PRs, paginada (tope de GitHub: 1000)."""
    nodes: list[dict] = []
    after, viewer, total = None, None, 0
    for _ in range(MAX_PAGES):
        args = ["-f", f"query={SEARCH}", "-f", f"q={q}"] + (["-f", f"after={after}"] if after else [])
        d = json.loads(await _graphql(gh, args))["data"]
        viewer, page = d["viewer"]["login"], d["s"]
        total = page["issueCount"]
        nodes += [n for n in page["nodes"] if n]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return viewer, nodes, total


async def fetch_nodes(gh: GhRunner, ids: list[str]) -> list[dict]:
    """Refresco por ID (lo dinámico de las PRs relevantes), en lotes de 50."""
    out: list[dict] = []
    for i in range(0, len(ids), 50):
        args = ["api", "graphql", "-f", f"query={NODES}"] + [
            x for nid in ids[i:i + 50] for x in ("-f", f"ids[]={nid}")]
        code, raw, err = await gh(args)
        try:                                    # un ID que ya no existe da error, pero el resto viene
            data = json.loads(raw).get("data") or {}
        except ValueError:
            data = {}
        if "nodes" not in data:
            raise RuntimeError(err.strip() or f"gh exit {code}")
        out += [n for n in data["nodes"] if n]
    return out


FULL_EVERY = 30 * 60        # resincronización completa
MEMBERS_EVERY = 24 * 3600   # miembros de la org
_CLOSED = ("MERGED", "CLOSED")


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ref(n: dict) -> dict:
    return {"url": n["url"], "title": n["title"], "number": n["number"], "state": n["state"]}


class GithubReviews:
    """Revisiones, Mis PRs, stacks y dependencias. La base (`.ide/ide.db`) guarda las PRs: el poll
    es incremental (`updated:`), más un refresco de lo dinámico (CI, review) de las relevantes y
    una resincronización completa cada 30 min. Ver spec 2026-10-16-desarrollos."""

    def __init__(self, root: Path, *, interval: int, db: Db, org: str | None = None,
                 run_gh: GhRunner | None = None, on_change: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._root, self._interval, self._org, self._db = root, interval, org, db
        self._gh = run_gh or _default_gh
        self._on_change = on_change or (lambda: None)
        self._clock = clock
        self.state: dict = {"pending": [], "changesRequested": [], "me": None, "reviewers": [],
                            "mine": {g: [] for g in MY_GROUPS}, "stacks": {},
                            "reviewersTruncated": False, "members": [], "selected": None,
                            "error": None, "lastOk": None, "orgs": []}

    async def _members(self, orgs: list[str]) -> list[dict]:
        if self._clock() - (self._db.get("members_at") or 0) < MEMBERS_EVERY and self._db.members(orgs):
            return self._db.members(orgs)
        for org in orgs:
            code, raw, err = await self._gh(["api", "graphql", "-f", f"query={MEMBERS}", "-f", f"org={org}"])
            if code != 0:
                raise RuntimeError(f"no pude listar los miembros de {org}: {err.strip() or code}")
            org_data = json.loads(raw)["data"]["organization"]
            if org_data is None:
                raise RuntimeError(f"{org} no es una organización de GitHub")
            self._db.set_members(org, [{"login": m["login"], "name": m.get("name")}
                                       for m in org_data["membersWithRole"]["nodes"]])
        self._db.set("members_at", self._clock())
        return self._db.members(orgs)

    def _store(self, nodes: list[dict], now: float) -> None:
        """Abiertas a `prs`; las que se cerraron o mergearon salen y quedan como referencia."""
        self._db.upsert_prs([n for n in nodes if n.get("state") not in _CLOSED], _iso(now))
        closed = [n for n in nodes if n.get("state") in _CLOSED]
        known = self._db.pr_snaps([n["url"] for n in closed])
        for n in closed:                        # mergeada/cerrada (por el IDE o por fuera)
            if n["url"] in known:
                self._db.event(_iso(now), "github", n["state"].lower(), pr_url=n["url"],
                               data={"title": n.get("title")})
        self._db.delete_prs(n["url"] for n in closed)
        self._db.put_refs({f"{n['repository']['nameWithOwner'].lower()}#{n['number']}": _ref(n) for n in closed})
        self._keep_closed(closed)

    def _keep_closed(self, nodes: list[dict]) -> None:
        """Las cerradas/mergeadas de un desarrollo con sesión quedan guardadas (`prclosed:<url>`): la
        card las sigue mostrando y, si están todas mergeadas, el desarrollo pasa a "mergeado"."""
        links = self._db.dev_prs()
        for n in nodes:
            if n.get("state") in _CLOSED and n["url"] in links:
                self._db.set(f"prclosed:{n['url']}", {**_card(n), "merged": n["state"] == "MERGED"})

    async def _backfill_closed(self, open_urls: set[str]) -> None:
        """PRs vinculadas que ya no están abiertas y no se guardaron (se cerraron antes de esto): una
        consulta por URL (`resource`), una sola vez."""
        known = self._db.with_prefix("prclosed:")
        urls = [u for u, l in self._db.dev_prs().items()
                if not l.get("out") and u not in open_urls and u not in known][:20]
        if not urls:
            return
        q = "query(%s) { %s }" % (", ".join(f"$u{i}: URI!" for i in range(len(urls))),
                                  " ".join(f"r{i}: resource(url: $u{i}) {{ {_FIELDS} }}" for i in range(len(urls))))
        args = ["-f", f"query={q}"] + [x for i, u in enumerate(urls) for x in ("-f", f"u{i}={u}")]
        data = json.loads(await _graphql(self._gh, args)).get("data") or {}
        self._keep_closed([n for n in data.values() if n])

    def _closed(self) -> list[dict]:
        links = self._db.dev_prs()
        return [c for u, c in self._db.with_prefix("prclosed:").items() if u in links and not links[u].get("out")]

    async def _sync(self, scope: str) -> str:
        """Trae a la base lo que cambió. Devuelve el login del viewer."""
        now = self._clock()
        last_full, last_inc = self._db.get("last_full") or 0, self._db.get("last_inc") or 0
        if now - last_full >= FULL_EVERY:
            me, nodes, total = await search_all(self._gh, f"is:pr is:open archived:false {scope}")
            # la búsqueda de GitHub a veces responde a medias (p.ej. 50 nodos, issueCount 0 y sin
            # más páginas): solo se borran las que faltan si el resultado cuadra; si no, se guarda lo
            # que llegó y se reintenta en el próximo ciclo (no se marca last_full)
            complete = total == len(nodes) or (total > len(nodes) >= MAX_PAGES * 50)
            cached = self._db.open_prs()
            fresh = {n["url"] for n in nodes}
            gone = [n["url"] for n in cached if n["url"] not in fresh]
            # degenerada: vacía con caché (nunca se acepta), o se llevaría de golpe más del 30% (y más de
            # 10): esa se acepta solo si la resincronización siguiente trae lo mismo (un cierre masivo
            # real no se traba)
            drastic = bool(cached) and len(gone) > max(10, 0.3 * len(cached))
            if cached and not nodes:
                complete = False
            elif complete and drastic and self._db.get("full_suspect") != len(nodes):
                self._db.set("full_suspect", len(nodes))
                complete = False
            info = {"at": _iso(now), "nodes": len(nodes), "issueCount": total, "cached": len(cached),
                    "gone": len(gone), "ok": complete}
            if complete:
                self._db.delete("full_suspect")
                self._db.delete_prs(gone)
                log.info("resincronización de PRs: %d de GitHub (issueCount %d), %d en caché, saqué %d",
                         len(nodes), total, len(cached), len(gone))
            else:
                log.warning("resincronización de PRs sospechosa (%d nodos, issueCount %d, %d en caché, sacaría %d): "
                            "no se borra nada, reintento", len(nodes), total, len(cached), len(gone))
                self._db.event(_iso(now), "github", "resync-suspect", data=info)
            self._db.set("last_sync", info)         # la UI lo muestra (⚠ sync) si no salió bien
            self._store(nodes, now)
            if complete:
                self._db.set("truncated", total > len(nodes))
                self._db.set("last_full", now)
        else:
            since = _iso(last_inc - 60)             # 1 min de solape: relojes y latencia
            me, nodes, _ = await search_all(self._gh, f"is:pr archived:false {scope} updated:>={since}")
            self._store(nodes, now)
        self._db.set("last_inc", now)
        self._db.set("me", me)
        # lo dinámico (CI, conflicto, review) no cambia `updatedAt`: refrescar las relevantes
        ids = self._relevant_ids(me)
        if ids:
            self._store(await fetch_nodes(self._gh, ids), now)
        return me

    def _relevant_ids(self, me: str) -> list[str]:
        """Mías, las que reviso o me pidieron, las de sus stacks y sus dependencias abiertas."""
        nodes = self._db.open_prs()
        by_url = {n["url"]: n for n in nodes}
        stacks = compute_stacks(nodes)
        rel = {n["url"] for n in nodes
               if (n.get("author") or {}).get("login") == me or me in _requested(n)
               or any((r.get("author") or {}).get("login") == me
                      for r in (n.get("latestOpinionatedReviews") or {}).get("nodes", []))}
        ids = {stacks[u]["id"] for u in rel if u in stacks}
        rel |= {u for u, st in stacks.items() if st["id"] in ids}
        by_key = {(n["repository"]["nameWithOwner"].lower(), n["number"]): n["url"] for n in nodes}
        for u in list(rel):
            n = by_url[u]
            for full, num in self._with_overrides(u, gh_deps.parse_deps(
                    n.get("body"), *n["repository"]["nameWithOwner"].split("/", 1), n["number"])):
                if (k := (full.lower(), num)) in by_key:
                    rel.add(by_key[k])
        return [by_url[u]["id"] for u in rel if by_url[u].get("id")]

    def _data(self, me: str) -> dict:
        """El mismo formato de antes (`parse_result`), armado desde la base."""
        nodes = self._db.open_prs()
        reviewed = [n for n in nodes if any((r.get("author") or {}).get("login") == me
                                            for r in (n.get("latestOpinionatedReviews") or {}).get("nodes", []))]
        total = len(nodes) + (1 if self._db.get("truncated") else 0)
        return {"data": {"viewer": {"login": me}, "reviewed": {"nodes": reviewed},
                         "open": {"nodes": nodes, "issueCount": total}}}

    # -- dependencias declaradas en el IDE (`ide dep`), además de las de la descripción ------------
    def _with_overrides(self, url: str, parsed: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """Las de la descripción, menos las ignoradas, más las agregadas en el IDE (`kv deps:<url>`)."""
        ov = self._db.get(f"deps:{url}") or {}
        ign = {r for u in ov.get("ignore") or [] if (r := gh_deps.ref_of(u))}
        out = [(f, n) for f, n in parsed if (f.lower(), n) not in ign]
        for u in ov.get("add") or []:
            r = gh_deps.ref_of(u)
            if r and r not in {(f.lower(), n) for f, n in out}:
                out.append(r)
        return out

    def dep_sources(self, url: str) -> dict:
        """De dónde sale cada dependencia directa de `url`: la descripción, el IDE, o ignorada."""
        node = next((n for n in self._db.open_prs() if n["url"] == url), None)
        parsed = gh_deps.parse_deps(node.get("body"), *node["repository"]["nameWithOwner"].split("/", 1),
                                    node["number"]) if node else []
        ov = self._db.get(f"deps:{url}") or {}
        return {"pr": url, "known": node is not None,
                "description": [f"https://github.com/{f}/pull/{n}" for f, n in parsed],
                "added": list(ov.get("add") or []), "ignored": list(ov.get("ignore") or [])}

    def set_deps(self, url: str, *, add: list[str] = (), remove: list[str] = (), ignore: bool = False) -> dict:
        ov = self._db.get(f"deps:{url}") or {}
        added, ignored = list(ov.get("add") or []), list(ov.get("ignore") or [])
        for u in add:
            if u != url and u not in added:
                added.append(u)
            if u in ignored:
                ignored.remove(u)
        for u in remove:
            if u in added:
                added.remove(u)
            if ignore and u not in ignored:
                ignored.append(u)
        if added or ignored:
            self._db.set(f"deps:{url}", {"add": added, "ignore": ignored})
        else:
            self._db.delete(f"deps:{url}")
        return self.dep_sources(url)

    async def _annotate_deps(self, res: dict, data: dict, *, offline: bool = False) -> None:
        """Agrega a cada card `deps` (cadena de dependencias declaradas) y `depsPending`."""
        prs = [n for n in data["data"]["open"]["nodes"] if n]
        by_key = {(n["repository"]["nameWithOwner"].lower(), n["number"]): n for n in prs}
        info = {n["url"]: {"repo": n["repository"]["name"], "number": n["number"], "title": n["title"],
                           "state": "OPEN"} for n in prs}
        refs = {n["url"]: gh_deps.parse_deps(n.get("body"), *n["repository"]["nameWithOwner"].split("/", 1),
                                             n["number"]) for n in prs}
        refs = {u: self._with_overrides(u, lst) for u, lst in refs.items()}
        unknown = sorted({(full.lower(), num) for lst in refs.values() for full, num in lst
                          if (full.lower(), num) not in by_key})
        cached = self._db.get_refs(f"{f}#{n}" for f, n in unknown)
        missing = [(f, n) for f, n in unknown if f"{f}#{n}" not in cached]
        found = await gh_deps.resolve(self._gh, missing) if missing and not offline else {}
        # las mergeadas/cerradas no cambian más: quedan en la base
        self._db.put_refs({f"{k[0]}#{k[1]}": v for k, v in found.items() if v.get("state") in _CLOSED})
        url_of = {k: n["url"] for k, n in by_key.items()}
        for key, pr in [*((tuple(k.rsplit("#", 1)), v) for k, v in cached.items()), *found.items()]:
            full, num = key[0], int(key[1])
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

    def _record_events(self, res: dict) -> None:
        """Historial de lo que pasa en GitHub (también lo hecho por fuera del IDE): compara la foto
        de cada PR relevante con la anterior y deja un evento por cada cambio."""
        cards = {c["url"]: c for lst in [res["pending"], res["changesRequested"], *res["mine"].values(),
                                         *res["stacks"].values()] for c in lst}
        snaps = {u: {"review": c.get("review"), "ci": c.get("ci"), "draft": c.get("draft"),
                     # None = GitHub todavía lo está calculando (UNKNOWN): se mantiene el de antes
                     "conflict": None if c.get("mergeable") not in ("MERGEABLE", "CONFLICTING") else bool(c.get("conflict")),
                     "reviewers": {r["login"]: r["state"] for r in c.get("reviewers") or []}}
                 for u, c in cards.items()}
        prev = self._db.pr_snaps(list(snaps))
        for url, cur in snaps.items():
            if cur["conflict"] is None and url in prev:
                cur["conflict"] = prev[url].get("conflict")
        at = _iso(self._clock())
        for url, cur in snaps.items():
            old = prev.get(url)
            if old is None:                     # primera vez que la vemos: sin evento (no inundar)
                continue
            for login, state in cur["reviewers"].items():
                if old["reviewers"].get(login) != state:
                    self._db.event(at, "github", {"requested": "review-requested"}.get(state, "review"),
                                   pr_url=url, data={"by": login, "state": state})
            if cur["ci"] != old["ci"] and cur["ci"] in ("success", "failure"):
                self._db.event(at, "github", "ci", pr_url=url, data={"state": cur["ci"]})
            if old["draft"] and not cur["draft"]:
                self._db.event(at, "github", "ready-for-review", pr_url=url)
            # pasó a conflicto (queda en el historial; no se avisa ni se rebasea: se resuelve al mergear)
            if cur["conflict"] and old.get("conflict") is False:
                self._db.event(at, "github", "conflict", pr_url=url)
        self._db.put_pr_snaps(snaps)

    def optimistic(self, url: str, *, requested: list[str] = (), verdict: tuple[str, str] | None = None) -> None:
        """Lo que el IDE acaba de hacer, sin esperar el próximo poll (que lo corrige si GitHub dice
        otra cosa): `requested` = a quiénes se les pidió (re)review → esperando; `verdict` = (login,
        approved|changes) de un review publicado."""
        st = self.state or {}
        cards = [c for lst in [st.get("pending") or [], st.get("changesRequested") or [],
                               *(st.get("mine") or {}).values(), *(st.get("stacks") or {}).values()]
                 for c in lst if c.get("url") == url]
        for c in cards:
            revs = {r["login"]: r["state"] for r in c.get("reviewers") or []}
            for login in requested:
                revs[login] = "requested"
            if verdict:
                revs[verdict[0]] = verdict[1]
            c["reviewers"] = [{"login": k, "state": v} for k, v in revs.items()]
            states = set(revs.values())
            # como `review_state`: un revisor con cambios pedidos manda (al que se le re-pidió ya está en requested)
            c["review"] = "changes" if "changes" in states else "review" if "requested" in states \
                else "approved" if "approved" in states else c.get("review")
        mine = st.get("mine") or {}
        group = {"changes": "returned", "review": "waiting", "approved": "approved"}
        for g, lst in list(mine.items()):                # Mis PRs: que la card cambie de grupo también
            for c in [c for c in lst if c.get("url") == url and not c.get("draft")]:
                to = group.get(c.get("review") or "")
                if to and to != g:
                    lst.remove(c)
                    mine.setdefault(to, []).append(c)
        if cards:
            self._on_change()

    async def set_selection(self, logins: list[str]) -> None:
        self._db.set("reviewers", sorted({str(x) for x in logins}, key=str.lower))
        self.state = {**self.state, "selected": self._db.get("reviewers")}
        self._on_change()

    async def warm_start(self) -> None:
        """Al arrancar, el estado sale de la base (lo de la última consulta) sin ir a GitHub: la primera
        consulta demora y, mientras, la sidebar mostraría los desarrollos sin las fases de sus PRs."""
        me = self._db.get("me")
        orgs = [self._org] if self._org else await asyncio.to_thread(workspace_orgs, self._root)
        if not me or not orgs or not self._db.open_prs():
            return
        members = self._db.members(orgs)
        data = self._data(me)
        res = parse_result(data, {m["login"] for m in members})
        await self._annotate_deps(res, data, offline=True)
        res["closed"] = self._closed()
        last = max(self._db.get("last_inc") or 0, self._db.get("last_full") or 0)
        self.state = {**res, "members": members, "selected": self._db.get("reviewers"), "error": None,
                      "lastOk": _iso(last) if last else None, "orgs": orgs, "sync": self._db.get("last_sync")}
        self._on_change()

    def _active_dev_prs(self) -> set[str]:
        """Las PRs vinculadas a un desarrollo con sesión viva y en curso: no archivada, no pausada ni mergeada.
        (Una PR suelta o vieja aprobada hace meses no se toca.)"""
        from ide_server.sessions_fs import session_path
        out = set()
        for url, link in self._db.dev_prs().items():
            sid = link.get("sid")
            if not sid or link.get("out") or not (session_path(self._root, sid) / ".session.toml").is_file():
                continue
            st = self._db.get(f"devstate:s:{sid}") or {}
            if st.get("block") == "paused" or st.get("phase") == "merged":
                continue
            out.add(url)
        return out

    async def _ready_approved(self, res: dict, me: str) -> None:
        """Una PR tuya en draft que quedó aprobada (sin revisiones pedidas pendientes) sale de draft sola:
        en el equipo se revisa en draft y el CI corre después de aprobar. También las hijas de un stack
        (el CI corre apenas puede). Queda en el historial; si `gh` falla, se reintenta en 30 min."""
        tried = self.__dict__.setdefault("_ready_tried", {})
        active = self._active_dev_prs()
        for c in [c for lst in (res.get("mine") or {}).values() for c in lst]:
            if c["url"] not in active:          # solo PRs de un desarrollo en curso (no sueltas, ni pausados)
                continue
            if not c.get("draft") or c.get("review") != "approved" or c.get("author") != f"@{me}" \
                    or any(r.get("state") == "requested" for r in c.get("reviewers") or []) \
                    or self._clock() - tried.get(c["url"], 0) < 1800:
                continue
            tried[c["url"]] = self._clock()
            code, _, err = await self._gh(["pr", "ready", c["url"]])
            if code != 0:
                log.warning("gh pr ready %s: %s", c["url"], err.strip())
                continue
            c["draft"] = False
            self._db.event(_iso(self._clock()), "ide", "ready-for-review", pr_url=c["url"],
                           data={"note": "sacada de draft por el IDE al aprobarse"})

    async def poll_once(self) -> None:
        orgs = [self._org] if self._org else await asyncio.to_thread(workspace_orgs, self._root)
        prev = self.state
        if not orgs:
            self.state = {**prev, "error": "no hay org de GitHub: configura [reviews] github_org"}
        else:
            scope = " ".join(f"org:{o}" for o in orgs)
            try:
                me = await self._sync(scope)
                members = await self._members(orgs)
                data = self._data(me)
                res = parse_result(data, {m["login"] for m in members})
                await self._annotate_deps(res, data)
                self._record_events(res)
                try:
                    await self._ready_approved(res, me)
                except Exception:  # noqa: BLE001 — sacar de draft no tumba el poll
                    log.exception("sacar de draft las PRs aprobadas")
                try:
                    await self._backfill_closed({n["url"] for n in data["data"]["open"]["nodes"] if n})
                except Exception:  # noqa: BLE001 — lo de las mergeadas no tumba el resto
                    log.exception("PRs cerradas de los desarrollos")
                res["closed"] = self._closed()
                self.state = {**res, "members": members, "selected": self._db.get("reviewers"),
                              "error": None, "lastOk": _iso(self._clock()), "orgs": orgs,
                              "sync": self._db.get("last_sync")}
            except RuntimeError as exc:
                self.state = {**prev, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 — queda marcado, nunca silencioso
                log.exception("poll de GitHub")
                self.state = {**prev, "error": f"respuesta inválida de gh: {exc}"}
        if {k: v for k, v in self.state.items() if k != "lastOk"} != \
           {k: v for k, v in prev.items() if k != "lastOk"}:
            self._on_change()

    async def run(self, stop: asyncio.Event) -> None:
        if self._interval <= 0:
            return
        try:
            await self.warm_start()
        except Exception:  # noqa: BLE001 — sin esto, solo se espera la primera consulta
            log.exception("estado inicial de GitHub desde la base")
        while not stop.is_set():
            try:
                await self.poll_once()
            except Exception:
                log.exception("el poller de revisiones de GitHub falló; sigue en el próximo")
            try:
                await asyncio.wait_for(stop.wait(), self._interval)
            except asyncio.TimeoutError:
                pass
