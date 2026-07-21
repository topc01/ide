from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _instances_dir(home: Path) -> Path:
    d = home / ".ide" / "instances"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def register_instance(home: Path, *, port: int, host: str, workspace: str, pid: int) -> Path:
    path = _instances_dir(home) / f"{port}.json"
    path.write_text(json.dumps({
        "pid": pid, "port": port, "host": host, "workspace": workspace,
        "url": f"http://{host}:{port}", "started": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    return path


def unregister_instance(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def list_instances(home: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(_instances_dir(home).glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not _pid_alive(int(data.get("pid", -1))):
            p.unlink(missing_ok=True)
            continue
        out.append(data)
    out.sort(key=lambda d: d.get("port", 0))
    return out
