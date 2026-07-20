from __future__ import annotations
import re

_H1 = re.compile(r"^#\s+(.+?)\s*$")
_STATUS = re.compile(r"^status:\s*(.+?)\s*$", re.IGNORECASE)


def parse_meta(markdown: str) -> dict:
    title = None
    status = None
    for line in markdown.splitlines():
        if title is None:
            m = _H1.match(line)
            if m:
                title = m.group(1)
        if status is None:
            m = _STATUS.match(line)
            if m:
                status = m.group(1)
    return {"title": title, "status": status}
