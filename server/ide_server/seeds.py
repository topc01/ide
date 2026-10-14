# server/ide_server/seeds.py
"""Contenido sembrado por `ide init` (solo si no existe; el usuario lo edita)."""
from __future__ import annotations

CONFIG_TOML = """\
name = "{name}"

[sessions]
default_permissions = "analyze"   # analyze | full | default
# max_running = 5                 # tope de `claude` corriendo a la vez (omitido = sin tope)
claude_command = "claude"

[reviews]
poll_interval = 300               # segundos; 0 = sin polling de PRs

[ui]
modules = ["sessions", "terminal"]
"""


def claude_md(repos: list[str]) -> str:
    lines = "\n".join(f"- `{r}`: (describí qué hace este repo)" for r in repos) or "- (sin repos)"
    return f"""\
# Workspace

Estás en una sesión del IDE (`.ide/sessions/<id>/`). Los repos del workspace:

{lines}

## Herramientas del IDE (por Bash)

- `ide repo add <repo> [--branch b]`: agrega el repo a tu sesión como worktree (corre su `setup`).
- `ide repo rm <repo>`: lo quita.
- `ide script <nombre> [<repo>]`: corre un script del repo (`run`, `test`, …).
- `ide session ls [--json]`: lista sesiones y su estado.
- `ide session new --if-missing --notion <url> --template ticket --vars-file -` (JSON por stdin):
  (solo la principal) lanza una sesión por ticket.
- `ide session new --review <pr-url>`: (solo la principal) lanza una revisión de PR.

## Convención de estado

Las sesiones de ticket mantienen `TICKET.md` (frontmatter `status`:
analyzing | blocked | questions | ready | in-progress | done). Las de revisión, `REVIEW.md`
(reviewing | commented | approved | changes-requested). Solo cambiá `status` y el cuerpo.
"""


TEMPLATE_MAIN = """\
Sos la sesión principal de este workspace.

1. Tickets: consultá mi base de tickets en Notion: <URL o collection:// de la base>
   (asignados a mí; Status en <estados que entran, ej. Backlog, To Do, In progress>).
2. PRs: `gh search prs --review-requested=@me --state=open --json url,title,repository`.
3. Probá cada uno con `--dry-run` y mostrame una tabla:
   id | título | status | ¿ya tiene sesión? | acción. Esperá mi OK.
4. Con OK, por cada ticket:
   `ide session new --if-missing --notion <url del ticket> --template ticket --vars-file -`
   pasando por stdin `{"title": "…"}` (JSON: así los títulos no se rompen en el shell).
   Por cada PR: `ide session new --if-missing --review <url>`.
5. Resumí lo lanzado. Estado general: leé `../*/TICKET.md` y `../*/REVIEW.md`.
"""
TEMPLATE_TICKET = """\
Sos la sesión del ticket {{id}}: "{{title}}" ({{notion_url}}).

Tu trabajo AHORA es analizar, no implementar:
1. Leé ../CLAUDE.md (mapa de repos) y el ticket en Notion ({{notion_url}}).
2. Determiná scope y qué repos toca. Por cada uno: `ide repo add <repo>`.
3. Escribí TICKET.md: Scope, Repos, Plan, Bloqueantes, Dudas.
   Cambiá `status` a blocked | questions | ready.
4. Pará y esperá instrucciones.
"""

TEMPLATE_REVIEW = """\
Sos la revisión del PR {{pr_url}} ("{{title}}", de {{author}}) en el repo {{repo}}.
El worktree `{{repo}}/` está en el head del PR (detached).

1. Revisá el diff contra la base (`gh pr diff {{pr_url}}`, y leé el código alrededor).
2. Escribí REVIEW.md con hallazgos por severidad (bloqueante / importante / menor / nit).
3. Cambiá `status` a commented | approved | changes-requested según tu veredicto.
4. NO publiques nada en GitHub sin que te lo pida.
"""

_READ_ONLY_BASH = [
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(find:*)",
    "Bash(rg:*)", "Bash(grep:*)",
    "Bash(git log:*)", "Bash(git diff:*)", "Bash(git show:*)", "Bash(git status:*)",
    "Bash(git branch:*)", "Bash(git remote -v)",
]

PERM_ANALYZE = {"permissions": {
    "allow": [
        "Read", "Grep", "Glob", *_READ_ONLY_BASH,
        "Bash(ide repo add:*)", "Bash(ide script:*)", "Bash(ide session ls:*)",
        "Bash(gh pr view:*)", "Bash(gh pr diff:*)", "Bash(gh search prs:*)",
        "Edit(**/TICKET.md)", "Edit(**/REVIEW.md)",
        "mcp__claude_ai_Notion__notion-fetch", "mcp__claude_ai_Notion__notion-search",
        "mcp__claude_ai_Notion__notion-query-data-sources",
    ],
    "deny": ["Bash(git diff --output:*)", "Bash(git log --output:*)"],
}}

# La principal = analyze + despachar sesiones (el server igual le niega `full`).
PERM_MAIN = {"permissions": {
    "allow": [*PERM_ANALYZE["permissions"]["allow"], "Bash(ide session new:*)"],
    "deny": list(PERM_ANALYZE["permissions"]["deny"]),
}}

PERM_FULL = {"permissions": {"defaultMode": "bypassPermissions"}}
