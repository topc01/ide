from __future__ import annotations
import re
from pathlib import Path
from ide_server.tasks.parse import parse_meta
from ide_server.sessions_store import slugify

_ID = re.compile(r"[A-Za-z0-9._-]+")


class InvalidTaskId(ValueError):
    pass


def _tasks_dir(root: Path) -> Path:
    d = root / ".ide" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _task_path(root: Path, task_id: str) -> Path:
    if not task_id or ".." in task_id or not _ID.fullmatch(task_id):
        raise InvalidTaskId(task_id)
    return _tasks_dir(root) / f"{task_id}.md"


def _meta(task_id: str, markdown: str) -> dict:
    m = parse_meta(markdown)
    return {"id": task_id, "title": m["title"] or task_id, "status": m["status"]}


def list_tasks(root: Path) -> list[dict]:
    out = []
    for p in sorted(_tasks_dir(root).glob("*.md")):
        out.append(_meta(p.stem, p.read_text(encoding="utf-8")))
    return out


def read_task(root: Path, task_id: str) -> dict:
    path = _task_path(root, task_id)
    if not path.is_file():
        raise KeyError(task_id)
    markdown = path.read_text(encoding="utf-8")
    return {**_meta(task_id, markdown), "markdown": markdown}


def write_task(root: Path, task_id: str, markdown: str) -> dict:
    path = _task_path(root, task_id)
    if not path.is_file():
        raise KeyError(task_id)
    path.write_text(markdown, encoding="utf-8")
    return _meta(task_id, markdown)


def create_task(root: Path, name: str) -> dict:
    base = slugify(name) or "tarea"
    slug, n = base, 1
    while (_tasks_dir(root) / f"{slug}.md").exists():
        n += 1
        slug = f"{base}-{n}"
    markdown = f"# {name}\nstatus: todo\n"
    (_tasks_dir(root) / f"{slug}.md").write_text(markdown, encoding="utf-8")
    return {"id": slug, "title": name, "status": "todo"}
