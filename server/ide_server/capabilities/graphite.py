from __future__ import annotations
from pathlib import Path
from ide_server.plugins import Registry
from ide_server import graphite
from ide_server.workspace import resolve_repo, _current_branch
from ide_server.sessions_store import load_sessions, find_node


def register(registry: Registry, root: Path) -> None:
    def _current(repo: Path, payload: dict) -> str:
        if payload.get("sessionId"):
            node = find_node(load_sessions(root), payload["sessionId"])
            if node and node.get("branch"):
                return node["branch"]
        return _current_branch(repo)

    async def stack_(payload: dict) -> dict:
        repo = resolve_repo(root, payload)
        current = _current(repo, payload)
        rows = graphite.read_stack(repo)
        return {"stack": graphite.build_stack(rows, current), "current": current}

    async def branch_(payload: dict) -> dict:
        repo = resolve_repo(root, payload)
        rows = {r["name"]: r for r in graphite.read_stack(repo)}
        row = rows.get(payload["branch"])
        if row is None:
            return {"commits": []}
        commits = graphite.branch_commits(repo, row["revision"], row["parentRevision"])
        for c in commits:
            c["files"] = graphite.commit_files(repo, c["hash"])
        return {"commits": commits}

    async def restack_(payload: dict) -> dict:
        repo = resolve_repo(root, payload)
        graphite.restack(repo, payload["branch"])
        current = _current(repo, payload)
        rows = graphite.read_stack(repo)
        return {"stack": graphite.build_stack(rows, current), "current": current}

    registry.register("graphite.stack", stack_)
    registry.register("graphite.branch", branch_)
    registry.register("graphite.restack", restack_)
