import json, subprocess
from ide_server.sessions_fs import seed_workspace, render_template
from ide_server.cli import init_workspace
from ide_server.config import sessions_config, ui_modules


def _repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)


def test_seed_creates_files_with_repo_map(tmp_path):
    _repo(tmp_path / "repo-a"); _repo(tmp_path / "repo-b")
    seed_workspace(tmp_path)
    ide = tmp_path / ".ide"
    claude_md = (ide / "sessions" / "CLAUDE.md").read_text()
    assert "repo-a" in claude_md and "repo-b" in claude_md and "ide repo add" in claude_md
    for name in ("ticket", "review"):
        assert (ide / "sessions" / "templates" / f"{name}.md").is_file()
    assert not (ide / "sessions" / "templates" / "main.md").exists()   # la principal no se autolanza
    assert "Notion" in (ide / "prompts" / "tickets-y-prs.md").read_text()
    analyze = json.loads((ide / "permissions" / "analyze.json").read_text())
    allow = analyze["permissions"]["allow"]
    assert "Bash(ide repo add:*)" in allow and "Bash(ide session new:*)" not in allow
    for cmd in ("ls", "cat", "head", "tail", "wc", "find", "rg", "grep", "git branch"):
        assert f"Bash({cmd}:*)" in allow
    assert "Bash(git remote -v)" in allow
    assert {"Bash(git diff --output:*)", "Bash(git log --output:*)"} <= set(
        analyze["permissions"]["deny"])
    main = json.loads((ide / "permissions" / "main.json").read_text())["permissions"]
    assert set(allow) < set(main["allow"]) and main["deny"] == analyze["permissions"]["deny"]
    assert {"Bash(ide session new:*)", "Bash(ide session ls:*)"} <= set(main["allow"])
    assert json.loads((ide / "permissions" / "full.json").read_text())
    assert (ide / "scripts").is_dir() and (ide / "worktrees").is_dir()


def test_seed_never_overwrites(tmp_path):
    seed_workspace(tmp_path)
    md = tmp_path / ".ide" / "sessions" / "CLAUDE.md"
    md.write_text("mío")
    created = seed_workspace(tmp_path)
    assert md.read_text() == "mío" and created == []


def test_ticket_template_renders_with_dispatch_vars(tmp_path):
    seed_workspace(tmp_path)
    tpl = (tmp_path / ".ide" / "sessions" / "templates" / "ticket.md").read_text()
    out = render_template(tpl, {"id": "fin-1", "title": "T", "notion_url": "u"})
    assert "fin-1" in out and "TICKET.md" in out


def test_init_workspace_seeds_and_config(tmp_path):
    init_workspace(tmp_path)
    assert (tmp_path / ".ide" / "sessions" / "CLAUDE.md").is_file()
    assert not (tmp_path / ".ide" / "tasks").exists()
    assert sessions_config(tmp_path)["default_permissions"] == "analyze"
    assert ui_modules(tmp_path) == ["sessions", "terminal"]
