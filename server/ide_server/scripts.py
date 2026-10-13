# server/ide_server/scripts.py
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
from typing import TextIO
from ide_server.sessions_fs import SessionError, session_path, read_toml, update_session_toml


def scripts_dir(root: Path, repo: str) -> Path:
    return root / ".ide" / "scripts" / repo


def list_scripts(root: Path, repo: str) -> list[dict]:
    d = scripts_dir(root, repo)
    if not d.is_dir():
        return []
    return [{"name": p.name, "executable": os.access(p, os.X_OK)}
            for p in sorted(d.iterdir()) if p.is_file() and not p.name.startswith(".")]


def has_script(root: Path, repo: str, name: str) -> bool:
    return (scripts_dir(root, repo) / name).is_file()


def script_argv(root: Path, repo: str, name: str) -> list[str]:
    path = scripts_dir(root, repo) / name
    if not path.is_file():
        raise SessionError("script_not_found", f"no existe el script {repo}/{name} ({path})")
    if not os.access(path, os.X_OK):
        raise SessionError("script_not_executable",
                           f"{repo}/{name} no es ejecutable: chmod +x {path}")
    return [str(path)]


def script_env(root: Path, sid: str, repo: str, base_env: dict | None = None) -> dict[str, str]:
    data = read_toml(session_path(root, sid) / ".session.toml")
    env = dict(os.environ if base_env is None else base_env)
    env.update(IDE_SESSION_ID=sid, IDE_REPO=repo, IDE_ROOT_REPO=str(root / repo),
               IDE_WORKSPACE=str(root))
    port = data.get("ports", {}).get(repo)
    if port is not None:
        env["IDE_PORT"] = str(port)
    return env


def run_script(root: Path, sid: str, repo: str, name: str, *, out: TextIO | None = None,
               base_env: dict | None = None) -> int:
    from ide_server.repos_fs import worktree_path
    out = out or sys.stdout
    try:
        argv = script_argv(root, repo, name)
        proc = subprocess.Popen(argv, cwd=worktree_path(root, sid, repo),
                                env=script_env(root, sid, repo, base_env),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            out.write(line)
        code = proc.wait()
    except SessionError:
        if name == "setup":
            _record_setup(root, sid, repo, "failed")
        raise
    except OSError as exc:
        if name == "setup":
            _record_setup(root, sid, repo, "failed")
        raise SessionError("script_failed",
                           f"no se pudo ejecutar {repo}/{name}: {exc}") from exc
    if name == "setup":
        _record_setup(root, sid, repo, "ok" if code == 0 else "failed")
    return code


def _record_setup(root: Path, sid: str, repo: str, state: str) -> None:
    update_session_toml(root, sid, lambda d: d.setdefault("setup", {}).update({repo: state}))
