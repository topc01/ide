from __future__ import annotations
from pathlib import Path


class GraphiteError(Exception):
    pass


def build_stack(rows: list[dict], current: str | None) -> list[dict]:
    by_name = {r["name"]: r for r in rows}
    children: dict[str, list[str]] = {}
    trunk = None
    for r in rows:
        if r["parent"] is None:
            trunk = r["name"]
        else:
            children.setdefault(r["parent"], []).append(r["name"])
    if trunk is None:
        raise GraphiteError("stack sin trunk (ninguna branch sin padre)")

    out: list[dict] = []

    def visit(name: str) -> None:
        r = by_name[name]
        parent = r["parent"]
        needs = False
        if parent is not None and parent in by_name:
            needs = r["parentRevision"] != by_name[parent]["revision"]
        out.append({
            "name": name, "parent": parent, "isTrunk": parent is None,
            "current": name == current, "needsRestack": needs, "revision": r["revision"],
        })
        for child in sorted(children.get(name, [])):
            visit(child)

    visit(trunk)
    return out
