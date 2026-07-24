from __future__ import annotations
import subprocess
import uuid
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.workspace import discover_repos


def _live_branch(wt: Path) -> str | None:
    # rama actual del worktree; None si git falla (worktree ausente / no-git) → se conserva la guardada
    out = subprocess.run(
        ["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    return out.stdout.strip() or "HEAD"


def _annotate_branches(nodes: list[dict], branch_of) -> None:
    for n in nodes:
        wt = n.get("worktreePath")
        if wt:
            live = branch_of(Path(wt))
            if live is not None:
                n["branch"] = live
        _annotate_branches(n.get("children") or [], branch_of)
from ide_server.worktrees import (
    list_branches, branch_occupied, add_worktree, remove_worktree,
    has_uncommitted_changes,
)
from ide_server.sessions_store import (
    load_sessions, save_sessions, slugify, insert_node, rename_node,
    find_node, remove_node,
)
from ide_server.roles import resolve_role
from ide_server.launcher import NullLauncher, SessionLauncher


def register(registry: Registry, root: Path, launcher: SessionLauncher | None = None,
             branch_of=None) -> None:
    launcher = launcher or NullLauncher()
    branch_of = branch_of or _live_branch

    def _repo_path(repo_id: str) -> Path:
        for repo in discover_repos(root):
            if repo["id"] == repo_id:
                return root / repo["id"]
        raise KeyError(repo_id)

    async def tree(_payload: dict) -> dict:
        sessions = load_sessions(root)
        _annotate_branches(sessions, branch_of)
        return {"sessions": sessions, "repos": discover_repos(root)}

    async def branches(payload: dict) -> dict:
        return {"branches": list_branches(_repo_path(payload["repoId"]))}

    async def create(payload: dict) -> dict:
        name = payload["name"]
        slug = slugify(name)
        node: dict = {
            "id": str(uuid.uuid4()), "name": name, "slug": slug,
            "description": payload.get("description"),
            "role": payload.get("role"),
            "status": "idle",
            "repoId": None, "branch": None, "access": None, "worktreePath": None,
            "expanded": True, "terminals": [], "children": [],
        }
        if payload.get("kind") == "work":
            repo = _repo_path(payload["repoId"])
            branch = payload.get("branch") or slug
            access = payload.get("access") or "rw"
            wt = root / ".ide" / "worktrees" / slug
            add_worktree(repo, wt, branch, access=access, base=payload.get("base"))
            node.update(repoId=payload["repoId"], branch=branch, access=access,
                        worktreePath=str(wt))

        tree_data = load_sessions(root)
        insert_node(tree_data, payload.get("parentId"), node)
        save_sessions(root, tree_data)
        launcher.launch(node, resolve_role(root, payload.get("role")))
        return {"session": node}

    async def rename(payload: dict) -> dict:
        tree_data = load_sessions(root)
        ok = rename_node(tree_data, payload["id"], payload["name"])
        if ok:
            save_sessions(root, tree_data)
        return {"renamed": ok}

    async def close(payload: dict) -> dict:
        tree_data = load_sessions(root)
        node = find_node(tree_data, payload["id"])
        if node is None:
            return {"closed": False}
        wt = node.get("worktreePath")
        if wt:
            repo = _repo_path(node["repoId"])
            if node.get("access") == "rw" and not payload.get("force") \
                    and has_uncommitted_changes(Path(wt)):
                raise UncommittedChanges(node["id"])
            remove_worktree(repo, Path(wt), force=bool(payload.get("force")))
        remove_node(tree_data, payload["id"])
        save_sessions(root, tree_data)
        return {"closed": True}

    for channel, handler in {
        "sessions.tree": tree, "sessions.branches": branches,
        "sessions.create": create, "sessions.rename": rename, "sessions.close": close,
    }.items():
        registry.register(channel, handler)


class UncommittedChanges(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"cambios sin commitear en la sesión {session_id}")
        self.session_id = session_id
