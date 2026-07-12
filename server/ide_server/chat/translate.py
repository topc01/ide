from __future__ import annotations
from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock, ResultMessage
from ide_server.chat.events import TextDelta, ToolUse, Edit, Usage, Done

_EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}

def _lines(s: str | None) -> int:
    return len(s.splitlines()) if s else 0

def _tool_detail(name: str, inp: dict) -> str:
    if name == "Bash":
        return str(inp.get("command", ""))
    for key in ("file_path", "path", "pattern", "url"):
        if key in inp:
            return str(inp[key])
    return ""

def _edit_detail(block: ToolUseBlock) -> Edit:
    inp = block.input
    path = str(inp.get("file_path", ""))
    if block.name == "Write":
        return Edit(id=block.id, path=path, added=_lines(inp.get("content")), removed=0)
    return Edit(id=block.id, path=path,
                added=_lines(inp.get("new_string")), removed=_lines(inp.get("old_string")))

def translate(message: object) -> list:
    out: list = []
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                out.append(TextDelta(text=block.text))
            elif isinstance(block, ToolUseBlock):
                if block.name in _EDIT_TOOLS:
                    out.append(_edit_detail(block))
                else:
                    out.append(ToolUse(id=block.id, name=block.name,
                                       detail=_tool_detail(block.name, block.input)))
        return out
    if isinstance(message, ResultMessage):
        usage = message.usage or {}
        it, ot = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        out.append(Usage(input_tokens=it, output_tokens=ot, total_tokens=it + ot))
        out.append(Done(session_id=message.session_id, is_error=bool(message.is_error)))
        return out
    return out
