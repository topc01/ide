from ide_server.chat.events import (
    TextDelta, ToolUse, Edit, Usage, Done, PermissionRequest, ChatError, to_payload,
)

def test_text_delta_payload():
    assert to_payload(TextDelta(text="hola")) == {"kind": "text_delta", "text": "hola"}

def test_tool_use_payload():
    assert to_payload(ToolUse(id="t1", name="Bash", detail="ls -la")) == {
        "kind": "tool_use", "id": "t1", "name": "Bash", "detail": "ls -la"}

def test_edit_payload():
    assert to_payload(Edit(id="e1", path="a.py", added=3, removed=1)) == {
        "kind": "edit", "id": "e1", "path": "a.py", "added": 3, "removed": 1}

def test_usage_payload():
    assert to_payload(Usage(input_tokens=10, output_tokens=20, total_tokens=30)) == {
        "kind": "usage", "inputTokens": 10, "outputTokens": 20, "totalTokens": 30}

def test_done_and_permission_and_error():
    assert to_payload(Done(session_id="s1", is_error=False)) == {
        "kind": "done", "sessionId": "s1", "isError": False}
    assert to_payload(PermissionRequest(id="p1", tool="Write", detail="a.py")) == {
        "kind": "permission_request", "id": "p1", "tool": "Write", "detail": "a.py"}
    assert to_payload(ChatError(code="not_logged_in", message="corré claude login")) == {
        "kind": "error", "code": "not_logged_in", "message": "corré claude login"}
