import asyncio
import pytest
from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage
from ide_server.chat.driver import ClaudeDriver
from ide_server.chat.events import TextDelta, Done

class FakeClient:
    def __init__(self, options=None):
        self.options = options
        self.sent: list[str] = []
        self.interrupted = False
        self._queue: asyncio.Queue = asyncio.Queue()
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def query(self, prompt): self.sent.append(prompt)
    async def interrupt(self): self.interrupted = True
    def feed(self, *messages):
        for m in messages: self._queue.put_nowait(m)
        self._queue.put_nowait(None)  # centinela fin de turno
    async def receive_response(self):
        while True:
            m = await self._queue.get()
            if m is None: return
            yield m

@pytest.mark.asyncio
async def test_start_and_send_stream_events():
    events = []
    fake = FakeClient()
    d = ClaudeDriver(cwd="/x", system_prompt="sys", permission_mode="default",
                     allowed_tools=None, on_event=events.append, on_permission=None,
                     client_factory=lambda options: fake)
    await d.start()
    fake.feed(AssistantMessage(content=[TextBlock(text="hola")], model="claude-test"),
              ResultMessage(session_id="s9", total_cost_usd=0.0,
                            usage={"input_tokens": 1, "output_tokens": 2}, num_turns=1,
                            subtype="success", duration_ms=1, duration_api_ms=1,
                            is_error=False, result="ok"))
    await d.send("hi")
    assert fake.sent == ["hi"]
    assert TextDelta(text="hola") in events
    assert any(isinstance(e, Done) and e.session_id == "s9" for e in events)
    assert d.session_id == "s9"

@pytest.mark.asyncio
async def test_interrupt_delegates_to_client():
    fake = FakeClient()
    d = ClaudeDriver(cwd="/x", system_prompt="s", permission_mode="default",
                     allowed_tools=None, on_event=lambda e: None, on_permission=None,
                     client_factory=lambda options: fake)
    await d.start()
    await d.interrupt()
    assert fake.interrupted is True
