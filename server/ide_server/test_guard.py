# server/ide_server/test_guard.py
"""Las sesiones no corren tests sin permiso del usuario: el hook PreToolUse (Bash) de `ide hook` le pide a
claude confirmar cualquier comando que corra tests (pytest, `make test`, vitest, jest, `npm test`, …), así
el usuario lo aprueba o rechaza en la terminal de la sesión."""
from __future__ import annotations
import re
import shlex

# envoltorios que se saltan para llegar al comando de verdad
_WRAPPERS = {"exec", "env", "time", "nice", "sudo", "command", "uv", "uvx", "poetry", "pipenv", "npx", "pnpx",
             "bunx", "timeout", "caffeinate"}
_RUNNERS = {"pytest", "py.test", "vitest", "jest", "mocha", "ava", "tap", "karma", "cypress"}
_PKG = {"npm", "pnpm", "yarn", "bun"}


def _segments(command: str) -> list[list[str]]:
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


ASK_REASON = ("El usuario pidió que ninguna sesión corra tests sin su permiso: apruébalo o recházalo aquí. "
              "(Sesión: si te lo rechaza, no lo intentes de otra forma; dile qué querías probar y por qué.)")
