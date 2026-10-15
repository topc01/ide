# server/ide_server/prompts.py
"""Prompts reutilizables (`.ide/prompts/*.md`): la UI los pega en el input de `claude`."""
from __future__ import annotations
from pathlib import Path
from ide_server.sessions_fs import SessionError


def prompts_dir(root: Path) -> Path:
    return root / ".ide" / "prompts"


def list_prompts(root: Path) -> list[dict]:
    d = prompts_dir(root)
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.md")):
        try:
            out.append({"name": f.stem, "text": f.read_text(encoding="utf-8")})
        except (OSError, UnicodeDecodeError) as exc:
            raise SessionError("bad_prompt", f"no se pudo leer {f}: {exc}") from exc
    return out
