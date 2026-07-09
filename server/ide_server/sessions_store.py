from __future__ import annotations
import json
import re
from pathlib import Path


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return s.strip("-")


def _path(root: Path) -> Path:
    return root / ".ide" / "sessions.json"


def load_sessions(root: Path) -> list[dict]:
    path = _path(root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("sessions", [])
    except (json.JSONDecodeError, OSError):
        # sin fallos silenciosos: respaldar y re-iniciar (el aviso lo emite la capacidad)
        path.replace(path.with_suffix(".json.bak"))
        return []


def save_sessions(root: Path, tree: list[dict]) -> None:
    _path(root).write_text(json.dumps({"sessions": tree}, indent=2), encoding="utf-8")


def find_node(tree: list[dict], node_id: str) -> dict | None:
    for node in tree:
        if node.get("id") == node_id:
            return node
        found = find_node(node.get("children", []), node_id)
        if found is not None:
            return found
    return None


def insert_node(tree: list[dict], parent_id: str | None, node: dict) -> None:
    if parent_id is None:
        tree.append(node)
        return
    parent = find_node(tree, parent_id)
    if parent is None:
        raise KeyError(parent_id)
    parent.setdefault("children", []).append(node)


def rename_node(tree: list[dict], node_id: str, name: str) -> bool:
    node = find_node(tree, node_id)
    if node is None:
        return False
    node["name"] = name
    return True


def remove_node(tree: list[dict], node_id: str) -> bool:
    for i, node in enumerate(tree):
        if node.get("id") == node_id:
            del tree[i]
            return True
        if remove_node(node.get("children", []), node_id):
            return True
    return False
