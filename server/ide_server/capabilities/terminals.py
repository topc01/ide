from __future__ import annotations
import base64
import os
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.pty_manager import PtyManager
from ide_server.workspace import discover_repos
from ide_server.sessions_store import load_sessions, find_node


def register(registry: Registry, root: Path, manager, pty: PtyManager | None = None) -> None:
    pty = pty or PtyManager()
    terms: dict[str, dict] = {}                 # tid -> {sessionId, cmd, cwd}

    def _repo_path(repo_id: str) -> Path:
        for repo in discover_repos(root):
            if repo["id"] == repo_id:
                return root / repo["id"]
        raise KeyError(repo_id)

    def _cwd(payload: dict) -> Path:
        if payload.get("sessionId"):
            node = find_node(load_sessions(root), payload["sessionId"])
            if node is None:
                raise KeyError(payload["sessionId"])
            return Path(node.get("worktreePath") or root)
        if payload.get("repoId"):
            return _repo_path(payload["repoId"])
        return root

    async def open_(payload: dict) -> dict:
        cwd = _cwd(payload)
        cmd = payload.get("cmd") or [os.environ.get("SHELL", "/bin/zsh")]
        tid = pty.spawn(cwd, cmd)
        terms[tid] = {"sessionId": payload.get("sessionId"), "cmd": cmd, "cwd": str(cwd)}
        return {"id": tid, "cwd": str(cwd)}

    async def list_(payload: dict) -> dict:
        sid = payload.get("sessionId")
        out = [{"id": tid, "cmd": t["cmd"], "alive": pty.is_alive(tid)}
               for tid, t in terms.items() if t["sessionId"] == sid]
        return {"terminals": out}

    async def write_(payload: dict) -> dict:
        pty.write(payload["id"], base64.b64decode(payload["data"]))
        return {"ok": True}

    async def resize_(payload: dict) -> dict:
        pty.resize(payload["id"], int(payload["cols"]), int(payload["rows"]))
        return {"ok": True}

    async def close_(payload: dict) -> dict:
        pty.close(payload["id"])
        terms.pop(payload["id"], None)
        return {"ok": True}

    registry.register("terminal.open", open_)
    registry.register("terminal.list", list_)
    registry.register("terminal.write", write_)
    registry.register("terminal.resize", resize_)
    registry.register("terminal.close", close_)

    # compartido con Tasks 4-5 (write/resize/close + streaming) vía cierre:
    register._pty = pty        # type: ignore[attr-defined]
    register._terms = terms    # type: ignore[attr-defined]
    register._manager = manager  # type: ignore[attr-defined]
