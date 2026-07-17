from __future__ import annotations
from pathlib import Path
from ide_server.customizations.readers import (
    read_roles, read_mcp, read_instructions, read_hooks, read_skills,
    read_agents, read_plugins, read_tools, roles_in_use,
)

_META = {
    "overview": ("Overview", "Resumen del catálogo global de customizations."),
    "roles": ("Roles", "Roles disponibles para las sesiones."),
    "agents": ("Agents", "Subagentes disponibles."),
    "skills": ("Skills", "Skills reutilizables."),
    "instructions": ("Instructions", "Instrucciones globales (CLAUDE.md)."),
    "hooks": ("Hooks", "Hooks de ciclo de vida."),
    "mcp": ("MCP Servers", "Servidores MCP conectados."),
    "plugins": ("Plugins", "Plugins instalados."),
    "tools": ("Tools", "Tools disponibles para el agente."),
}


def _used_tools(home: Path, workspace_root: Path) -> set[str]:
    from ide_server.roles import resolve_role
    used: set[str] = set()
    for name in roles_in_use(workspace_root):
        r = resolve_role(workspace_root, name)
        if r and r.tools:
            used.update(r.tools)
    return used


def _item(key: str, rows: list[dict]) -> dict:
    title, desc = _META[key]
    return {"key": key, "title": title, "description": desc, "count": len(rows), "rows": rows}


def build_items(home: Path, workspace_root: Path) -> list[dict]:
    roles = read_roles(home, workspace_root)
    agents = read_agents(home)
    skills = read_skills(home)
    instructions = read_instructions(home)
    hooks = read_hooks(home)
    mcp = read_mcp(home)
    plugins = read_plugins(home)
    tools = read_tools(_used_tools(home, workspace_root))
    counts = {"roles": len(roles), "agents": len(agents), "skills": len(skills),
              "instructions": len(instructions), "hooks": len(hooks), "mcp": len(mcp),
              "plugins": len(plugins), "tools": len(tools)}
    overview = [{"label": f"{_META[k][0]}: {v}", "inUse": False} for k, v in counts.items()]
    return [
        _item("overview", overview), _item("roles", roles), _item("agents", agents),
        _item("skills", skills), _item("instructions", instructions), _item("hooks", hooks),
        _item("mcp", mcp), _item("plugins", plugins), _item("tools", tools),
    ]
