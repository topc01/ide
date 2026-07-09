from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.workspace import discover_repos
from ide_server.worktrees import list_branches
from ide_server.sessions_store import load_sessions
from ide_server.launcher import NullLauncher, SessionLauncher


def register(registry: Registry, root: Path, launcher: SessionLauncher | None = None) -> None:
    launcher = launcher or NullLauncher()

    def _repo_path(repo_id: str) -> Path:
        for repo in discover_repos(root):
            if repo["id"] == repo_id:
                return root / repo["id"]
        raise KeyError(repo_id)

    async def tree(_payload: dict) -> dict:
        return {"sessions": load_sessions(root), "repos": discover_repos(root)}

    async def branches(payload: dict) -> dict:
        repo = _repo_path(payload["repoId"])
        return {"branches": list_branches(repo)}

    registry.register("sessions.tree", tree)
    registry.register("sessions.branches", branches)

    # guardado para tareas siguientes (create/rename/close comparten estado)
    register._root = root          # type: ignore[attr-defined]
    register._launcher = launcher  # type: ignore[attr-defined]
