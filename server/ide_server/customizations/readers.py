from __future__ import annotations
import json, tomllib
from pathlib import Path


def roles_in_use(workspace_root: Path) -> set[str]:
    from ide_server.sessions_store import load_sessions
    used: set[str] = set()

    def walk(nodes: list[dict]) -> None:
        for n in nodes:
            if n.get("role"):
                used.add(n["role"])
            walk(n.get("children") or [])

    try:
        walk(load_sessions(workspace_root))
    except Exception:
        pass
    return used


def read_roles(home: Path, workspace_root: Path) -> list[dict]:
    from ide_server.roles import PRESETS
    names: list[str] = list(PRESETS.keys())
    global_cfg = home / ".ide" / "config.toml"
    if global_cfg.exists():
        try:
            data = tomllib.loads(global_cfg.read_text())
            for name in (data.get("roles") or {}):
                if name not in names:
                    names.append(name)
        except Exception:
            pass
    used = roles_in_use(workspace_root)
    return [{"label": n, "inUse": n in used} for n in names]


def _rows(labels) -> list[dict]:
    return [{"label": str(l), "inUse": False} for l in labels]


def _json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def read_mcp(home: Path) -> list[dict]:
    return _rows((_json(home / ".claude.json").get("mcpServers") or {}).keys())


def read_hooks(home: Path) -> list[dict]:
    return _rows((_json(home / ".claude" / "settings.json").get("hooks") or {}).keys())


def read_instructions(home: Path) -> list[dict]:
    p = home / ".claude" / "CLAUDE.md"
    return _rows(["CLAUDE.md"]) if p.exists() and p.read_text().strip() else []


def _dir_entries(d: Path, *, files: bool) -> list[str]:
    if not d.is_dir():
        return []
    out = []
    for entry in sorted(d.iterdir()):
        if files and entry.is_file():
            out.append(entry.stem)
        elif not files and entry.is_dir():
            out.append(entry.name)
    return out


def read_skills(home: Path) -> list[dict]:
    return _rows(_dir_entries(home / ".claude" / "skills", files=False))


def read_agents(home: Path) -> list[dict]:
    return _rows(_dir_entries(home / ".claude" / "agents", files=True))


def read_plugins(home: Path) -> list[dict]:
    return _rows(_dir_entries(home / ".claude" / "plugins", files=False))


TOOLS = ["bash", "read", "write", "edit", "grep", "glob",
         "webSearch", "webFetch", "task", "todoWrite", "notebookEdit", "multiEdit"]


def read_tools(used_tools: set[str]) -> list[dict]:
    return [{"label": t, "inUse": t in used_tools} for t in TOOLS]
