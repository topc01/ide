from __future__ import annotations
import json
import re
from pathlib import Path

_HEX32 = re.compile(r"([0-9a-fA-F]{32})(?![0-9a-fA-F])")
_DASHED = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


def parse_page_id(url_or_id: str) -> str:
    m = _DASHED.search(url_or_id)
    if m:
        return m.group(1).lower()
    m = _HEX32.search(url_or_id.replace("-", ""))
    if not m:
        raise ValueError(f"no se encontró un page id en: {url_or_id}")
    h = m.group(1).lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _path(root: Path) -> Path:
    return root / ".ide" / "notion.json"


def list_refs(root: Path) -> list[dict]:
    p = _path(root)
    if not p.is_file():
        return []
    try:
        return json.loads(p.read_text()).get("pages", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save(root: Path, pages: list[dict]) -> None:
    p = _path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pages": pages}, ensure_ascii=False, indent=2))


def add_ref(root: Path, id: str, title: str) -> None:
    # update in-place si ya existe (conserva su posición), si no lo agrega al final
    pages = list_refs(root)
    for r in pages:
        if r["id"] == id:
            r["title"] = title
            _save(root, pages)
            return
    pages.append({"id": id, "title": title})
    _save(root, pages)


def remove_ref(root: Path, id: str) -> None:
    _save(root, [r for r in list_refs(root) if r["id"] != id])
