# server/ide_server/push.py
"""`ide push`: sube a `origin` las ramas de los worktrees de una sesión, sin que la sesión tenga que
hacer `cd` ni armar el `git push` (el clasificador de permisos de claude los frena y terminan pidiéndole
al usuario que los corra). Solo ramas de la sesión, nunca la principal del repo; con `--force` va
`--force-with-lease` (nunca `--force` a secas)."""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import TextIO
from ide_server.repos_fs import require_session
from ide_server.sessions_fs import SessionError, repo_links

PROTECTED = {"main", "master", "develop", "staging", "production"}


def _git(wt: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, timeout=300)


def _default_branch(wt: Path) -> str | None:
    r = _git(wt, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return r.stdout.strip().removeprefix("origin/") or None if r.returncode == 0 else None


def push(root: Path, sid: str, repo: str | None, *, branches: list[str] | None = None, force: bool = False,
         out: TextIO) -> int:
    links = {p.name: p for p in repo_links(require_session(root, sid))}
    if repo is not None and repo not in links:
        raise SessionError("unknown_repo", f"la sesión {sid} no tiene {repo} (tiene: {', '.join(links) or 'ninguno'})")
    if branches and repo is None and len(links) != 1:
        raise SessionError("ambiguous_repo", f"--branch necesita el repo: {', '.join(links)}")
    if not links:
        out.write(f"la sesión {sid} no tiene repos\n")
        return 1
    failed = 0
    for name in [repo] if repo else sorted(links):
        wt = links[name].resolve()
        todo = branches or [_git(wt, "branch", "--show-current").stdout.strip()]
        if not todo[0]:
            out.write(f"{name}: sin rama (detached), no subo nada\n"); failed += 1; continue
        protected = PROTECTED | ({d} if (d := _default_branch(wt)) else set())
        for b in todo:
            if b in protected:
                out.write(f"{name}: {b} es una rama principal, no la subo\n"); failed += 1; continue
            if _git(wt, "rev-parse", "--verify", "--quiet", f"refs/heads/{b}").returncode != 0:
                out.write(f"{name}: no existe la rama local {b}\n"); failed += 1; continue
            r = _git(wt, "push", *(["--force-with-lease"] if force else []), "-u", "origin", f"{b}:{b}")
            msg = (r.stderr.strip() or r.stdout.strip()).splitlines()
            out.write(f"{name}: {b} {'subida' if r.returncode == 0 else 'FALLÓ'}"
                      + (f" ({msg[-1]})" if msg else "") + "\n")
            if r.returncode != 0:
                failed += 1
                if not force and ("non-fast-forward" in r.stderr or "rejected" in r.stderr):
                    out.write("  (la rama remota tiene otra historia: si rebaseaste a propósito, usa --force)\n")
    return 1 if failed else 0
