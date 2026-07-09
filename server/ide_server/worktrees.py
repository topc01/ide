from __future__ import annotations
import subprocess
from pathlib import Path


class WorktreeError(Exception):
    """Error de operación de git worktree (nunca silencioso: viaja como envelope)."""


class BranchOccupied(WorktreeError):
    def __init__(self, branch: str) -> None:
        super().__init__(f"branch ocupada: {branch}")
        self.branch = branch


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
    )


def _occupied_branches(repo: Path) -> set[str]:
    """Branches checkouteadas en algún worktree (incluye el principal)."""
    out = _git(repo, "worktree", "list", "--porcelain")
    if out.returncode != 0:
        raise WorktreeError(out.stderr.strip() or "git worktree list falló")
    occupied: set[str] = set()
    for line in out.stdout.splitlines():
        if line.startswith("branch "):
            ref = line[len("branch "):].strip()       # p.ej. refs/heads/feature/x
            occupied.add(ref.removeprefix("refs/heads/"))
    return occupied


def list_branches(repo: Path) -> list[dict]:
    out = _git(repo, "branch", "--format=%(refname:short)")
    if out.returncode != 0:
        raise WorktreeError(out.stderr.strip() or "git branch falló")
    occupied = _occupied_branches(repo)
    names = [n.strip() for n in out.stdout.splitlines() if n.strip()]
    return [{"name": n, "occupied": n in occupied} for n in names]


def branch_occupied(repo: Path, branch: str) -> bool:
    return branch in _occupied_branches(repo)


def _branch_exists(repo: Path, branch: str) -> bool:
    out = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    return out.returncode == 0


def add_worktree(repo: Path, path: Path, branch: str, access: str,
                 base: str | None = None) -> None:
    if access not in ("rw", "ro"):
        raise WorktreeError(f"access inválido: {access}")
    exists = _branch_exists(repo, branch)

    if access == "rw":
        if exists and branch_occupied(repo, branch):
            raise BranchOccupied(branch)
        if exists:
            args = ["worktree", "add", str(path), branch]
        else:
            args = ["worktree", "add", "-b", branch, str(path), base or "HEAD"]
    else:  # ro → detached, siempre permitido
        target = branch if exists else (base or "HEAD")
        args = ["worktree", "add", "--detach", str(path), target]

    out = _git(repo, *args)
    if out.returncode != 0:
        raise WorktreeError(out.stderr.strip() or "git worktree add falló")


def remove_worktree(repo: Path, path: Path, force: bool = False) -> None:
    args = ["worktree", "remove", str(path)]
    if force:
        args.append("--force")
    out = _git(repo, *args)
    if out.returncode != 0:
        raise WorktreeError(out.stderr.strip() or "git worktree remove falló")


def has_uncommitted_changes(worktree: Path) -> bool:
    out = _git(worktree, "status", "--porcelain")
    if out.returncode != 0:
        raise WorktreeError(out.stderr.strip() or "git status falló")
    return bool(out.stdout.strip())
