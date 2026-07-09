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
