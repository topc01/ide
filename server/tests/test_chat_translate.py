from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock, ResultMessage
from ide_server.chat.translate import translate
from ide_server.chat.events import TextDelta, ToolUse, Edit, Usage, Done

def test_text_block_becomes_text_delta():
    msg = AssistantMessage(content=[TextBlock(text="hola")], model="claude-x")
    out = translate(msg)
    assert out == [TextDelta(text="hola")]

def test_bash_tool_becomes_tool_use():
    msg = AssistantMessage(content=[
        ToolUseBlock(id="t1", name="Bash", input={"command": "ls -la"})], model="claude-x")
    out = translate(msg)
    assert out == [ToolUse(id="t1", name="Bash", detail="ls -la")]

def test_write_tool_becomes_edit_with_added_lines():
    msg = AssistantMessage(content=[
        ToolUseBlock(id="e1", name="Write", input={"file_path": "a.py", "content": "x\ny\nz"})], model="claude-x")
    out = translate(msg)
    assert out == [Edit(id="e1", path="a.py", added=3, removed=0)]

def test_edit_tool_counts_old_and_new_lines():
    msg = AssistantMessage(content=[ToolUseBlock(id="e2", name="Edit",
        input={"file_path": "b.py", "old_string": "a\nb", "new_string": "a\nb\nc\nd"})], model="claude-x")
    out = translate(msg)
    assert out == [Edit(id="e2", path="b.py", added=4, removed=2)]

def test_result_message_becomes_usage_then_done():
    msg = ResultMessage(session_id="s1", total_cost_usd=0.01,
        usage={"input_tokens": 10, "output_tokens": 20}, num_turns=1,
        subtype="success", duration_ms=100, duration_api_ms=80, is_error=False, result="ok")
    out = translate(msg)
    assert out == [Usage(input_tokens=10, output_tokens=20, total_tokens=30),
                   Done(session_id="s1", is_error=False)]
