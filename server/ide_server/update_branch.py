# server/ide_server/update_branch.py
"""`ide update`: pone al día la rama de un worktree de la sesión sobre su base, **solo cuando hace falta**:
la PR está en conflicto con su base, o su madre del stack se mergeó (con squash). Que `develop` haya
avanzado (BEHIND) no basta: rebasear por eso cambia los commits y vuelve a correr todo el CI (al mergear,
si GitHub exige la rama al día, la pone al día el IDE). Rebasea en el mismo worktree; si choca, deja el
rebase a medias para que la sesión resuelva y siga (`git rebase --continue` + `ide push --force`)."""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from typing import TextIO
from ide_server.gh_merge import squashed_parent
from ide_server.push import PROTECTED, _default_branch
from ide_server.repos_fs import require_session
from ide_server.sessions_fs import SessionError, repo_links


def _git(wt: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, timeout=timeout)


def _gh(wt: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=wt, capture_output=True, text=True, timeout=120)


def _slug(wt: Path) -> str | None:
    url = _git(wt, "remote", "get-url", "origin").stdout.strip()
    return re.sub(r"\.git$", "", re.split(r"github\.com[:/]", url)[-1]) if "github.com" in url else None


def plan(wt: Path, branch: str) -> dict:
    """Qué haría (sin tocar nada): {pr, reason, onto, upstream, new_base} o {pr, skip: motivo}."""
    out = _gh(wt, "pr", "view", branch, "--json", "number,url,state,baseRefName,mergeable,mergeStateStatus")
    if out.returncode != 0:
        return {"skip": f"la rama {branch} no tiene PR: sin PR no hay conflicto que resolver"}
    pr = json.loads(out.stdout)
    if pr["state"] != "OPEN":
        return {"pr": pr, "skip": f"la PR #{pr['number']} está {pr['state'].lower()}"}
    base, full = pr["baseRefName"], _slug(wt)
    # la madre del stack (la rama base) ya se mergeó: rebasear lo propio sobre la base de la madre
    # (si la base es una rama principal no hay madre: una PR mergeada desde develop sería un release)
    main = base in PROTECTED or base == _default_branch(wt)
    mother = None if main else _gh(wt, "pr", "list", "--head", base, "--state", "merged",
                                   "--json", "number,headRefOid,baseRefName", "--limit", "1")
    merged = json.loads(mother.stdout or "[]") if mother is not None and mother.returncode == 0 else []
    if merged:
        m = merged[0]
        return {"pr": pr, "reason": f"su madre #{m['number']} ({base}) se mergeó", "onto": f"origin/{m['baseRefName']}",
                "upstream": m["headRefOid"], "new_base": m["baseRefName"]}
    # GitHub ya la re-apuntó, pero arrastra los commits de la madre squasheada
    cut = squashed_parent(wt, branch, base, full, pr["number"])
    if cut:
        return {"pr": pr, "reason": "arrastra commits de una madre que se mergeó con squash",
                "onto": f"origin/{base}", "upstream": cut}
    if pr.get("mergeable") == "CONFLICTING":
        return {"pr": pr, "reason": f"está en conflicto con {base}", "onto": f"origin/{base}"}
    state = pr.get("mergeStateStatus") or pr.get("mergeable") or "?"
    why = ("solo está atrás de su base (BEHIND): eso no basta, no se actualiza" if state == "BEHIND"
           else "GitHub todavía está calculando si tiene conflicto: prueba en un rato" if pr.get("mergeable") == "UNKNOWN"
           else f"no tiene conflicto ni madre mergeada ({state}): no hace falta")
    return {"pr": pr, "skip": why}


