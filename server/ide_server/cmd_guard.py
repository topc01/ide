# server/ide_server/cmd_guard.py
"""Trampas conocidas de los comandos de una sesión: el hook PreToolUse (Bash) de `ide hook` frena el comando y
le dice a claude cuál es el correcto, en vez de que choque con el clasificador o con un permiso (y quede
esperando al usuario). Así esas reglas no hace falta tenerlas en el CLAUDE.md de las sesiones.

`advise(cmd)` → None (sigue) o (decisión, motivo): "deny" = no corre y claude lee el motivo; "ask" = se le
pregunta al usuario."""
from __future__ import annotations
import re
import shlex

from ide_server.test_guard import _HEREDOC

_OPS = {"|", "||", "&&", ";", "&", ";;", "(", ")", "|&"}

DB_ALONE = ("`ide db` va solo, como único comando de la línea (sin pipes, `;`, `&&`, `cd … &&` delante, loops ni "
            "`$(…)`): solo así lo cubre el permiso; combinado, el clasificador lo frena como «Production Reads». "
            "Filtra u ordena en el SQL; para procesar el resultado, guárdalo con `ide db <prod|staging> \"<SQL>\" "
            "--csv --out nombre.csv` (queda en attachments/db/) y léelo en otro comando. Una consulta por comando "
            "(prod y staging, en dos). Ver `ide db --help`.")
REVIEW_PUBLISH = ("Para publicar una review usa `ide review publish <pr> <review.json>` (el mismo JSON de POST "
                  ".../reviews: body, event REQUEST_CHANGES, commit_id, comments), no `gh api` ni `gh pr review`: ese "
                  "lo frena el clasificador; este lo cubre el permiso. Nunca una review solo de comentarios (COMMENT). "
                  "Ver `ide review --help`.")
REVIEW_REPLY = ("Para responder en un hilo de review usa `ide review reply <pr> <comment_id> \"texto\"` (o `--file -`), "
                "no `gh api` (en una sesión de ticket, sobre las PRs de tu desarrollo; `ide review inbox` lista los "
                "hilos con sus ids). Ver `ide review --help`.")
REVIEW_RESOLVE = "Para resolver un hilo usa `ide review resolve <PRRT_…>` (`--undo` lo reabre), no `gh api graphql`."
PUSH = ("Para subir la rama usa `ide push [<repo>]` (sin cd; `--force` = force-with-lease después de un rebase; "
        "`--branch <rama>` para otra rama local, p.ej. las de un stack). Ver `ide push --help`.")
TYPECHECK = ("El chequeo de tipos del proyecto entero (vue-tsc, `npm run type-check`, `npm run build`) va con "
             "`ide typecheck [<repo>]` (`--build` para el build): uno a la vez entre todas las sesiones y con tope de "
             "memoria. Dos a la vez llenaron la memoria de la Mac. Ver `ide typecheck --help`.")
TELEGRAM = ("La conexión de Telegram (su token, el chat y la clave del código de verificación) la maneja solo el usuario "
            "en su terminal: una sesión no la lee ni la cambia.")
DRAFT = ("Las PRs se abren en draft mientras están en desarrollo: agrega `--draft` (`gh pr create --draft …`). Pasa a "
         "lista para revisión cuando pides revisor (`ide review add-reviewer` lo hace solo).")

def _tokens(cmd: str) -> list[str]:
    cmd = _HEREDOC.sub("", cmd)          # el cuerpo de un heredoc es texto, no comandos
    cmd = re.sub(r"\d*>&\d+", " ", cmd)   # 2>&1 es una redirección, no un `&`
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
    lx.whitespace_split = True
    lx.commenters = ""
    try:
        return list(lx)
    except ValueError:                   # comillas sin cerrar: que siga y falle solo
        return cmd.split()


def _commands(toks: list[str]) -> list[list[str]]:
    out, cur = [], []
    for t in toks:
        if t in _OPS or set(t) <= set(";&|()") and t:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def _head(words: list[str]) -> list[str]:
    w = list(words)
    # VAR=… y palabras del shell delante (`do ide db …`, `then git push`, `time …`)
    while w and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w[0]) or w[0] in ("do", "then", "else", "time", "exec", "command", "!", "{")):
        w = w[1:]
    if w:
        w[0] = w[0].rsplit("/", 1)[-1]
    return w


def advise(cmd: str) -> tuple[str, str] | None:
    toks = _tokens(cmd)
    cmds = [_head(c) for c in _commands(toks)]
    cmds = [c for c in cmds if c]
    combined = len(cmds) > 1 or "$(" in cmd or "`" in _HEREDOC.sub("", cmd) or any(t in ("for", "while") for t in toks)
    for w in cmds:
        if w[:2] == ["ide", "db"] and combined:
            return "deny", DB_ALONE
        if (w[:2] == ["ide", "telegram"] and w[2:3] and w[2] in ("setup", "2fa")) or "ide-telegram" in cmd:
            return "deny", TELEGRAM
        runners = ("npm", "pnpm", "yarn", "bun")
        if any(x == "vue-tsc" or x.endswith("/vue-tsc") for x in w) \
                or (w[:1] and w[0] in runners and any(x in ("type-check", "build", "typecheck") for x in w[1:4])):
            return "deny", TYPECHECK
        if w[:2] == ["git", "push"] or (w[:1] == ["git"] and "push" in w[1:4] and w[1] in ("-C", "-c")):
            return "deny", PUSH
        if w[:2] == ["gh", "api"]:
            path = next((x for x in w[2:] if re.search(r"(^|/)(repos|graphql)", x) or x == "graphql"), "")
            # con campos (-f/-F/--input) gh api ya hace POST; o el método explícito
            writes = any(x.startswith(("-f", "-F", "--field", "--raw-field", "--input")) for x in w[2:]) \
                or bool(re.search(r"(-X|--method)[ =]*(POST|PUT|PATCH)", " ".join(w), re.I))
            if re.search(r"/pulls/\d+/reviews/?$", path) and writes:
                return "deny", REVIEW_PUBLISH
            if re.search(r"/pulls/(\d+/)?comments/\d+/replies/?$", path) and writes:
                return "deny", REVIEW_REPLY
            if path == "graphql" and re.search(r"(un)?resolveReviewThread", " ".join(w), re.I):
                return "deny", REVIEW_RESOLVE
        if w[:3] == ["gh", "pr", "review"] and any(x in ("--request-changes", "-r", "--comment", "-c") for x in w[3:]):
            return "deny", REVIEW_PUBLISH
        if w[:3] == ["gh", "pr", "create"] and not any(x in ("--draft", "-d") for x in w[3:]):
            return "deny", DRAFT
    return None
