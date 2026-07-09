from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
from ide_server.config import load_workspace_config


@dataclass(frozen=True)
class Role:
    name: str
    model: str | None = None
    system_prompt: str | None = None
    read_only: bool = False
    tools: list[str] | None = None


PRESETS: dict[str, Role] = {
    "lector": Role("lector", model="haiku", read_only=True),
    "revisor": Role("revisor", system_prompt="Revisá el código y reportá problemas.", read_only=True),
    "arquitecto": Role("arquitecto", system_prompt="Diseñá la arquitectura.", read_only=False),
    "disenador": Role("disenador", system_prompt="Enfocate en frontend/UI.", read_only=False),
}


def load_roles(root: Path) -> dict[str, Role]:
    roles = dict(PRESETS)
    cfg = load_workspace_config(root).get("roles", {})
    for name, data in cfg.items():
        base = roles.get(name, Role(name))
        roles[name] = replace(
            base,
            name=name,
            model=data.get("model", base.model),
            system_prompt=data.get("system_prompt", base.system_prompt),
            read_only=data.get("read_only", base.read_only),
            tools=data.get("tools", base.tools),
        )
    return roles


def resolve_role(root: Path, name: str | None) -> Role | None:
    if name is None:
        return None
    return load_roles(root)[name]
