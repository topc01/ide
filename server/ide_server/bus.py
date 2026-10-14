from __future__ import annotations
import json
from ide_server.plugins import Registry
from ide_server.worktrees import WorktreeError, BranchOccupied
from ide_server.capabilities.sessions import UncommittedChanges
from ide_server.capabilities.search import SearchError
from ide_server.sessions_fs import SessionError


async def handle_message(raw: str, registry: Registry) -> str:
    try:
        msg = json.loads(raw)
        mid, channel = msg.get("id"), msg.get("channel")
        payload = msg.get("payload") or {}
    except (json.JSONDecodeError, AttributeError) as exc:
        return json.dumps({"type": "error", "id": None, "channel": None,
                           "payload": {"code": "invalid_message", "message": str(exc)}})
    try:
        result = await registry.dispatch(channel, payload)
        return json.dumps({"type": "res", "id": mid, "channel": channel, "payload": result})
    except KeyError:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": "unknown_channel", "message": f"no handler: {channel}"}})
    except BranchOccupied as exc:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": "branch_occupied", "message": str(exc),
                                       "branch": exc.branch, "suggestion": "new_branch"}})
    except UncommittedChanges as exc:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": "uncommitted_changes", "message": str(exc),
                                       "sessionId": exc.session_id}})
    except WorktreeError as exc:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": "worktree_error", "message": str(exc)}})
    except SearchError as exc:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": exc.code, "message": str(exc)}})
    except SessionError as exc:
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": exc.code, "message": str(exc)}})
    except Exception as exc:  # noqa: BLE001 — todo error viaja como envelope, nunca silencioso
        return json.dumps({"type": "error", "id": mid, "channel": channel,
                           "payload": {"code": "handler_error", "message": str(exc)}})


class ConnectionManager:
    def __init__(self) -> None:
        self._active: set = set()

    async def connect(self, ws) -> None:
        await ws.accept()
        self._active.add(ws)

    def disconnect(self, ws) -> None:
        self._active.discard(ws)

    async def broadcast(self, channel: str, payload: dict) -> None:
        msg = json.dumps({"type": "event", "id": None, "channel": channel, "payload": payload})
        for ws in list(self._active):
            await ws.send_text(msg)
