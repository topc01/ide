# server/ide_server/ids_migration.py
"""Una vez: las sesiones de ticket pasan a llamarse por su número de desarrollo (`n-7b9b0a5c76` → `98`) y la
manager a `manager`. Mueve, por sesión: su carpeta (`.ide/sessions`), sus worktrees (`.ide/worktrees`,
reparados con `git worktree repair`), sus servidores (`.ide/runs`) y su conversación de claude
(`~/.claude/projects/<carpeta codificada>`), rehace los enlaces a sus worktrees, y reemplaza el id en toda
la base (filas, historial, claves y valores) y en los .md de las sesiones. Las sesiones con claude
corriendo se paran antes y se relanzan después; sus servidores se paran. Las revisiones, la IDE, Recursos y
las archivadas no cambian."""
from __future__ import annotations
import json
import re
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from ide_server.sessions_fs import list_sessions, read_toml, session_path, write_toml

KEEP = {"ide", "recursos", "manager"}


def _enc(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", str(path))


def plan(root: Path, db) -> list[tuple[str, str]]:
    """[(id viejo, id nuevo)] de las sesiones vivas que cambian."""
    idx = db.with_prefix("devidx:")
    out = []
    for s in list_sessions(root):
        sid, kind = s["id"], s.get("kind")
        if sid in KEEP or sid.isdigit():
            continue
        if kind == "main":
            out.append((sid, "manager"))
        elif kind == "ticket" and idx.get(f"s:{sid}"):
            out.append((sid, str(idx[f"s:{sid}"])))
    return out


def _sub(text: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return text
    rx = re.compile(r"(?<![A-Za-z0-9-])(" + "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True))
                    + r")(?![A-Za-z0-9-])")
    return rx.sub(lambda m: mapping[m.group(1)], text)


def _db(db_path: Path, mapping: dict[str, str], log: Callable[[str], None]) -> None:
    """El id en toda la base: cada columna de texto de cada tabla (claves incluidas)."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("BEGIN IMMEDIATE")
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for t in tables:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t})") if (c[2] or "").upper() == "TEXT"]
            pk = [c[1] for c in conn.execute(f"PRAGMA table_info({t})") if c[5]] or ["rowid"]
            rows = conn.execute(f"SELECT rowid, {', '.join(cols)} FROM {t}").fetchall()
            n = 0
            for row in rows:
                new = [(_sub(v, mapping) if isinstance(v, str) else v) for v in row[1:]]
                if new != list(row[1:]):
                    conn.execute(f"UPDATE {t} SET {', '.join(f'{c} = ?' for c in cols)} WHERE rowid = ?", (*new, row[0]))
                    n += 1
            if n:
                log(f"base: {t}: {n} filas")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def migrate(root: Path, db_path: Path, *, stop: Callable[[str], bool], stop_runs: Callable[[str], None],
            start: Callable[[str], None], home: Path, log: Callable[[str], None]) -> dict:
    """`stop(sid)` para su claude y dice si corría; `stop_runs(sid)` para sus servidores; `start(sid)` lo
    relanza retomando su conversación. Devuelve {mapping, relaunched, backup}."""
    from ide_server.db import Db
    root = root.resolve()
    pairs = plan(root, Db(root))
    mapping = dict(pairs)
    if not pairs:
        return {"mapping": {}, "relaunched": [], "backup": None}
    ide = root / ".ide"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ide / "backups" / f"ids-{stamp}"
    backup.mkdir(parents=True)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup / "ide.db")
    src.backup(dst)
    src.close(); dst.close()
    (backup / "mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    log(f"respaldo: {backup}")
    running = [old for old, _ in pairs if stop(old)]
    for old, _ in pairs:
        stop_runs(old)
    time.sleep(2)
    for old, new in pairs:
        # worktrees: se mueve la carpeta y git repara sus enlaces
        wt_old, wt_new = ide / "worktrees" / old, ide / "worktrees" / new
        if wt_old.is_dir():
            wt_old.rename(wt_new)
            for wt in sorted(p for p in wt_new.iterdir() if (p / ".git").is_file()):
                r = subprocess.run(["git", "-C", str(wt), "worktree", "repair"], capture_output=True, text=True)
                if r.returncode != 0:
                    log(f"  ⚠ {wt}: git worktree repair: {r.stderr.strip()}")
        # la sesión, con sus enlaces a los worktrees
        s_old, s_new = session_path(root, old), session_path(root, new)
        s_old.rename(s_new)
        for link in [p for p in s_new.iterdir() if p.is_symlink()]:
            target = str(link.readlink())
            fixed = target.replace(f"/worktrees/{old}/", f"/worktrees/{new}/")
            if fixed != target:
                link.unlink()
                link.symlink_to(fixed)
        toml = s_new / ".session.toml"
        data = read_toml(toml)
        if isinstance(data.get("claude_name"), str):
            data["claude_name"] = _sub(data["claude_name"], mapping)
        write_toml(toml, data)
        # servidores
        r_old = ide / "runs" / old
        if r_old.is_dir():
            r_old.rename(ide / "runs" / new)
            for meta in (ide / "runs" / new).rglob("meta.json"):
                meta.write_text(_sub(meta.read_text(encoding="utf-8").replace(f"/worktrees/{old}/", f"/worktrees/{new}/"),
                                     {}), encoding="utf-8")
        # la conversación de claude (está guardada por la carpeta de la sesión)
        p_old, p_new = home / ".claude" / "projects" / _enc(s_old), home / ".claude" / "projects" / _enc(s_new)
        if p_old.is_dir() and not p_new.exists():
            p_old.rename(p_new)
        log(f"{old} → {new}")
    _db(db_path, mapping, log)
    for f in sorted((ide / "sessions").glob("*/*.md")) + [ide / "sessions" / "CLAUDE.md", ide / "manager.md"]:
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            new_text = _sub(text, mapping)
            if new_text != text:
                f.write_text(new_text, encoding="utf-8")
    relaunched = []
    for old in running:
        try:
            start(mapping[old])
            relaunched.append(mapping[old])
        except Exception as exc:  # noqa: BLE001
            log(f"  ⚠ no pude relanzar {mapping[old]}: {exc}")
    return {"mapping": mapping, "relaunched": relaunched, "backup": str(backup)}
