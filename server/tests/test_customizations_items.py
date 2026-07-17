import json
from ide_server.customizations.readers import read_tools, TOOLS
from ide_server.customizations.items import build_items


def test_read_tools_marks_in_use(tmp_path):
    rows = read_tools({"bash", "read"})
    assert {r["label"] for r in rows} == set(TOOLS)
    by = {r["label"]: r["inUse"] for r in rows}
    assert by["bash"] is True and by["glob"] is False


def test_build_items_has_nine_in_order(tmp_path):
    (tmp_path / ".ide").mkdir()
    (tmp_path / ".ide" / "sessions.json").write_text(json.dumps({"sessions": []}))
    home = tmp_path / "home"
    items = build_items(home, tmp_path)
    assert [i["key"] for i in items] == [
        "overview", "roles", "agents", "skills", "instructions", "hooks", "mcp", "plugins", "tools"]
    roles = next(i for i in items if i["key"] == "roles")
    assert roles["count"] == len(roles["rows"]) and roles["count"] >= 4   # PRESETS
    overview = next(i for i in items if i["key"] == "overview")
    assert isinstance(overview["rows"], list)   # resumen (conteos)
