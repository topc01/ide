# server/ide_server/backport.py
"""`ide backport <repo>`: el backport de un hotfix en el mismo desarrollo. El hotfix va en tu worktree del repo
(rama sobre main); el backport, en un worktree extra de tu carpeta de worktrees (`<repo>-develop`, el IDE lo
reconoce como tuyo), con una rama `<tu rama>-develop` desde origin/develop y los commits del hotfix copiados con
`git cherry-pick -x`. Después la sube (`ide push`). La PR la abres tú (`gh pr create --draft --base develop`)."""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import TextIO

from ide_server.push import push
from ide_server.repos_fs import require_session
from ide_server.sessions_fs import SessionError, repo_links


def _git(wt: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, timeout=timeout)


def backport(root: Path, sid: str, repo: str, *, onto: str = "develop", source: str = "main", out: TextIO) -> int:
    links = {p.name: p for p in repo_links(require_session(root, sid))}
    if repo not in links:
        raise SessionError("unknown_repo", f"la sesión {sid} no tiene {repo} (tiene: {', '.join(links) or 'ninguno'})")
    wt = links[repo].resolve()
    branch = _git(wt, "branch", "--show-current").stdout.strip()
    if not branch:
        raise SessionError("detached", f"{repo}: el worktree no está en una rama (detached)")
    for b in (onto, source):
        r = _git(wt, "fetch", "origin", b)
        if r.returncode != 0:
            raise SessionError("fetch_failed", f"no pude traer origin/{b}: {r.stderr.strip()[-200:]}")
    commits = _git(wt, "rev-list", "--reverse", "--no-merges", f"origin/{source}..HEAD").stdout.split()
    if not commits:
        raise SessionError("nothing", f"{repo}: tu rama {branch} no tiene commits sobre origin/{source} (¿el hotfix va "
                                      f"sobre otra base? usa --from <rama>)")
    target = wt.parent / f"{repo}-{onto}"
    new = f"{branch}-{onto}"
    if target.exists():
        raise SessionError("exists", f"ya existe {target}: el backport está ahí (rama "
                                     f"{_git(target, 'branch', '--show-current').stdout.strip() or '?'}); súbelo con "
                                     f"`ide push {repo} --branch {new}`")
    if _git(wt, "rev-parse", "--verify", "--quiet", f"refs/heads/{new}").returncode == 0:
        raise SessionError("exists", f"ya existe la rama local {new}")
    r = _git(wt, "worktree", "add", "--no-track", "-b", new, str(target), f"origin/{onto}")
    if r.returncode != 0:
        raise SessionError("worktree_failed", r.stderr.strip()[-300:])
    out.write(f"{repo}: worktree {target} en {new} (desde origin/{onto})\n")
    r = _git(target, "cherry-pick", "-x", *commits)
    if r.returncode != 0:
        out.write(f"el cherry-pick chocó ({len(commits)} commits):\n{(r.stderr or r.stdout).strip()[-600:]}\n"
                  f"resuélvelo en {target} (`git -C {target} status`), `git -C {target} cherry-pick --continue`, y "
                  f"después `ide push {repo} --branch {new}`\n")
        return 1
    out.write(f"{len(commits)} commits copiados (cherry-pick -x)\n")
    code = push(root, sid, repo, branches=[new], out=out)
    if code == 0:
        out.write(f"siguiente: abre la PR (`gh pr create --draft --base {onto} --head {new}`, en el body «backport de "
                  f"#<n del hotfix>») y declara que van juntas: `ide dep add <hotfix> <backport>` e "
                  f"`ide dep add <backport> <hotfix>`\n")
    return code
