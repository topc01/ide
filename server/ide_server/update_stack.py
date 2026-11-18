# server/ide_server/update_stack.py
"""`ide update` sobre un stack: el worktree está en la rama de arriba, pero lo que necesita ponerse al día es una de
abajo (en conflicto con develop, atrás sin aprobación, o su madre se mergeó). Se rebasea esa rama según su plan
(`update_branch.plan`) y cada una de las de encima sobre la nueva versión de su madre (`--onto <madre nueva>
<madre vieja>`: solo sus propios commits), de abajo hacia arriba, en el mismo worktree y sin checkout de las otras
ramas (en detached; la de arriba, la del worktree, vuelve a quedar en su rama). Cada una se sube con
`--force-with-lease`. Si un rebase choca, queda a medias en el worktree y el avance se guarda en
`<sesión>/.update-<repo>.json`: la sesión resuelve, `git rebase --continue`, y vuelve a correr `ide update <repo>`,
que sigue desde ahí. Un worktree aparte que tenga checkouteada una de esas ramas (limpio y al día) queda en la
versión nueva."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import TextIO

from ide_server.push import PROTECTED, _default_branch


def _git(wt: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, timeout=timeout)


def _gh(wt: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=wt, capture_output=True, text=True, timeout=120)


def chain(wt: Path, branch: str) -> list[str]:
    """Las ramas del stack bajo `branch` (incluida), de abajo hacia arriba, siguiendo la base de cada PR abierta
    hasta una rama principal (o una sin PR abierta: una madre mergeada la resuelve el plan de su hija)."""
    out, b, seen = [branch], branch, {branch}
    while True:
        r = _gh(wt, "pr", "view", b, "--json", "state,baseRefName")
        if r.returncode != 0:
            break
        pr = json.loads(r.stdout)
        base = pr.get("baseRefName")
        if pr.get("state") != "OPEN" or not base or base in PROTECTED or base == _default_branch(wt) or base in seen:
            break
        mother = _gh(wt, "pr", "view", base, "--json", "state")
        if mother.returncode != 0 or json.loads(mother.stdout).get("state") != "OPEN":
            break
        out.insert(0, base)
        seen.add(base)
        b = base
    return out


def tree(wt: Path, root: str, top: str) -> tuple[list[str], dict[str, str]]:
    """`root` y todas las ramas apiladas encima (PRs abiertas cuya base es una de ellas, también hermanas en otros
    worktrees), madres antes que hijas, y la madre de cada una. `top` (la del worktree) siempre va."""
    order, parent, queue = [root], {}, [root]
    while queue:
        b = queue.pop(0)
        r = _gh(wt, "pr", "list", "--base", b, "--state", "open", "--author", "@me", "--json", "headRefName")
        kids = [x["headRefName"] for x in json.loads(r.stdout or "[]")] if r.returncode == 0 else []
        for h in kids:
            if h not in parent and h != root:
                parent[h] = b
                order.append(h)
                queue.append(h)
    if top not in order:
        raise RuntimeError(f"{top} no quedó en el stack de {root}")
    return order, parent


def _elsewhere(wt: Path, branches: list[str]) -> dict[str, Path]:
    """Otros worktrees (del mismo repo) donde está checkouteada alguna de esas ramas."""
    out, path, me = {}, None, wt.resolve()
    for line in _git(wt, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:]).resolve()
        elif line.startswith("branch refs/heads/") and path and path != me and line[18:] in branches:
            out[line[18:]] = path
    return out


def _state_file(session_dir: Path, repo: str) -> Path:
    return session_dir / f".update-{repo}.json"


def start(wt: Path, session_dir: Path, repo: str, line: list[str], k: int, first: dict, out: TextIO) -> int:
    """Arranca el update del stack desde `line[k]` (que tiene el plan `first`): ella y todo lo apilado encima
    (la línea hasta la del worktree y las hermanas)."""
    top = line[-1]
    try:
        order, parent = tree(wt, line[k], top)
    except RuntimeError:
        order, parent = line[k:], {b: line[i + k] for i, b in enumerate(line[k + 1:])}
    branches = order
    if _git(wt, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        out.write(f"{repo}: tienes cambios sin commitear: commitea o guárdalos antes\n")
        return 1
    others = _elsewhere(wt, branches)
    for b in branches:
        local = _git(wt, "rev-parse", f"refs/heads/{b}").stdout.strip()
        remote = _git(wt, "rev-parse", f"refs/remotes/origin/{b}").stdout.strip()
        if local and remote and local != remote and _git(wt, "merge-base", "--is-ancestor", local, remote).returncode != 0:
            out.write(f"{repo}: {b} tiene commits locales sin subir (o divergió de origin): súbelos antes (`ide push "
                      f"{repo} --branch {b}`)\n")
            return 1
        if b in others and _git(others[b], "status", "--porcelain", "--untracked-files=no").stdout.strip():
            out.write(f"{repo}: {b} está checkouteada en {others[b]} con cambios sin commitear: commitéalos o "
                      f"guárdalos antes\n")
            return 1
    # de dónde parte cada una: la local si va adelante de origin (commits sin subir, p.ej. en la del worktree), si
    # no origin; el push forzado se protege contra lo que hay en origin
    leases = {b: _git(wt, "rev-parse", f"refs/remotes/origin/{b}").stdout.strip() for b in branches}
    olds = {}
    for b in branches:
        local = _git(wt, "rev-parse", f"refs/heads/{b}").stdout.strip()
        ahead = local and (not leases[b] or _git(wt, "merge-base", "--is-ancestor", leases[b], local).returncode == 0)
        olds[b] = local if ahead else leases[b]
    st = {"top": top, "branches": branches, "parent": parent, "olds": olds, "leases": leases, "news": {},
          "first": first, "i": 0}
    return _run(wt, session_dir, repo, st, out)


def resume(wt: Path, session_dir: Path, repo: str, out: TextIO) -> int | None:
    """Sigue un update de stack a medias (None si no hay uno)."""
    f = _state_file(session_dir, repo)
    if not f.exists():
        return None
    st = json.loads(f.read_text(encoding="utf-8"))
    gitdir = Path(_git(wt, "rev-parse", "--absolute-git-dir").stdout.strip())
    if (gitdir / "rebase-merge").exists() or (gitdir / "rebase-apply").exists():
        b = st["branches"][st["i"]]
        out.write(f"{repo}: el rebase de {b} sigue a medias: resuelve los conflictos, `git -C {wt} add …`, "
                  f"`git -C {wt} rebase --continue` y vuelve a correr `ide update {repo}`. (Para abandonar: "
                  f"`git -C {wt} rebase --abort`, `git -C {wt} checkout {st['top']}` y borra {f}.)\n")
        return 1
    # el rebase de branches[i] terminó (la sesión hizo --continue): subirlo y seguir con las de encima
    if not _finish(wt, repo, st, out):
        f.unlink(missing_ok=True)
        return 1
    st["i"] += 1
    return _run(wt, session_dir, repo, st, out)


def _finish(wt: Path, repo: str, st: dict, out: TextIO) -> bool:
    """El HEAD (detached) es la versión nueva de branches[i]: subirla y dejarla en los worktrees que la tienen."""
    b = st["branches"][st["i"]]
    new = _git(wt, "rev-parse", "HEAD").stdout.strip()
    old, lease = st["olds"][b], st["leases"][b]
    if new != lease:
        push = _git(wt, "push", f"--force-with-lease={b}:{lease}", "origin", f"HEAD:refs/heads/{b}")
        if push.returncode != 0:
            out.write(f"{repo}: {b} rebaseada, pero el push falló: {push.stderr.strip()[-300:]}\n")
            return False
    st["news"][b] = new
    if b != st["top"]:
        other = _elsewhere(wt, [b]).get(b)
        if other is not None:
            _git(other, "reset", "--hard", new)
        elif _git(wt, "rev-parse", "--verify", "--quiet", f"refs/heads/{b}").returncode == 0:
            _git(wt, "branch", "-f", b, new)
    out.write(f"{repo}: {b} " + ("rebaseada y subida" if new != old else "ya estaba al día") + "\n")
    return True


def _run(wt: Path, session_dir: Path, repo: str, st: dict, out: TextIO) -> int:
    f = _state_file(session_dir, repo)
    while st["i"] < len(st["branches"]):
        b = st["branches"][st["i"]]
        if st["i"] == 0:
            p = st["first"]
            onto, upstream = p["onto"], p.get("upstream")
            out.write(f"{repo}: {b}: {p['reason']}: la rebaseo sobre {onto}\n")
        else:
            mother = st["parent"][b]
            onto, upstream = st["news"][mother], st["olds"][mother]
            if onto == upstream:                  # la madre no cambió: esta tampoco
                st["news"][b] = st["olds"][b]
                st["i"] += 1
                continue
            out.write(f"{repo}: {b}: la re-apilo sobre la nueva {mother}\n")
        _git(wt, "checkout", "--quiet", "--detach", st["olds"][b])
        r = _git(wt, "rebase", *(["--onto", onto, upstream] if upstream else [onto]))
        if r.returncode != 0:
            f.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
            out.write(f"{repo}: el rebase de {b} chocó y quedó a medias en {wt}.\n"
                      f"  Resuelve los archivos en conflicto, `git -C {wt} add …` y `git -C {wt} rebase --continue`;"
                      f" después vuelve a correr `ide update {repo}`: sube {b} y sigue con las de encima.\n")
            return 1
        if not _finish(wt, repo, st, out):
            f.unlink(missing_ok=True)
            _git(wt, "checkout", "--quiet", st["top"])
            return 1
        st["i"] += 1
    top = st["top"]
    _git(wt, "checkout", "--quiet", "-B", top, st["news"].get(top) or st["olds"][top])
    _git(wt, "branch", "--quiet", "--set-upstream-to", f"origin/{top}", top)
    f.unlink(missing_ok=True)
    first = st["first"]
    if first.get("new_base") and first["new_base"] != first["pr"]["baseRefName"]:
        _gh(wt, "pr", "edit", str(first["pr"]["number"]), "--base", first["new_base"])
        out.write(f"{repo}: la base de #{first['pr']['number']} ahora es {first['new_base']}\n")
    out.write(f"{repo}: stack al día; el worktree sigue en {top}\n")
    return 0
