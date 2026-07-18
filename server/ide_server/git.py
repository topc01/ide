from __future__ import annotations
import subprocess
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


class GitError(Exception):
    pass


def _git(cwd: Path, args: list[str]) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise GitError(out.stderr.strip() or f"git {' '.join(args)} falló")
    return out.stdout


def repo_status(cwd: Path) -> dict:
    branch = _git(cwd, ["branch", "--show-current"]).strip() or "(detached)"
    head = _git(cwd, ["rev-parse", "HEAD"]).strip()
    numstat = parse_numstat(_git(cwd, ["diff", "--numstat", "HEAD"]))
    porcelain = parse_porcelain(_git(cwd, ["status", "--porcelain", "-uall"]))
    files = merge_changes(porcelain, numstat)
    for f in files:
        if f["status"] == "?" and not f["added"]:
            f["added"] = untracked_lines(cwd / f["path"])
    return {
        "name": cwd.name, "path": str(cwd), "branch": branch, "head": head,
        "files": files,
        "totalAdded": sum(f["added"] or 0 for f in files),
        "totalRemoved": sum(f["removed"] or 0 for f in files),
    }


def file_diff_full(cwd: Path, path: str, status: str) -> list[dict]:
    if status == "?":
        try:
            data = (cwd / path).read_bytes()
        except OSError as exc:
            return [{"type": "ctx", "text": f"no se pudo leer el archivo: {exc}"}]
        if b"\x00" in data:
            return [{"type": "ctx", "text": "(binario)"}]
        return [{"type": "add", "text": t} for t in data.decode("utf-8", "replace").split("\n")]
    return parse_diff(_git(cwd, ["diff", "HEAD", "-U1000000", "--", path]))
