from __future__ import annotations
from pathlib import Path


def parse_numstat(raw: str) -> list[dict]:
    out: list[dict] = []
    for line in raw.split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        added, removed = parts[0], parts[1]
        out.append({
            "path": "\t".join(parts[2:]),
            "added": None if added == "-" else int(added),
            "removed": None if removed == "-" else int(removed),
        })
    return out


def parse_porcelain(raw: str) -> list[dict]:
    out: list[dict] = []
    for line in raw.split("\n"):
        if not line:
            continue
        code = line[:2]
        p = line[3:]
        if " -> " in p:
            p = p.split(" -> ")[1]
        trimmed = code.strip()
        status = "?" if code == "??" else (trimmed[0] if trimmed else "?")
        out.append({"path": p, "status": status})
    return out


def merge_changes(porcelain: list[dict], numstat: list[dict]) -> list[dict]:
    by_path: dict[str, dict] = {}
    for p in porcelain:
        by_path[p["path"]] = {"path": p["path"], "status": p["status"], "added": 0, "removed": 0}
    for n in numstat:
        existing = by_path.get(n["path"]) or {
            "path": n["path"], "status": "M", "added": 0, "removed": 0}
        existing["added"] = n["added"] or 0
        existing["removed"] = n["removed"] or 0
        by_path[n["path"]] = existing
    return list(by_path.values())


def parse_diff(raw: str) -> list[dict]:
    out: list[dict] = []
    for line in raw.split("\n"):
        if (line.startswith("diff ") or line.startswith("index ")
                or line.startswith("+++") or line.startswith("---")):
            continue
        if line.startswith("@@"):
            out.append({"type": "hunk", "text": line})
        elif line.startswith("+"):
            out.append({"type": "add", "text": line[1:]})
        elif line.startswith("-"):
            out.append({"type": "del", "text": line[1:]})
        else:
            out.append({"type": "ctx", "text": line[1:] if line.startswith(" ") else line})
    while out and out[-1]["type"] == "ctx" and out[-1]["text"] == "":
        out.pop()
    return out


def untracked_lines(path: Path) -> int:
    try:
        stt = path.stat()
        if not path.is_file() or stt.st_size > 5 * 1024 * 1024:
            return 0
        data = path.read_bytes()
        if b"\x00" in data or not data:
            return 0
        n = data.count(b"\n")
        return n if data.endswith(b"\n") else n + 1
    except OSError:
        return 0
