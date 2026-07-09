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
            ref = line[len("branch "):].strip()       # p.ej. refs/heads/main
            occupied.add(ref.rsplit("/", 1)[-1])
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
