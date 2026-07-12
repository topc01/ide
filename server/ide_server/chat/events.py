from __future__ import annotations
from dataclasses import dataclass

@dataclass
class TextDelta:
    text: str

@dataclass
class ToolUse:
    id: str
    name: str
    detail: str

@dataclass
class Edit:
    id: str
    path: str
    added: int
    removed: int

@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int

@dataclass
class Done:
    session_id: str
    is_error: bool

@dataclass
class PermissionRequest:
    id: str
    tool: str
    detail: str

@dataclass
class ChatError:
    code: str
    message: str

def to_payload(event: object) -> dict:
    if isinstance(event, TextDelta):
        return {"kind": "text_delta", "text": event.text}
    if isinstance(event, ToolUse):
        return {"kind": "tool_use", "id": event.id, "name": event.name, "detail": event.detail}
    if isinstance(event, Edit):
        return {"kind": "edit", "id": event.id, "path": event.path,
                "added": event.added, "removed": event.removed}
    if isinstance(event, Usage):
        return {"kind": "usage", "inputTokens": event.input_tokens,
                "outputTokens": event.output_tokens, "totalTokens": event.total_tokens}
    if isinstance(event, Done):
        return {"kind": "done", "sessionId": event.session_id, "isError": event.is_error}
    if isinstance(event, PermissionRequest):
        return {"kind": "permission_request", "id": event.id, "tool": event.tool, "detail": event.detail}
    if isinstance(event, ChatError):
        return {"kind": "error", "code": event.code, "message": event.message}
    raise TypeError(f"evento de chat desconocido: {type(event)!r}")
