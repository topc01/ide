# server/ide_server/migrations.py
"""Migraciones de Django de una PR contra la base actual (develop), leyendo los archivos (sin levantar
Django): cada migración nueva de una app tiene que ir después de la última de esa app en la base
(número mayor) y la primera tiene que depender de esa última; si no, al mergear quedan dos hojas y el
CI de todas las PRs falla. `plan` dice qué chocó y cómo renumerar; `renumber` lo aplica en un worktree
(renombra los archivos y corrige las dependencias) y deja un commit."""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

_MIG = re.compile(r"^(?:.*/)?(?P<app>[^/]+)/migrations/(?P<num>\d{4})_(?P<rest>[^/]+)\.py$")


def _git(wt: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])}: {out.stderr.strip()}")
    return out.stdout


def _parse(path: str) -> dict | None:
    m = _MIG.match(path)
    return {"path": path, "app": m["app"], "num": int(m["num"]), "name": f"{m['num']}_{m['rest']}"} if m else None


def _deps(text: str, app: str) -> list[str]:
    """Las dependencias de la migración en su misma app: ("app", "0345_x")."""
    return re.findall(rf"""\(\s*['"]{re.escape(app)}['"]\s*,\s*['"](\d{{4}}_[^'"]+)['"]\s*\)""", text)


def plan(wt: Path, base: str, head: str) -> dict:
    """{ok, apps: [{app, base_leaf, new: [...], problems: [...], renames: {viejo: nuevo}}]} comparando las
    migraciones que agrega `head` respecto de `base` (refs de git, p.ej. origin/develop y origin/rama)."""
    added = [p for p in (_parse(x) for x in _git(wt, "diff", "--name-only", "--diff-filter=A",
                                                  f"{base}...{head}").splitlines()) if p]
    if not added:
        return {"ok": True, "apps": []}
    tree = [p for p in (_parse(x) for x in _git(wt, "ls-tree", "-r", "--name-only", base).splitlines()) if p]
    apps = []
    for app_dir in sorted({str(Path(a["path"]).parent) for a in added}):
        new = sorted((a for a in added if str(Path(a["path"]).parent) == app_dir), key=lambda a: a["num"])
        app = new[0]["app"]
        have = sorted((t for t in tree if str(Path(t["path"]).parent) == app_dir), key=lambda t: t["num"])
        if not have:                                # app nueva: nada con qué chocar
            continue
        top = have[-1]["num"]
        leaves = [t["name"] for t in have if t["num"] == top]
        problems = []
        if len(leaves) > 1:
            problems.append(f"la base ya tiene dos hojas en {app} ({', '.join(leaves)}): arréglala primero")
        first_deps = _deps(_git(wt, "show", f"{head}:{new[0]['path']}"), app)
        if new[0]["num"] <= top:
            problems.append(f"{new[0]['name']} tiene un número ya tomado o anterior: la base llega a {leaves[0]}")
        if leaves[0] not in first_deps:
            problems.append(f"{new[0]['name']} depende de {', '.join(first_deps) or 'nada'}, no de la última de la base ({leaves[0]})")
        renames = {}
        if problems and len(leaves) == 1:
            for i, n in enumerate(new, start=1):
                renames[n["name"]] = f"{top + i:04d}_{n['name'][5:]}"
        apps.append({"app": app, "dir": app_dir, "base_leaf": leaves[0], "new": [n["name"] for n in new],
                     "first_deps": first_deps, "problems": problems, "renames": renames})
    return {"ok": not any(a["problems"] for a in apps), "apps": [a for a in apps if a["problems"]]}


def describe(p: dict) -> str:
    lines = []
    for a in p["apps"]:
        lines.append(f"{a['app']}: " + "; ".join(a["problems"]))
        if a["renames"]:
            lines.append("  renumerar: " + ", ".join(f"{o} → {n}" for o, n in a["renames"].items())
                         + f" (la primera pasa a depender de {a['base_leaf']})")
    return "\n".join(lines)


def renumber(wt: Path, p: dict) -> list[str]:
    """Aplica los renombres de `plan` en el worktree `wt` (que está en la rama de la PR): mueve los
    archivos, corrige las dependencias (la primera, a la hoja de la base; las demás, a los nombres
    nuevos; también en otras migraciones que las nombren) y deja un commit. Devuelve los archivos tocados."""
    touched = []
    for a in p["apps"]:
        if not a["renames"]:
            raise RuntimeError(f"{a['app']}: no se puede renumerar solo ({'; '.join(a['problems'])})")
        d = wt / a["dir"]
        for old, new in a["renames"].items():
            _git(wt, "mv", f"{a['dir']}/{old}.py", f"{a['dir']}/{new}.py")
        first_new = a["renames"][a["new"][0]]
        for f in sorted(d.glob("[0-9][0-9][0-9][0-9]_*.py")):
            text = f.read_text(encoding="utf-8")
            orig = text
            for old, new in a["renames"].items():
                text = re.sub(rf"(['\"]){re.escape(old)}(['\"])", rf"\g<1>{new}\g<2>", text)
            if f.stem == first_new:             # la primera: de la hoja vieja a la de la base
                for dep in a["first_deps"]:
                    if dep not in a["renames"]:
                        text = re.sub(rf"(\(\s*['\"]{re.escape(a['app'])}['\"]\s*,\s*['\"]){re.escape(dep)}(['\"])",
                                      rf"\g<1>{a['base_leaf']}\g<2>", text)
            if text != orig:
                f.write_text(text, encoding="utf-8")
                touched.append(str(f.relative_to(wt)))
        touched += [f"{a['dir']}/{n}.py" for n in a["renames"].values()]
    _git(wt, "add", "-A", *{str(Path(t).parent) for t in touched})
    names = ", ".join(n for a in p["apps"] for n in a["renames"].values())
    _git(wt, "commit", "-m", f"fix(migrations): renumera {names} sobre la base actual")
    return sorted(set(touched))
