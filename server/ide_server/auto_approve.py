# server/ide_server/auto_approve.py
"""Aprobación con plazo: cuando la sesión de revisión registra «aprobar» (`ide review verdict <pr> approve`), el IDE
decide si la PR es de **bajo riesgo**. Si lo es, la aprueba solo después de `[reviews] auto_approve_minutes` (5) salvo
que la frenes (barra inferior o Telegram); si no, te avisa por Telegram con un botón «Aprobar» (con el código de 6
dígitos). «Pedir cambios» nunca pasa por acá.

Bajo riesgo = todo esto:
- es una **re-revisión**: ya le habías pedido cambios (tu última review en la PR es CHANGES_REQUESTED);
- **menos de `auto_approve_max_lines`** (300) líneas cambiadas (sumadas y borradas);
- no toca **migraciones, infraestructura, permisos, pagos ni dependencias** (rutas de SENSITIVE);
- la sesión **no dejó dudas** (`ide review verdict … --doubt "…"` la deja esperando tu click)."""
from __future__ import annotations
import json
import re
import subprocess

SENSITIVE = re.compile(
    r"(^|/)migrations?/|(^|/)(terraform|infra|infrastructure|\.github|helm|k8s|deploy|ops)/|\.tf$|(^|/)Dockerfile|"
    r"docker-compose|(^|/)(settings|permissions?|auth|authentication|security)(\.py|/)|permission|"
    r"pay(ment)?s?|pago|billing|stripe|transbank|webpay|(^|/)(requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|"
    r"package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|uv\.lock)$", re.I)


def pr_facts(url: str) -> dict:
    r = subprocess.run(["gh", "pr", "view", url, "--json", "files,changedFiles,additions,deletions,headRefOid,state,reviews,author,title"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-200:] or "gh pr view falló")
    return json.loads(r.stdout)


def classify(facts: dict, me: str | None, *, max_lines: int, doubt: str | None = None) -> tuple[bool, list[str]]:
    """(bajo riesgo, por qué no). Sin `me` no se sabe si es una re-revisión: no es bajo riesgo."""
    why: list[str] = []
    mine = [r for r in facts.get("reviews") or [] if (r.get("author") or {}).get("login") == me
            and r.get("state") in ("APPROVED", "CHANGES_REQUESTED")]
    if not me or not mine or mine[-1].get("state") != "CHANGES_REQUESTED":
        why.append("no es una re-revisión de cambios que pediste")
    lines = int(facts.get("additions") or 0) + int(facts.get("deletions") or 0)
    if lines >= max_lines:
        why.append(f"cambia {lines} líneas (el tope es {max_lines})")
    files = facts.get("files") or []
    if int(facts.get("changedFiles") or 0) != len(files):     # gh lista hasta 100: sin la lista entera, no se sabe
        why.append(f"no pude ver todos sus archivos ({len(files)} de {facts.get('changedFiles')})")
    touchy = sorted({f["path"] for f in facts.get("files") or [] if SENSITIVE.search(f.get("path") or "")})
    if touchy:
        why.append("toca " + ", ".join(touchy[:4]) + (f" y {len(touchy) - 4} más" if len(touchy) > 4 else ""))
    if doubt:
        why.append(f"la sesión dejó una duda: {doubt[:200]}")
    return not why, why
