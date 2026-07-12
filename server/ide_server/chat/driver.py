from __future__ import annotations
import uuid
from typing import Awaitable, Callable
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
)
from ide_server.chat.translate import translate, _tool_detail
from ide_server.chat.events import Done, PermissionRequest

EventCb = Callable[[object], None]
PermissionCb = Callable[[str, dict], Awaitable[bool]] | None

class ClaudeDriver:
    def __init__(self, *, cwd: str, system_prompt: str, permission_mode: str,
                 allowed_tools: list[str] | None, on_event: EventCb,
                 on_permission: PermissionCb, resume: str | None = None,
                 client_factory=None) -> None:
        self._on_event = on_event
        self._on_permission = on_permission
        self._factory = client_factory or ClaudeSDKClient
        self.session_id: str | None = resume
        opts: dict = {"cwd": cwd, "system_prompt": system_prompt,
                      "permission_mode": permission_mode, "include_partial_messages": False}
        if allowed_tools is not None:
            opts["allowed_tools"] = allowed_tools
        if resume:
            opts["resume"] = resume
        if permission_mode != "bypassPermissions" and on_permission is not None:
            opts["can_use_tool"] = self._make_permission_callback()
        self._client = self._factory(options=ClaudeAgentOptions(**opts))

    def _make_permission_callback(self):
        async def can_use_tool(tool_name: str, input_data: dict, context) -> object:
            req_id = str(uuid.uuid4())
            self._on_event(PermissionRequest(id=req_id, tool=tool_name,
                                             detail=_tool_detail(tool_name, input_data)))
            allowed = True
            if self._on_permission is not None:
                allowed = await self._on_permission(req_id)
            if allowed:
                return PermissionResultAllow(updated_input=input_data)
            return PermissionResultDeny(message="Denegado por el usuario")
        return can_use_tool

    async def start(self) -> None:
        await self._client.__aenter__()

    async def send(self, text: str) -> None:
        await self._client.query(prompt=text)
        async for message in self._client.receive_response():
            for event in translate(message):
                if isinstance(event, Done):
                    self.session_id = event.session_id
                self._on_event(event)

    async def interrupt(self) -> None:
        await self._client.interrupt()

    async def close(self) -> None:
        await self._client.__aexit__(None, None, None)
