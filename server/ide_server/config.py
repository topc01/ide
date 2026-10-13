from __future__ import annotations
import tomllib
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8787
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = {"env_prefix": "IDE_"}


def load_workspace_config(root: Path) -> dict:
    path = root / ".ide" / "config.toml"
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text())


SESSION_DEFAULTS = {"default_permissions": "analyze", "max_running": None,
                    "claude_command": "claude"}


def sessions_config(root: Path) -> dict:
    cfg = {**SESSION_DEFAULTS, **load_workspace_config(root).get("sessions", {})}
    if cfg["default_permissions"] not in ("analyze", "full", "default"):
        raise ValueError(f"[sessions] default_permissions inválido: "
                         f"{cfg['default_permissions']!r} (analyze | full | default)")
    return cfg


def reviews_config(root: Path) -> dict:
    return {"poll_interval": 300, **load_workspace_config(root).get("reviews", {})}


def ui_modules(root: Path) -> list[str]:
    return list(load_workspace_config(root).get("ui", {}).get("modules", ["sessions", "terminal"]))
