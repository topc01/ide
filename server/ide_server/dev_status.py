# server/ide_server/dev_status.py
"""`ide dev status`: el estado de tu desarrollo en una sola tabla, en vez de recorrer repo por repo con git y PR por
PR con gh. Por repo de la sesión: la rama del worktree, si hay cambios sin commitear, commits sin subir y cuántos
le faltan de su base (según el último fetch; `--fetch` trae origin antes), y debajo sus PRs abiertas del desarrollo
con draft, revisión y CI (lo que el IDE ya sabe de GitHub, sin pedirlo de nuevo)."""
from __future__ import annotations
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TextIO

from ide_server.sessions_fs import session_path

_REVIEW = {"review": "en revisión", "changes": "CAMBIOS PEDIDOS", "approved": "aprobada", None: "sin revisor"}


def _git(wt: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _count(wt: Path, rng: str) -> int | None:
    n = _git(wt, "rev-list", "--count", rng)
    return int(n) if n.isdigit() else None


def worktree(wt: Path, base: str | None, fetch: bool) -> dict:
    if fetch:
        _git(wt, "fetch", "--quiet", "origin")
    branch = _git(wt, "branch", "--show-current")
    dirty = [x for x in _git(wt, "status", "--porcelain").splitlines() if x.strip()]
    up = _git(wt, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    remote = up or (f"origin/{branch}" if _git(wt, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}") else "")
    return {"branch": branch, "dirty": len(dirty), "remote": remote,
            "unpushed": _count(wt, f"{remote}..HEAD") if remote else None,
            "behind_base": _count(wt, f"HEAD..origin/{base}") if base else None, "base": base}


def render(dev: dict, root: Path, sid: str, out: TextIO, *, fetch: bool = False) -> int:
    prs = dev.get("prs") or []
    repos = dev.get("repos") or []
    base_of = {}
    for p in prs:                                    # la base de la PR más de abajo de la rama del worktree
        for r in repos:
            if r["name"] == p["repo"] and r.get("branch") == p.get("head"):
                base_of[r["name"]] = p.get("base")
    with ThreadPoolExecutor(max_workers=6) as ex:
        wts = dict(zip([r["name"] for r in repos], ex.map(
            lambda r: worktree(session_path(root, sid) / r["name"], base_of.get(r["name"]) or "develop", fetch), repos)))
    for r in repos:
        w = wts[r["name"]]
        bits = [f"rama {w['branch'] or '(detached)'}"]
        bits.append(f"{w['dirty']} archivo(s) sin commitear" if w["dirty"] else "limpio")
        if not w["remote"]:
            bits.append("sin rama en origin (sin subir, o ya mergeada y borrada)")
        elif w["unpushed"]:
            bits.append(f"{w['unpushed']} commit(s) sin subir")
        if w["behind_base"]:
            bits.append(f"le faltan {w['behind_base']} commit(s) de origin/{w['base']} (no hace falta actualizar salvo "
                        f"conflicto: `ide update` decide; `--behind` solo si el usuario lo pide)")
        out.write(f"{r['name']}: {', '.join(bits)}\n")
        mine = [p for p in prs if p["repo"] == r["name"]]
        for p in sorted(mine, key=lambda p: (p.get("stack") or {}).get("position", 0)):
            st = p.get("stack") or {}
            flags = [_REVIEW.get(p.get("review"), p.get("review") or "?"), f"ci={p.get('ci') or '-'}"]
            if p.get("draft"):
                flags.append("draft")
            if st.get("size", 1) > 1:
                flags.append(f"stack {st.get('position')}/{st.get('size')}")
            here = " ← tu worktree" if p.get("head") == w["branch"] else ""
            out.write(f"    {p['repo'].removeprefix('finnecto-')}#{p['number']}  {' · '.join(flags)}  {p['title'][:70]}{here}\n")
    other = [p for p in prs if p["repo"] not in wts]
    for p in other:
        out.write(f"{p['repo']}#{p['number']} (sin worktree en la sesión)  "
                  f"{_REVIEW.get(p.get('review'), p.get('review') or '?')} · ci={p.get('ci') or '-'}  {p['title'][:70]}\n")
    if not repos and not prs:
        out.write("el desarrollo no tiene repos ni PRs abiertas\n")
    if not fetch:
        out.write("(commits de origin según el último fetch; `--fetch` los trae antes. Lo pedido en las PRs: `ide review inbox`)\n")
    return 0
