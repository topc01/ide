# server/ide_server/gh_deps.py
"""Dependencias entre PRs declaradas en la sección `## Dependencias` de la descripción (la
plantilla de PR de Finnecto). Solo se leen y se muestran; no frenan el merge (avisan).

Reglas de parseo (las casillas `[ ]`/`[x]` se ignoran: hay líneas sin marcar con dependencias reales):
- Referencias `owner/repo#N`, `repo#N`, `#N` o URLs `github.com/owner/repo/pull/N`.
- Un `#N` suelto hereda el último repo explícito de la misma línea ("api#4581 → #4583"); si no
  hay, es del repo de la PR.
- En una línea con "este/esta PR" (p.ej. "merge en orden: A → B → este PR → C") solo cuenta lo
  que va antes: lo de después depende de esta, no al revés.
- Si A depende de B y B (directa o indirectamente) de A, "van juntas": se muestran, no frenan."""
from __future__ import annotations
import json
import re
from typing import Awaitable, Callable

GhRunner = Callable[[list[str]], Awaitable[tuple[int, str, str]]]
_SECTION_RE = re.compile(r"^#{1,6}\s*dependencias\b.*$", re.I | re.M)
_HEADING_RE = re.compile(r"^#{1,6}\s", re.M)
_SELF_RE = re.compile(r"\b(?:este|esta)\b(?:\s+(?:PR|pull request))?", re.I)
_REF_RE = re.compile(
    r"github\.com/(?P<uo>[\w.-]+)/(?P<ur>[\w.-]+)/pull/(?P<un>\d+)"
    r"|(?:(?P<o>[\w.-]+)/)?(?P<r>[A-Za-z][\w.-]*)?#(?P<n>\d+)")


def deps_section(body: str | None) -> str:
    m = _SECTION_RE.search(body or "")
    if not m:
        return ""
    rest = body[m.end():]
    nxt = _HEADING_RE.search(rest)
    return rest[: nxt.start()] if nxt else rest


def parse_deps(body: str | None, owner: str, repo: str, number: int) -> list[tuple[str, int]]:
    """[(owner/repo, número)] de las dependencias directas declaradas, sin la propia PR."""
    out: list[tuple[str, int]] = []
    for line in deps_section(body).splitlines():
        if (m := _SELF_RE.search(line)) and _REF_RE.search(line[m.end():]):
            line = line[: m.start()]            # lo que va después de "este PR" depende de esta
        last = f"{owner}/{repo}"
        for r in _REF_RE.finditer(line):
            if r.group("un"):
                full, n = f"{r.group('uo')}/{r.group('ur')}", int(r.group("un"))
                last = full
            else:
                n = int(r.group("n"))
                if r.group("r"):
                    full = f"{r.group('o') or owner}/{r.group('r')}"
                    last = full
                else:
                    full = last
            key = (full.lower(), n)
            if key != (f"{owner}/{repo}".lower(), number) and key not in [(a.lower(), b) for a, b in out]:
                out.append((full, n))
    return out


async def resolve(gh: GhRunner, refs: list[tuple[str, int]]) -> dict[tuple[str, int], dict]:
    """Estado de PRs que no están entre las abiertas (mergeadas/cerradas), en lotes de 40."""
    found: dict[tuple[str, int], dict] = {}
    for i in range(0, len(refs), 40):
        batch = refs[i:i + 40]
        parts = []
        for k, (full, n) in enumerate(batch):
            o, r = full.split("/", 1)
            parts.append(f'p{k}: repository(owner: {json.dumps(o)}, name: {json.dumps(r)}) '
                         f'{{ pullRequest(number: {n}) {{ url title number state }} }}')
        code, out, _err = await gh(["api", "graphql", "-f", "query={ " + " ".join(parts) + " }"])
        try:
            data = json.loads(out).get("data") or {}
        except ValueError:
            data = {}
        for k, ref in enumerate(batch):     # repos inexistentes o #N que es issue: se ignoran
            pr = ((data.get(f"p{k}") or {}).get("pullRequest"))
            if pr:
                found[(ref[0].lower(), ref[1])] = pr
    return found


def chains(direct: dict[str, list[str]], info: dict[str, dict], url: str) -> list[dict]:
    """Dependencias de `url` (directas y transitivas) con su estado y si van juntas."""
    seen: dict[str, str | None] = {}            # dep -> por cuál directa se llega (None = directa)
    todo = [(d, None) for d in direct.get(url, [])]
    while todo:
        d, via = todo.pop(0)
        if d == url or d in seen:
            continue
        seen[d] = via
        todo += [(x, via or d) for x in direct.get(d, [])]

    def reaches(a: str, b: str) -> bool:        # a depende (transitivamente) de b
        stack, vis = list(direct.get(a, [])), set()
        while stack:
            x = stack.pop()
            if x == b:
                return True
            if x not in vis:
                vis.add(x)
                stack += direct.get(x, [])
        return False

    out = []
    for d, via in seen.items():
        i = info.get(d) or {}
        out.append({"url": d, "repo": i.get("repo"), "number": i.get("number"), "title": i.get("title"),
                    "state": i.get("state", "UNKNOWN"), "via": via, "together": reaches(d, url)})
    return out
