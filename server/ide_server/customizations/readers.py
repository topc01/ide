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
