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
    if out.returncode != 0:
        return "unknown"
    return out.stdout.strip() or "HEAD"


def discover_repos(root: Path) -> list[dict]:
    repos: list[dict] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if (child / ".git").exists():
            repos.append({"id": child.name, "name": child.name, "branch": _current_branch(child)})
    return repos


def _folder_session(root: Path, payload: dict) -> Path | None:
    sid = payload.get("sessionId")
    if not sid or Path(sid).name != sid or sid in (".", ".."):
        return None
    path = root / ".ide" / "sessions" / sid
    return path if (path / ".session.toml").is_file() else None


def _linked_repos(folder: Path) -> list[str]:
    from ide_server.sessions_fs import repo_links   # sin TICKET.md/REVIEW.md (symlinks a SESSION.md)
    return [p.name for p in repo_links(folder)]


def resolve_cwd(root: Path, payload: dict) -> Path:
    folder = _folder_session(root, payload)
    if folder is not None:
        repo = payload.get("repoId")
        if not repo:
            return folder
        if repo not in _linked_repos(folder) or not (folder / repo).exists():
            raise KeyError(repo)
        return (folder / repo).resolve()
    from ide_server.sessions_store import load_sessions, find_node
    if payload.get("sessionId"):
        node = find_node(load_sessions(root), payload["sessionId"])
        if node is None:
            raise KeyError(payload["sessionId"])
        return Path(node.get("worktreePath") or root)
    if payload.get("repoId"):
        for repo in discover_repos(root):
            if repo["id"] == payload["repoId"]:
                return root / repo["id"]
        raise KeyError(payload["repoId"])
    return root


def resolve_repo(root: Path, payload: dict) -> Path:
    folder = _folder_session(root, payload)
    if folder is not None:
        repos = _linked_repos(folder)
        repo = payload.get("repoId")
        if repo is not None and repo not in repos:
            raise KeyError(repo)
        if repo is None:
            if len(repos) != 1:
                raise KeyError("la sesión tiene 0 o varios repos: indica repoId")
            repo = repos[0]
        return root / repo
    from ide_server.sessions_store import load_sessions, find_node
    if payload.get("sessionId"):
        node = find_node(load_sessions(root), payload["sessionId"])
        if node is None or not node.get("repoId"):
            raise KeyError(payload["sessionId"])
        return root / node["repoId"]
    if payload.get("repoId"):
        return root / payload["repoId"]
    raise KeyError("sin contexto de repo")
