# server/ide_server/staging_deploy.py
"""¿Ya llegó a staging (tech.finnecto.com) el merge de una PR? Para avisarle a la sesión que saque las
evidencias recién cuando el cambio está desplegado, no apenas se mergea.

Cada repo se despliega distinto (`[staging.repos.<repo>]` en config.toml; los de abajo son el default):
- `github_env`: la api se despliega en las horas pares (hora de Chile) y deja un deployment de GitHub en
  ese environment: está cuando el último deployment exitoso contiene el commit del merge.
- `amplify_app` (+ `amplify_branch`): el embed lo construye Amplify en cada push a develop (~7 min): está
  cuando el último build exitoso contiene el commit del merge (`aws amplify list-jobs`).
Si no se puede saber (repo sin fuente, gh/aws fallan), vale la regla de horario: el release de la
siguiente hora par (un merge a menos de `cutoff_min` de la hora par cuenta para la siguiente) más
`delay_min` de holgura."""
from __future__ import annotations
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from ide_server.config import load_workspace_config

DEFAULT_REPOS = {
    "finnecto-api": {"github_env": "staging"},
    "finnecto-embed": {"amplify_app": "dfvghz9wvit1m", "amplify_branch": "develop"},
}
GIVE_UP = timedelta(hours=12)   # sin verlo desplegado en este tiempo: se avisa igual, diciendo que no se confirmó


def config(root: Path) -> dict:
    cfg = load_workspace_config(root).get("staging", {})
    return {"delay_min": int(cfg.get("delay_min", 30)), "cutoff_min": int(cfg.get("cutoff_min", 10)),
            "repos": {**DEFAULT_REPOS, **(cfg.get("repos") or {})}}


def _run(argv: list[str], timeout: float = 60) -> str | None:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def merge_info(url: str) -> dict | None:
    """{sha, mergedAt} del merge de una PR (None si no está mergeada o gh falla)."""
    out = _run(["gh", "pr", "view", url, "--json", "mergeCommit,mergedAt,state"])
    if not out:
        return None
    d = json.loads(out)
    if d.get("state") != "MERGED" or not (d.get("mergeCommit") or {}).get("oid"):
        return None
    return {"sha": d["mergeCommit"]["oid"], "mergedAt": d.get("mergedAt")}


def _contains(full: str, deployed: str, sha: str) -> bool | None:
    """¿El commit desplegado incluye `sha`? (compare: `deployed` igual o adelante de `sha`)."""
    if deployed == sha:
        return True
    out = _run(["gh", "api", f"repos/{full}/compare/{sha}...{deployed}", "--jq", ".status"])
    if out is None:
        return None
    return out.strip() in ("ahead", "identical")


def _github_deployed(full: str, env: str) -> str | None:
    """El sha del último deployment exitoso del environment."""
    out = _run(["gh", "api", f"repos/{full}/deployments?environment={env}&per_page=10",
                "--jq", "[.[] | {id, sha}]"])
    if out is None:
        return None
    for dep in json.loads(out or "[]"):
        st = _run(["gh", "api", f"repos/{full}/deployments/{dep['id']}/statuses?per_page=1", "--jq", ".[0].state"])
        if st is not None and st.strip() == "success":
            return dep["sha"]
    return None


def _amplify_deployed(app: str, branch: str) -> str | None:
    """El commit del último build exitoso de Amplify en esa rama."""
    out = _run(["aws", "amplify", "list-jobs", "--app-id", app, "--branch-name", branch, "--max-items", "15",
                "--query", "jobSummaries[?status=='SUCCEED'].commitId | [0]", "--output", "text"])
    sha = ((out or "").strip().splitlines() or [""])[0].strip()   # con --max-items, aws agrega una línea del paginado
    return sha if sha and sha != "None" else None


def deployed(root: Path, repo: str, full: str, sha: str) -> bool | None:
    """True: ya está en staging; False: todavía no; None: este repo no tiene cómo saberlo (o falló)."""
    src = config(root)["repos"].get(repo) or {}
    if src.get("github_env"):
        dep = _github_deployed(full, src["github_env"])
    elif src.get("amplify_app"):
        dep = _amplify_deployed(src["amplify_app"], src.get("amplify_branch", "develop"))
    else:
        return None
    return None if dep is None else _contains(full, dep, sha)


def by_schedule(root: Path, merged_at: datetime) -> datetime:
    """Cuándo debería estar, por horario: la siguiente hora par (local) + holgura."""
    cfg = config(root)
    t = merged_at.astimezone() + timedelta(minutes=cfg["cutoff_min"])
    release = t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if release.hour % 2:
        release += timedelta(hours=1)
    return release + timedelta(minutes=cfg["delay_min"])


def check(root: Path, prs: list[dict], now: datetime | None = None) -> tuple[bool, str]:
    """¿Ya se puede avisar? (listo, nota). `prs`: [{url, repo, full, sha, mergedAt}]."""
    now = (now or datetime.now()).astimezone()
    pending = []
    for p in prs:
        if p.get("ok"):
            continue
        merged = datetime.fromisoformat(p["mergedAt"].replace("Z", "+00:00")) if p.get("mergedAt") else now
        state = deployed(root, p["repo"], p["full"], p["sha"])
        if state is True or (state is None and now >= by_schedule(root, merged)):
            p["ok"] = True
            continue
        if now - merged >= GIVE_UP:
            pending.append(p)
            continue
        return False, ""
    if pending:
        return True, ("(Ojo: no pude confirmar que " + ", ".join(f"{p['repo']}#{p['url'].rsplit('/', 1)[-1]}" for p in pending)
                      + " ya esté desplegado en staging; revísalo antes de probar.)")
    return True, ""
