from __future__ import annotations

_READ_ONLY_TOOLS = ["Read", "Grep", "Glob", "LS"]

def resolve_permission(role: dict | None, override: str | None) -> tuple[str, list[str] | None]:
    if override == "skip":
        return ("bypassPermissions", None)
    if override == "normal":
        return ("default", None)
    role = role or {}
    if role.get("read_only"):
        return ("default", list(_READ_ONLY_TOOLS))
    if role.get("skip"):
        return ("bypassPermissions", None)
    return ("default", None)
