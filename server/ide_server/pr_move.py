# server/ide_server/pr_move.py
"""`ide pr move <pr> --onto <base>`: mueve una PR tuya de una base a otra (p. ej. sacar una PR apilada a su propia
rama desde develop), sin rehacer la rama a mano. En el worktree del repo de la sesión:

1. Frena si la PR toca archivos que no existen en la base nueva (vienen de la base vieja): los lista y no resuelve
   nada solo (hay que pasarlos a la madre o sacarlos de la PR).
2. Re-aplica solo los commits propios de la PR sobre la base nueva (`rebase --onto origin/<nueva> <punto de corte>`;
   si la base vieja se reescribió a mano, el punto de corte sale del reflog, `merge-base --fork-point`). Si choca,
   aborta, deja todo como estaba y lista los archivos.
3. Revisa las migraciones contra la base nueva y, si chocan, las renumera con un commit (`ide migrations renumber`).
4. Sube con `--force-with-lease`, cambia la base de la PR en GitHub y deja el worktree en la rama donde estaba.

La PR queda en el mismo desarrollo (la CLI la asigna antes de mover: si no, una rama desde develop se separaría sola
en otro). Las PRs apiladas encima quedan con la versión vieja: se re-apilan con `ide update`."""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from typing import TextIO

from ide_server.push import PROTECTED
from ide_server.repos_fs import require_session
from ide_server.sessions_fs import SessionError, repo_links


def _git(wt: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, timeout=timeout)


def _gh(wt: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=wt, capture_output=True, text=True, timeout=120)


def _ok_ref(b: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,150}", b)) and ".." not in b \
        and not b.endswith((".lock", "/", "."))


