# server/ide_server/test_guard.py
"""Las sesiones no corren tests en la Mac del usuario (19-11: se le llenaba la memoria): el hook PreToolUse (Bash)
de `ide hook` frena cualquier comando que corra tests (pytest, `make test`, vitest, jest, `npm test`, …). Los
tests se escriben y los corre el CI."""
from __future__ import annotations
import re
import shlex

# envoltorios que se saltan para llegar al comando de verdad
_WRAPPERS = {"exec", "env", "time", "nice", "sudo", "command", "uv", "uvx", "poetry", "pipenv", "npx", "pnpx",
             "bunx", "timeout", "caffeinate"}
_RUNNERS = {"pytest", "py.test", "vitest", "jest", "mocha", "ava", "tap", "karma", "cypress"}
_PKG = {"npm", "pnpm", "yarn", "bun"}


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?=\n|$)", re.S)


def _segments(command: str) -> list[list[str]]:
    # el cuerpo de un heredoc es texto (un body de PR, un script), no comandos: «make test» ahí no corre nada
    command = _HEREDOC.sub("", command)
    out = []
    for part in re.split(r"&&|\|\||[;|&\n(){}`]|\$\(", command):
        try:
            words = shlex.split(part, comments=True)
        except ValueError:
            words = part.split()
        if words:
            out.append(words)
    return out


def _strip(words: list[str]) -> list[str]:
    """Saca asignaciones de variables, envoltorios y `docker compose exec|run [flags] <servicio>`."""
    w = list(words)
    while w:
        head = w[0].rsplit("/", 1)[-1]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w[0]):
            w = w[1:]
        elif head in _WRAPPERS or (head == "run" and len(w) > 1):      # `uv run`, `poetry run`
            w = w[1:]
            while w and w[0].startswith("-"):
                w = w[1:]
                if w and head == "timeout" and re.fullmatch(r"[\d.]+[smhd]?", w[0]):
                    w = w[1:]
            if head == "timeout" and w and re.fullmatch(r"[\d.]+[smhd]?", w[0]):
                w = w[1:]
        elif head in ("docker", "docker-compose", "podman"):
            i = 1
            while i < len(w) and w[i] not in ("exec", "run"):
                i += 1
            if i >= len(w):
                return w
            i += 1
            while i < len(w) and w[i].startswith("-"):     # flags (los con valor más comunes)
                i += 2 if w[i] in ("-u", "--user", "-w", "--workdir", "-e", "--env", "--name") else 1
            w = w[i + 1:]                                   # salta el servicio
        elif head in _PKG and len(w) > 1 and w[1] in ("exec", "x", "dlx"):   # `npm exec vitest`, `pnpm dlx jest`
            w = w[2:]
            while w and (w[0].startswith("-")):
                w = w[1:]
        elif head in ("python", "python3") and len(w) > 2 and w[1] == "-m":
            w = w[2:]
        else:
            return w
    return w


def is_test_command(command: str) -> bool:
    for seg in _segments(command or ""):
        w = _strip(seg)
        if not w:
            continue
        head = w[0].rsplit("/", 1)[-1]
        rest = w[1:]
        if head in _RUNNERS:
            return True
        if head == "make" and any(re.fullmatch(r"test[\w-]*", a) for a in rest if not a.startswith("-")):
            return True
        if head in _PKG:
            args = [a for a in rest if not a.startswith("-")]
            if args[:1] == ["run"]:
                args = args[1:]
            if args and re.fullmatch(r"(test|tests|e2e|test:[\w:-]+)", args[0]):
                return True
        if head.endswith("manage.py") and rest[:1] == ["test"]:
            return True
        if head in ("python", "python3") and rest[:1] and rest[0].endswith("manage.py") and rest[1:2] == ["test"]:
            return True
        if head == "ide" and rest[:2] == ["script", "test"]:
            return True
        if head == "go" and rest[:1] == ["test"] or head == "cargo" and rest[:1] == ["test"]:
            return True
    return False


_VALUE_OPTS = {"-t", "--testNamePattern", "--reporter", "-c", "--config", "--project", "--root", "-r", "--dir",
               "--maxWorkers", "--minWorkers", "--pool", "--shard", "--environment", "--outputFile", "-k", "-m", "-n",
               "-p", "--maxfail", "--tb", "--ds", "--durations", "-o", "--rootdir", "--testPathPattern"}


def full_suite(command: str) -> bool:
    """Si el comando de tests corre la suite entera: sin ruta ni archivo (vitest, jest, pytest, `make test` sin
    argumentos, `make test-fresh`), o con un filtro de nombre vacío (`-t ""`, `-k ""`), que parece puntual y no lo es."""
    for seg in _segments(command or ""):
        w = _strip(seg)
        if not w:
            continue
        head = w[0].rsplit("/", 1)[-1]
        rest = w[1:]
        if head == "make":
            targets = [a for a in rest if not a.startswith("-")]
            if any(re.fullmatch(r"test[\w-]*", a) for a in targets):
                if any(a in ("test-fresh", "test-ci") for a in targets):
                    return True
                return not [a for a in targets[1:] if "=" not in a]
            continue
        if head in _PKG:
            args = [a for a in rest if not a.startswith("-")]
            if args[:1] == ["run"]:
                args = args[1:]
            if args and re.fullmatch(r"(test|tests|e2e|test:[\w:-]+)", args[0]):
                return len(args) < 2
            continue
        if head not in _RUNNERS:
            continue
        pos, empty_filter, i = [], False, 0
        while i < len(rest):
            a = rest[i]
            if a in ("run", "watch", "related") and not pos and head == "vitest":
                i += 1
                continue
            if a in _VALUE_OPTS:
                val = rest[i + 1] if i + 1 < len(rest) else ""
                if a in ("-t", "--testNamePattern", "-k") and not val.strip():
                    empty_filter = True
                i += 2
                continue
            if a.startswith("-"):
                if re.match(r"^(-t|--testNamePattern|-k)=$", a):
                    empty_filter = True
                i += 1
                continue
            pos.append(a)
            i += 1
        if empty_filter or not pos or all(p.rstrip("/") in ("src", "tests", "src/__tests__", ".") or p.rstrip("/").endswith("__tests__") for p in pos):
            return True
    return False


ASK_REASON = ("El usuario pidió que ninguna sesión corra tests sin su permiso: apruébalo o recházalo aquí. "
              "(Sesión: si te lo rechaza, no lo intentes de otra forma; dile qué querías probar y por qué.)")
ASK_FULL = ("⚠ SUITE ENTERA: este comando corre todos los tests (sin archivo, o con un filtro de nombre vacío como "
            "`-t \"\"`), no uno puntual. ")


DENY_REASON = ("El usuario pidió que no se corra NINGÚN test en su Mac (se le llena la memoria): ni puntuales ni la "
               "suite, ni por otro comando, script o subagente. Escribe o ajusta el test y súbelo: lo corre el CI. "
               "Si necesitas confirmar algo antes, léelo en el código o pruébalo en el navegador.")