def update(root: Path, sid: str, repo: str | None, *, dry_run: bool = False, out: TextIO) -> int:
    links = {p.name: p for p in repo_links(require_session(root, sid))}
    if repo is not None and repo not in links:
        raise SessionError("unknown_repo", f"la sesión {sid} no tiene {repo} (tiene: {', '.join(links) or 'ninguno'})")
    failed = 0
    for name in [repo] if repo else sorted(links):
        wt = links[name].resolve()
        branch = _git(wt, "branch", "--show-current").stdout.strip()
        if not branch:
            out.write(f"{name}: sin rama (detached o rebase a medias), no hago nada\n"); failed += 1; continue
        if branch in PROTECTED or branch == _default_branch(wt):
            out.write(f"{name}: {branch} es una rama principal, no la toco\n"); failed += 1; continue
        _git(wt, "fetch", "origin", "--prune")
        p = plan(wt, branch)
        if "skip" in p:
            out.write(f"{name}: {branch}: {p['skip']}\n")
            continue
        n = p["pr"]["number"]
        if dry_run:
            out.write(f"{name}: #{n} {p['reason']}: rebasearía sobre {p['onto']}\n")
            continue
        if _git(wt, "status", "--porcelain", "--untracked-files=no").stdout.strip():
            out.write(f"{name}: #{n} {p['reason']}, pero tienes cambios sin commitear: commitea o guárdalos antes\n")
            failed += 1; continue
        old = _git(wt, "rev-parse", "HEAD").stdout.strip()
        r = _git(wt, "rebase", *(["--onto", p["onto"], p["upstream"]] if p.get("upstream") else [p["onto"]]))
        if r.returncode != 0:
            out.write(f"{name}: #{n} {p['reason']}: el rebase sobre {p['onto']} chocó y quedó a medias en {wt}.\n"
                      f"  Resuelve los archivos en conflicto, `git -C {wt} add …` y `git -C {wt} rebase --continue`;"
                      f" después `ide push {name} --force`. (Para volver atrás: `git -C {wt} rebase --abort`.)\n")
            failed += 1; continue
        push = _git(wt, "push", f"--force-with-lease={branch}:{old}", "origin", f"HEAD:refs/heads/{branch}")
        if push.returncode != 0:
            out.write(f"{name}: #{n} rebaseada, pero el push falló: {push.stderr.strip().splitlines()[-1:]}\n")
            failed += 1; continue
        if p.get("new_base") and p["new_base"] != p["pr"]["baseRefName"]:
            _gh(wt, "pr", "edit", str(n), "--base", p["new_base"])
        out.write(f"{name}: #{n} {p['reason']}: rebaseada sobre {p['onto']} y subida"
                  + (f"; base ahora {p['new_base']}" if p.get("new_base") else "") + "\n")
    return 1 if failed else 0


def migrations_cmd(root: Path, sid: str, repo: str | None, *, fix: bool, out: TextIO) -> int:
    """`ide migrations check|renumber`: las migraciones de la rama de cada worktree contra la base de su PR
    (o develop); `renumber` las corrige con un commit y sube la rama (sin --force)."""
    from ide_server import migrations
    links = {p.name: p for p in repo_links(require_session(root, sid))}
    if repo is not None and repo not in links:
        raise SessionError("unknown_repo", f"la sesión {sid} no tiene {repo} (tiene: {', '.join(links) or 'ninguno'})")
    failed = 0
    for name in [repo] if repo else sorted(links):
        wt = links[name].resolve()
        branch = _git(wt, "branch", "--show-current").stdout.strip()
        if not branch:
            out.write(f"{name}: sin rama, no reviso\n"); continue
        _git(wt, "fetch", "origin", "--prune")
        pr = _gh(wt, "pr", "view", branch, "--json", "baseRefName")
        base = json.loads(pr.stdout)["baseRefName"] if pr.returncode == 0 else "develop"
        try:
            plan = migrations.plan(wt, f"origin/{base}", "HEAD")
        except RuntimeError as exc:
            out.write(f"{name}: no pude revisar: {exc}\n"); failed += 1; continue
        if plan["ok"]:
            out.write(f"{name}: migraciones OK contra {base}\n"); continue
        out.write(f"{name}: chocan con {base}:\n{migrations.describe(plan)}\n")
        if not fix:
            failed += 1; continue
        if _git(wt, "status", "--porcelain", "--untracked-files=no").stdout.strip():
            out.write(f"{name}: tienes cambios sin commitear: commitea o guárdalos antes\n"); failed += 1; continue
        try:
            touched = migrations.renumber(wt, plan)
        except RuntimeError as exc:
            out.write(f"{name}: no pude renumerar: {exc}\n"); failed += 1; continue
        push = _git(wt, "push", "origin", f"HEAD:refs/heads/{branch}")
        out.write(f"{name}: renumeradas ({', '.join(touched)}), commit "
                  + ("subido" if push.returncode == 0 else f"local; el push falló: {push.stderr.strip()[-200:]}") + "\n")
        failed += push.returncode != 0
    return 1 if failed else 0
