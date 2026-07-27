from __future__ import annotations
import asyncio
import json
from pathlib import Path
from ide_server.plugins import Registry
from ide_server.workspace import resolve_cwd
from ide_server.capabilities.files import _safe_join

MAX_MATCHES = 2000
MAX_FILES = 500


class SearchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _build_args(query: str, opts: dict) -> list[str]:
    args = ["rg", "--json"]
    if opts.get("regex", True) is False:
        args.append("-F")                       # texto literal
    args.append("-s" if opts.get("caseSensitive") else "-i")
    if opts.get("wholeWord"):
        args.append("-w")
    for g in opts.get("include") or []:
        args += ["-g", g]
    for g in opts.get("exclude") or []:
        args += ["-g", f"!{g}"]
    ctx = int(opts.get("context") or 0)
    if ctx > 0:
        args += ["-C", str(ctx)]
    args += ["--", query]
    return args


def _byte_to_char(text: str, byte_off: int) -> int:
    # rg da offsets en bytes; el frontend resalta sobre chars.
    return len(text.encode("utf-8")[:byte_off].decode("utf-8", "ignore"))


def _parse(stdout: bytes) -> dict:
    by_path: dict[str, list] = {}
    order: list[str] = []
    total = 0
    truncated = False
    for raw in stdout.splitlines():
        if not raw:
            continue
        evt = json.loads(raw)
        if evt.get("type") != "match":
            continue
        data = evt["data"]
        path = data["path"]["text"]
        text = data["lines"]["text"].rstrip("\n")
        line = data["line_number"]
        ranges = [[_byte_to_char(text, sm["start"]), _byte_to_char(text, sm["end"])]
                  for sm in data.get("submatches", [])]
        if path not in by_path:
            if len(order) >= MAX_FILES:
                truncated = True
                continue
            by_path[path] = []
            order.append(path)
        if total >= MAX_MATCHES:
            truncated = True
            continue
        by_path[path].append({"line": line, "text": text, "ranges": ranges})
        total += 1
    matches = [{"path": p, "lines": by_path[p]} for p in order if by_path[p]]
    return {"matches": matches, "total": total,
            "files": len(matches), "truncated": truncated}


def register(registry: Registry, root: Path) -> None:
    async def content(payload: dict) -> dict:
        base = resolve_cwd(root, payload)
        _safe_join(base, "")                     # asegura base dentro del root
        query = payload.get("query") or ""
        if not query:
            return {"matches": [], "total": 0, "files": 0, "truncated": False}
        args = _build_args(query, payload.get("options") or {})
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, cwd=str(base),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError:
            raise SearchError("rg_missing", "ripgrep (rg) no está instalado")
        stdout, stderr = await proc.communicate()
        # rg: exit 0 = con matches, 1 = sin matches, 2 = error (regex inválido, etc.)
        if proc.returncode == 2:
            raise SearchError("bad_regex", stderr.decode("utf-8", "ignore").strip())
        return _parse(stdout)

    registry.register("search.content", content)
