# server/ide_server/browsers.py
"""Perfiles de navegador del workspace (`ide browser`): uno por cuenta (p.ej. `aprobador`, `prod-admin`),
para que una sesión tenga varias cuentas abiertas a la vez sin cerrar e iniciar sesión cada vez.

Cada perfil vive en `.ide/browsers/<nombre>/`: `profile.toml` (url, nota) y `state.json` (cookies y
localStorage; nace vacío y lo llena `ide browser login` cuando el usuario cierra la ventana). A cada claude se le
pasa `--mcp-config .ide/browsers/mcp.json`: un Playwright MCP por perfil (`browser-<nombre>`), en modo
`--isolated` con ese `state.json`, así que cada sesión abre su propio navegador con la cuenta ya
iniciada y dos sesiones pueden usar la misma cuenta a la vez. El MCP lee `state.json` al abrir el
navegador (no al arrancar claude): un login nuevo lo toma el próximo navegador que se abra."""
from __future__ import annotations
import json
import re
import shutil
import subprocess
from pathlib import Path
from ide_server.sessions_fs import SessionError, read_toml, write_toml

MCP_VERSION = "0.0.83"          # @playwright/mcp
PLAYWRIGHT_VERSION = "1.64.1"   # el CLI `playwright open` del login
LOCAL = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/|$)")


def base(root: Path) -> Path:
    return root / ".ide" / "browsers"


def _dir(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
        raise SessionError("bad_name", f"nombre de perfil inválido: {name!r} (minúsculas, números y guiones)")
    return base(root) / name


def list_profiles(root: Path) -> list[dict]:
    if not base(root).is_dir():
        return []
    out = []
    for d in sorted(base(root).iterdir()):
        if (d / "profile.toml").is_file():
            data = read_toml(d / "profile.toml")
            url = str(data.get("url") or "")
            out.append({"name": d.name, "url": url, "note": str(data.get("note") or ""),
                        "local": bool(LOCAL.match(url)), "logged": _logged(d / "state.json"),
                        "server": f"browser-{d.name}"})
    return out


def _logged(state: Path) -> bool:
    try:
        return bool(json.loads(state.read_text(encoding="utf-8")).get("cookies"))
    except (OSError, ValueError):
        return False


def new(root: Path, name: str, url: str, note: str = "") -> dict:
    d = _dir(root, name)
    if d.exists():
        raise SessionError("exists", f"ya existe el perfil {name}")
    if not re.match(r"^https?://", url):
        raise SessionError("bad_url", f"la url tiene que empezar con http:// o https:// ({url})")
    d.mkdir(parents=True)
    write_toml(d / "profile.toml", {"url": url, "note": note})
    (d / "state.json").write_text('{"cookies": [], "origins": []}\n', encoding="utf-8")
    write_mcp_config(root)
    return next(p for p in list_profiles(root) if p["name"] == name)


def remove(root: Path, name: str) -> None:
    d = _dir(root, name)
    if not d.is_dir():
        raise SessionError("unknown_profile", f"no hay perfil {name}")
    shutil.rmtree(d)
    write_mcp_config(root)


def login(root: Path, name: str) -> int:
    """Abre una ventana de Chrome con la cuenta del perfil (si ya tenía una, con esa); el usuario inicia
    sesión y la cierra: Playwright guarda las cookies en `state.json`."""
    d = _dir(root, name)
    if not (d / "profile.toml").is_file():
        raise SessionError("unknown_profile", f"no hay perfil {name} (créalo con `ide browser new`)")
    state = d / "state.json"
    url = str(read_toml(d / "profile.toml").get("url") or "")
    argv = ["npx", "-y", f"playwright@{PLAYWRIGHT_VERSION}", "open", "--channel", "chrome",
            *(["--load-storage", str(state)] if _logged(state) else []), "--save-storage", str(state), url]
    return subprocess.run(argv).returncode


def write_mcp_config(root: Path) -> Path | None:
    """`.ide/browsers/mcp.json` con un servidor por perfil; sin perfiles, lo borra."""
    f = base(root) / "mcp.json"
    profiles = list_profiles(root)
    if not profiles:
        f.unlink(missing_ok=True)
        return None
    servers = {}
    for p in profiles:
        servers[p["server"]] = {"command": "npx", "args": [
            "-y", f"@playwright/mcp@{MCP_VERSION}", "--isolated", "--browser", "chrome",
            "--storage-state", str(base(root) / p["name"] / "state.json")]}
    text = json.dumps({"mcpServers": servers}, indent=2) + "\n"
    if not f.is_file() or f.read_text(encoding="utf-8") != text:
        f.write_text(text, encoding="utf-8")
    return f
