import json
import pytest
from ide_server.plugins import Registry
from ide_server.capabilities import customizations as cap


@pytest.mark.asyncio
async def test_list_returns_nine_items(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps({"sessions": []}))
    home = tmp_path / "home"
    reg = Registry()
    cap.register(reg, tmp_path, home=home)
    out = await reg.dispatch("customizations.list", {})
    assert [i["key"] for i in out["items"]] == [
        "overview", "roles", "agents", "skills", "instructions", "hooks", "mcp", "plugins", "tools"]
