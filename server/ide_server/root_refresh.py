# server/ide_server/root_refresh.py
"""Refresco de los checkouts raíz del workspace (cada hora, mientras el IDE corre): cada repo que usan las
sesiones se pone al día con `origin/develop` (fetch + fast-forward) solo si está en develop, sin cambios
en archivos versionados y sin un merge/rebase a medias; si no, se salta y queda anotado por qué. En la api,
si llegaron migraciones nuevas, migra la base raíz (`finnecto_dev`, la plantilla que se copia para cada
sesión), reconstruyendo antes su imagen si cambiaron las dependencias."""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

BRANCH = "develop"
API = "finnecto-api"
_DEPS = ("requirements", "pyproject.toml", "poetry.lock", "uv.lock", "Dockerfile", "docker-compose.yml")


def _git(repo: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout)


def repos(root: Path) -> list[Path]:
    """Los repos raíz que tienen worktrees de sesiones (`.ide/worktrees/<sesión>/<repo>`) o scripts del IDE."""
    names = {p.name for p in (root / ".ide" / "worktrees").glob("*/*") if p.is_dir() or p.is_symlink()}
    names |= {p.name for p in (root / ".ide" / "scripts").glob("*") if p.is_dir()}
    return sorted(root / n for n in names if (root / n / ".git").exists())


def _skip_reason(repo: Path) -> str | None:
    if _git(repo, "branch", "--show-current").stdout.strip() != BRANCH:
        return f"no está en {BRANCH}"
    if any(l and not l.startswith("??") for l in _git(repo, "status", "--porcelain").stdout.splitlines()):
        return "tiene cambios sin commitear"
    gitdir = Path(_git(repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    if any((gitdir / f).exists() for f in ("MERGE_HEAD", "REBASE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD")):
        return "tiene un merge o rebase a medias"
    return None


def _compose(repo: Path, *args: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", *args], cwd=repo, capture_output=True, text=True, timeout=timeout)


def _migrate_api(repo: Path, old: str, new: str) -> str:
    changed = _git(repo, "diff", "--name-only", old, new).stdout.splitlines()
    if not any("/migrations/" in f for f in changed):
        return "sin migraciones nuevas"
    if any(f.startswith(_DEPS) or f.split("/")[-1].startswith(_DEPS) for f in changed):
        b = _compose(repo, "build", "api", timeout=1800)
        if b.returncode != 0:
            return "no pude reconstruir la imagen: " + (b.stderr or b.stdout).strip()[-300:]
    _compose(repo, "up", "-d", "db", timeout=300)
    m = _compose(repo, "run", "--rm", "--no-deps", "api", "python", "manage.py", "migrate", "--noinput", timeout=1800)
    if m.returncode != 0:
        return "la migración de finnecto_dev falló: " + (m.stderr or m.stdout).strip()[-400:]
    return "finnecto_dev migrada"


def refresh(root: Path, db=None) -> list[dict]:
    """Una pasada. Devuelve, por repo, qué hizo: {repo, result, detail}. La base raíz se migra contra el último
    commit con que quedó migrada (`kv roots:migrated`), así una migración que falló se reintenta en la próxima."""
    out = []
    for repo in repos(root):
        r = {"repo": repo.name, "result": "skipped", "detail": ""}
        try:
            if (why := _skip_reason(repo)):
                r["detail"] = why
            else:
                f = _git(repo, "fetch", "--quiet", "origin", BRANCH)
                old = _git(repo, "rev-parse", "HEAD").stdout.strip()
                if f.returncode != 0:
                    r.update(result="error", detail="fetch: " + f.stderr.strip()[-200:])
                elif (m := _git(repo, "merge", "--ff-only", "--quiet", f"origin/{BRANCH}")).returncode != 0:
                    r.update(result="error", detail="no avanza sin merge (tiene commits locales): " + m.stderr.strip()[-200:])
                else:
                    new = _git(repo, "rev-parse", "HEAD").stdout.strip()
                    if new == old:
                        r.update(result="ok", detail="ya estaba al día")
                    else:
                        n = _git(repo, "rev-list", "--count", f"{old}..{new}").stdout.strip()
                        r.update(result="updated", detail=f"{n} commits")
                    if repo.name == API and db is not None:
                        done = db.get("roots:migrated") or old
                        if done != new:
                            res = _migrate_api(repo, done, new)
                            r["detail"] += ("; " if r["detail"] else "") + res
                            if res.startswith(("sin migraciones", "finnecto_dev migrada")):
                                db.set("roots:migrated", new)
                            else:
                                r["result"] = "error"
        except (OSError, subprocess.SubprocessError) as exc:
            r.update(result="error", detail=str(exc)[:200])
        r["at"] = datetime.now().isoformat(timespec="seconds")
        out.append(r)
    return out
