from __future__ import annotations
import os
import tomllib
from pathlib import Path


def _token_from(cfg: Path) -> str | None:
    if not cfg.is_file():
        return None
    try:
        data = tomllib.loads(cfg.read_text())
    except tomllib.TOMLDecodeError:
        return None
    tok = (data.get("notion") or {}).get("token")
    return tok or None


def notion_token(home: Path, root: Path) -> str | None:
    env = os.environ.get("NOTION_TOKEN")
    if env:
        return env
    return (_token_from(root / ".ide" / "config.toml")
            or _token_from(home / ".ide" / "config.toml"))
