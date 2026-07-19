from __future__ import annotations
import os
import tomllib
import tomli_w
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


def write_token(home: Path, token: str) -> None:
    cfg = home / ".ide" / "config.toml"
    data: dict = {}
    if cfg.is_file():
        data = tomllib.loads(cfg.read_text())
    data.setdefault("notion", {})["token"] = token
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(tomli_w.dumps(data))


def clear_token(home: Path) -> None:
    cfg = home / ".ide" / "config.toml"
    if not cfg.is_file():
        return
    try:
        data = tomllib.loads(cfg.read_text())
    except tomllib.TOMLDecodeError:
        return
    notion = data.get("notion")
    if isinstance(notion, dict):
        notion.pop("token", None)
        if not notion:
            data.pop("notion", None)
    cfg.write_text(tomli_w.dumps(data))
