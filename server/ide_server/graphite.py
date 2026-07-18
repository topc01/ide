from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

from ide_server import git


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

    # Verificar que todos los padres referenciados existan
    for parent_name in children:
        if parent_name not in by_name:
            # Encontrar la primera rama huérfana de este padre para el error
            orphan_names = children[parent_name]
            raise GraphiteError(f"stack inconsistente: el padre '{parent_name}' de '{orphan_names[0]}' no existe")

    out: list[dict] = []

    def visit(name: str) -> None:
        r = by_name[name]
        parent = r["parent"]
        needs = False
        if parent is not None:
            if parent not in by_name:
                raise GraphiteError(f"stack inconsistente: el padre '{parent}' de '{name}' no existe")
            needs = r["parentRevision"] != by_name[parent]["revision"]
        out.append({
            "name": name, "parent": parent, "isTrunk": parent is None,
            "current": name == current, "needsRestack": needs, "revision": r["revision"],
        })
        for child in sorted(children.get(name, [])):
            visit(child)

    visit(trunk)
    return out


def read_stack(repo_path: Path) -> list[dict]:
    db = repo_path / ".git" / ".graphite_metadata.db"
    if not db.exists():
        raise GraphiteError(f"no es un repo Graphite (falta {db.name})")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            cur = con.execute(
                "SELECT branch_name, parent_branch_name, parent_branch_revision, branch_revision "
                "FROM branch_metadata")
            rows = cur.fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise GraphiteError(f"no se pudo leer la metadata de Graphite: {exc}") from exc
    return [{"name": n, "parent": p, "parentRevision": pr, "revision": rev}
            for (n, p, pr, rev) in rows]


def branch_commits(repo_path: Path, revision: str, parent_revision: str | None) -> list[dict]:
    if parent_revision is None:
        return []
    raw = git._git(repo_path, ["log", "--format=%h%x1f%s", f"{parent_revision}..{revision}"])
    out: list[dict] = []
    for line in raw.split("\n"):
        if not line:
            continue
        h, _, msg = line.partition("\x1f")
        out.append({"hash": h, "message": msg})
    return out


def commit_files(repo_path: Path, sha: str) -> list[dict]:
    raw = git._git(repo_path, ["show", "--numstat", "--format=", sha])
    return [{"path": f["path"], "added": f["added"], "removed": f["removed"]}
            for f in git.parse_numstat(raw)]


def restack(repo_path: Path, branch: str) -> None:
    if shutil.which("gt") is None:
        raise GraphiteError("gt (Graphite) no está instalado")
    out = subprocess.run(
        ["gt", "restack", "--branch", branch, "--only", "--no-interactive", "-q",
         "--cwd", str(repo_path)],
        capture_output=True, text=True)
    if out.returncode != 0:
        # defensivo: no dejar el repo a medio-rebase
        subprocess.run(["git", "-C", str(repo_path), "rebase", "--abort"],
                       capture_output=True, text=True)
        msg = (out.stderr or out.stdout or "").strip() or "gt restack falló"
        raise GraphiteError(f"restack falló (¿conflictos?): {msg}")