def move(root: Path, sid: str, repo: str, number: int, url: str, *, onto: str, out: TextIO) -> int:
    if not _ok_ref(onto):
        raise SessionError("bad_ref", f"rama inválida: {onto!r} (p. ej. develop)")
    links = {p.name: p for p in repo_links(require_session(root, sid))}
    if repo not in links:
        raise SessionError("unknown_repo", f"la sesión {sid} no tiene {repo} (tiene: {', '.join(links) or 'ninguno'})")
    wt = links[repo].resolve()
    info = _gh(wt, "pr", "view", url, "--json", "headRefName,baseRefName,state,headRefOid,author,isCrossRepository")
    if info.returncode != 0:
        raise SessionError("gh_failed", f"no pude leer {url}: {info.stderr.strip()[-200:]}")
    pr = json.loads(info.stdout)
    me = _gh(wt, "api", "user", "--jq", ".login").stdout.strip()
    head, old = pr["headRefName"], pr["baseRefName"]
    if pr["state"] != "OPEN":
        raise SessionError("not_open", f"{repo}#{number} no está abierta ({pr['state']})")
    if pr.get("isCrossRepository") or not me or (pr.get("author") or {}).get("login") != me:
        raise SessionError("forbidden", f"{repo}#{number} no es una PR tuya de este repo")
    if head in PROTECTED or not _ok_ref(head) or not _ok_ref(old):
        raise SessionError("bad_ref", f"no muevo la rama {head!r}")
    if old == onto:
        out.write(f"{repo}#{number} ya va sobre {onto}: nada que mover\n")
        return 0
    if _git(wt, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise SessionError("dirty", f"{repo}: tienes cambios sin commitear en el worktree: commitea o guárdalos antes")
    if any((wt / _git(wt, "rev-parse", "--git-path", d).stdout.strip()).exists() for d in ("rebase-merge", "rebase-apply")):
        raise SessionError("rebasing", f"{repo}: hay un rebase a medias en el worktree: termínalo o abórtalo antes")
    for b in {head, old, onto}:
        r = _git(wt, "fetch", "origin", f"+refs/heads/{b}:refs/remotes/origin/{b}")
        if r.returncode != 0:
            raise SessionError("fetch_failed", f"no pude traer origin/{b}: {r.stderr.strip()[-200:]}")
    tip = _git(wt, "rev-parse", f"origin/{head}").stdout.strip()
    if tip != pr["headRefOid"]:
        raise SessionError("moved", f"origin/{head} cambió mientras lo leía: vuelve a correrlo")
    local = _git(wt, "rev-parse", "-q", "--verify", f"refs/heads/{head}").stdout.strip()
    if local and local != tip:
        ahead = _git(wt, "rev-list", "--count", f"origin/{head}..{head}").stdout.strip()
        if ahead not in ("", "0"):
            raise SessionError("unpushed", f"{repo}: la rama {head} tiene {ahead} commit(s) sin subir: súbelos (`ide push`) antes")

    # el punto de corte: donde la PR sale de su base vieja (si la base se reescribió a mano, el del reflog)
    fork = _git(wt, "merge-base", "--fork-point", f"origin/{old}", tip).stdout.strip() \
        or _git(wt, "merge-base", f"origin/{old}", tip).stdout.strip()
    if not fork:
        raise SessionError("no_fork", f"no encuentro dónde sale {head} de {old}")
    mine = _git(wt, "rev-list", "--count", f"{fork}..{tip}").stdout.strip()
    out.write(f"{repo}#{number}: {head} sale de {old} con {mine} commit(s) propios; los paso a {onto}\n")

    # 1. archivos que la PR cambia o borra y que la base nueva no tiene (vienen de la base vieja)
    missing = []
    for line in _git(wt, "diff", "--name-status", "--no-renames", fork, tip).stdout.splitlines():
        st, _, path = line.partition("\t")
        if st[:1] in ("M", "D") and _git(wt, "cat-file", "-e", f"origin/{onto}:{path}").returncode != 0:
            missing.append(path)
    if missing:
        out.write(f"FRENO: la PR toca archivos que no existen en {onto} (vienen de {old}):\n"
                  + "".join(f"  - {p}\n" for p in missing)
                  + f"Pasa esos cambios a {old} (o sácalos de la PR) y vuelve a correr `ide pr move`. No moví nada.\n")
        return 1

    orig = _git(wt, "branch", "--show-current").stdout.strip() or _git(wt, "rev-parse", "HEAD").stdout.strip()

    def back() -> None:
        _git(wt, "checkout", "-q", orig)

    # 2. re-aplicar los commits propios sobre la base nueva (detached: la rama se mueve recién al final)
    co = _git(wt, "checkout", "-q", "--detach", tip)
    if co.returncode != 0:
        raise SessionError("checkout_failed", f"{repo}: no pude pararme en {head}: {co.stderr.strip()[-200:]}")
    rb = _git(wt, "rebase", "--onto", f"origin/{onto}", fork)
    if rb.returncode != 0:
        files = _git(wt, "diff", "--name-only", "--diff-filter=U").stdout.split()
        _git(wt, "rebase", "--abort")
        back()
        out.write(f"FRENO: los commits de la PR chocan con {onto} en:\n" + "".join(f"  - {f}\n" for f in files or ["(ver git)"])
                  + "No moví nada (el worktree quedó como estaba). Resuélvelo a mano o pásale esos cambios a la base.\n")
        return 1

    # 3. migraciones contra la base nueva (no contra la base que GitHub todavía tiene en la PR)
    from ide_server import migrations
    try:
        plan = migrations.plan(wt, f"origin/{onto}", "HEAD")
    except RuntimeError as exc:
        _git(wt, "reset", "-q", "--hard", tip); back()
        raise SessionError("migrations", f"no pude revisar las migraciones: {exc}. No moví nada.")
    if not plan["ok"]:
        out.write(f"las migraciones chocan con {onto}:\n{migrations.describe(plan)}\n")
        try:
            touched = migrations.renumber(wt, plan)
        except RuntimeError as exc:
            back()
            out.write(f"FRENO: no pude renumerarlas solo ({exc}). No moví nada.\n")
            return 1
        out.write(f"renumeradas: {', '.join(touched)} (commit aparte)\n")

    # 4. subir, mover la rama local, cambiar la base de la PR y volver a donde estaba
    new = _git(wt, "rev-parse", "HEAD").stdout.strip()
    push = _git(wt, "push", f"--force-with-lease=refs/heads/{head}:{tip}", "origin", f"HEAD:refs/heads/{head}")
    if push.returncode != 0:
        back()
        out.write(f"FRENO: el push falló (¿alguien subió algo a {head}?): {push.stderr.strip()[-300:]}\nNo cambié la base.\n")
        return 1
    if orig == head:
        _git(wt, "checkout", "-q", "-B", head, new)
    else:
        if local:
            br = _git(wt, "branch", "-f", head, new)
            if br.returncode != 0:
                out.write(f"aviso: no pude mover tu rama local {head} ({br.stderr.strip()[-150:]}); origin ya tiene la nueva\n")
        back()
    ed = _gh(wt, "pr", "edit", url, "--base", onto)
    if ed.returncode != 0:
        out.write(f"la rama ya está sobre {onto} y subida, pero no pude cambiar la base de la PR: "
                  f"{ed.stderr.strip()[-200:]}\nCámbiala con `gh pr edit {url} --base {onto}`.\n")
        return 1
    out.write(f"{repo}#{number}: movida de {old} a {onto} ({new[:8]}). La descripción no la toqué: si habla de la base "
              f"vieja o de dependencias, actualízala.\n")
    kids = _gh(wt, "pr", "list", "--base", head, "--state", "open", "--json", "number", "--jq", ".[].number").stdout.split()
    if kids:
        out.write(f"aviso: {', '.join('#' + k for k in kids)} va(n) apilada(s) sobre {head} con la versión vieja: "
                  f"re-apílalas con `ide update {repo}`\n")
    return 0
