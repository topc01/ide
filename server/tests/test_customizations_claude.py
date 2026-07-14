from ide_server.customizations.readers import (
    read_mcp, read_instructions, read_hooks, read_skills, read_agents, read_plugins,
)


def test_absent_sources_return_empty(tmp_path):
    for fn in (read_mcp, read_instructions, read_hooks, read_skills, read_agents, read_plugins):
        assert fn(tmp_path) == []


def test_read_mcp_lists_server_names(tmp_path):
    (tmp_path / ".claude.json").write_text('{"mcpServers": {"github": {}, "linear": {}}}')
    assert {r["label"] for r in read_mcp(tmp_path)} == {"github", "linear"}


def test_read_hooks_lists_keys(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": [], "Stop": []}}')
    assert {r["label"] for r in read_hooks(tmp_path)} == {"PreToolUse", "Stop"}


def test_read_skills_and_agents_and_plugins_list_dir_entries(tmp_path):
    c = tmp_path / ".claude"
    (c / "skills" / "make-deck").mkdir(parents=True)
    (c / "agents").mkdir(parents=True)
    (c / "agents" / "reviewer.md").write_text("x")
    (c / "plugins" / "superpowers").mkdir(parents=True)
    assert [r["label"] for r in read_skills(tmp_path)] == ["make-deck"]
    assert [r["label"] for r in read_agents(tmp_path)] == ["reviewer"]
    assert [r["label"] for r in read_plugins(tmp_path)] == ["superpowers"]


def test_read_instructions_presence(tmp_path):
    assert read_instructions(tmp_path) == []
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "CLAUDE.md").write_text("reglas")
    assert [r["label"] for r in read_instructions(tmp_path)] == ["CLAUDE.md"]


def test_corrupt_json_degrades_to_empty(tmp_path):
    (tmp_path / ".claude.json").write_text("{not json")
    assert read_mcp(tmp_path) == []
