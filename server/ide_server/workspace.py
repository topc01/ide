from __future__ import annotations
import subprocess
from pathlib import Path


def find_workspace_root(start: Path) -> Path | None:
    start = start.resolve()
    for candidate in [start, *start.parents]:
        if (candidate / ".ide").is_dir():
            return candidate
    return None


def _current_branch(repo: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return out.stdout.strip() or "HEAD"


def discover_repos(root: Path) -> list[dict]:
    repos: list[dict] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if (child / ".git").exists():
            repos.append({"id": child.name, "name": child.name, "branch": _current_branch(child)})
    return repos
