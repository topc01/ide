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
    mr = cfg["max_running"]
    if mr is not None and (not isinstance(mr, int) or isinstance(mr, bool) or mr < 1):
        raise ValueError(f"[sessions] max_running inválido: {mr!r} (entero >= 1, u omitido)")
    return cfg


def reviews_config(root: Path) -> dict:
    return {"poll_interval": 300, "github_interval": 120, "github_org": None, "plugins": [],
            **load_workspace_config(root).get("reviews", {})}


def manager_config(root: Path) -> dict:
    """[manager] nightly = "HH:MM" (hora de la revisión semanal de feedback; "" la apaga) y weekday = el día
    ("mon".."sun", lunes por defecto)."""
    return {"nightly": "03:00", "weekday": "mon", **load_workspace_config(root).get("manager", {})}


def ui_modules(root: Path) -> list[str]:
    return list(load_workspace_config(root).get("ui", {}).get("modules", ["sessions", "dev", "terminal", "prompts", "stack", "review", "deps", "servers", "db", "later", "notion", "evidence", "attachments", "explorer", "config"]))


def ide_config(root: Path) -> dict:
    """`[ide]`: la sesión "IDE" (pestaña junto a la manager). `repo` = el repo del IDE (su claude corre
    ahí); `resume` = la conversación de claude que retoma la primera vez (opcional)."""
    cfg = load_workspace_config(root).get("ide", {})
    return {"repo": cfg.get("repo"), "resume": cfg.get("resume")}
