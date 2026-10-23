# server/ide_server/server_blocks.py
"""Bloques del módulo Servidores (la misma regla que la UI, `ui/src/modules/servers/place.ts`), para
`ide server`: un bloque por stack de cada repo del desarrollo (y uno por repo de la sesión cuya rama
no tiene PR). Un stack corre desde la rama de su PR de más arriba; en el worktree de la sesión si está
en la rama de alguna PR del stack, si no en uno aparte (`wt-<repo>-<n>`, se crea al correr)."""
from __future__ import annotations
import re
from pathlib import Path
from ide_server import pr_worktrees
from ide_server.runs import _branch
from ide_server.repos_fs import worktree_path
from ide_server.sessions_fs import SessionError
from ide_server.scripts import list_scripts

HIDDEN = {"archive"}


def short(repo: str) -> str:
    return re.sub(r"^finnecto-", "", repo or "")


def blocks(root: Path, dev: dict, session: dict | None) -> list[dict]:
    """`dev`: el de `list_devs` (prs con head/stack/deps); `session`: la de la sesión (repos con rama)."""
    prs = dev.get("prs") or []
    by_repo: dict[str, dict[str, list[dict]]] = {}
    for p in prs:
        key = (p.get("stack") or {}).get("id") or p["url"]
        by_repo.setdefault(p["repo"], {}).setdefault(key, []).append(p)
    sess_repos = [r for r in (session or {}).get("repos") or [] if r.get("state") == "ok"]
    places = {p["id"]: p for p in pr_worktrees.list_places(root)}
    out, covered = [], set()
    for repo in sorted(by_repo):
        for stack in by_repo[repo].values():
            stack.sort(key=lambda p: (p.get("stack") or {}).get("position", 0))
            top = stack[-1]
            heads = [p.get("head") for p in stack]
            wt = next((r for r in sess_repos if r["name"] == repo and r.get("branch") in heads), None)
            if wt and session:
                covered.add(repo)
                out.append({"repo": repo, "prs": stack, "place": session["id"], "where": "session", "exists": True,
                            "branch": wt.get("branch"), "top": top})
            else:
                place = pr_worktrees.place_for(top["url"])[0]
                found = places.get(place)
                exists = bool(found and repo in found["repos"])
                out.append({"repo": repo, "prs": stack, "place": place, "where": "pr", "exists": exists,
                            "branch": (found or {}).get("heads", {}).get(repo) if exists else top.get("head"), "top": top})
    for r in sess_repos:
        if r["name"] not in covered and session:
            out.append({"repo": r["name"], "prs": [], "place": session["id"], "where": "session", "exists": True,
                        "branch": r.get("branch"), "top": None})
    for b in out:
        b["name"] = f"{short(b['repo'])}#{b['top']['number']}" if b["top"] else short(b["repo"])
        b["scripts"] = [s["name"] for s in list_scripts(root, b["repo"]) if s["name"] not in HIDDEN]
        b["front"] = "point-api" in b["scripts"]
    return out


def find(bl: list[dict], ref: str) -> dict:
    """Un bloque por una de sus PRs (`api#4897`, `finnecto-api#4897`, URL) o por su repo (`admin`) si es
    el único bloque de ese repo."""
    ref = ref.strip()
    m = re.search(r"([\w.-]+)(?:#|/pull/)(\d+)$", ref)
    if m:
        repo, n = m.group(1), int(m.group(2))
        for b in bl:
            if short(b["repo"]) in (repo, short(repo)) and any(p["number"] == n for p in b["prs"]):
                return b
        raise SessionError("unknown_block", f"ningún bloque tiene la PR {ref} (mira `ide server ls`)")
    same = [b for b in bl if short(b["repo"]) == short(ref)]
    if len(same) == 1:
        return same[0]
    if not same:
        raise SessionError("unknown_block", f"no hay bloque de {ref} (mira `ide server ls`)")
    raise SessionError("ambiguous_block", f"{ref} tiene {len(same)} bloques: nómbralo por su PR ("
                       + ", ".join(b["name"] for b in same) + ")")


def default_api(bl: list[dict], b: dict, run_of) -> dict | None:
    """La api de un front: la del bloque de la PR de la que depende; si no, la única api corriendo."""
    apis = [a for a in bl if not a["front"] and "run" in a["scripts"]]
    deps = {d.get("url") for p in b["prs"] for d in p.get("deps") or []}
    dep = next((a for a in apis if any(p["url"] in deps for p in a["prs"])), None)
    if dep:
        return dep
    running = [a for a in apis if (run_of(a, "run") or {}).get("state") == "running"]
    return running[0] if len(running) == 1 else None


def port_of(run: dict | None) -> int | None:
    for u in (run or {}).get("urls") or []:
        if m := re.search(r":(\d+)(?:/|$)", u):
            return int(m.group(1))
    return None


def ensure_worktree(root: Path, b: dict) -> None:
    if b["where"] == "pr" and not b["exists"] and b["top"]:
        pr_worktrees.ensure(root, b["top"]["url"])
    if not worktree_path(root, b["place"], b["repo"]).is_dir():
        raise SessionError("unknown_worktree", f"no hay worktree de {b['repo']} en {b['place']}")


__all__ = ["blocks", "find", "default_api", "port_of", "ensure_worktree", "_branch"]
