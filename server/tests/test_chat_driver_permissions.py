import asyncio
import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from ide_server.chat.driver import ClaudeDriver
from ide_server.chat.events import PermissionRequest

def _driver(on_event, on_permission):
    return ClaudeDriver(cwd="/x", system_prompt="s", permission_mode="default",
                        allowed_tools=None, on_event=on_event, on_permission=on_permission,
                        client_factory=lambda options: _Fake(options))

class _Fake:
    def __init__(self, options): self.options = options

@pytest.mark.asyncio
async def test_permission_allow_emits_request_and_returns_allow():
    events = []
    async def on_perm(req_id): return True
    d = _driver(events.append, on_perm)
    cb = d._make_permission_callback()
    result = await cb("Write", {"file_path": "a.py"}, None)
    assert isinstance(result, PermissionResultAllow)
    assert any(isinstance(e, PermissionRequest) and e.tool == "Write" and e.detail == "a.py"
               for e in events)

@pytest.mark.asyncio
async def test_permission_deny_returns_deny():
    async def on_perm(req_id): return False
    d = _driver(lambda e: None, on_perm)
    cb = d._make_permission_callback()
    result = await cb("Bash", {"command": "rm -rf /"}, None)
    assert isinstance(result, PermissionResultDeny)
