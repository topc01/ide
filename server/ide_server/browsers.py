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
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from ide_server.sessions_fs import SessionError, read_toml, write_toml

MCP_VERSION = "0.0.83"          # @playwright/mcp
PLAYWRIGHT_VERSION = "1.64.1"   # el CLI `playwright open` del login
# "local": localhost y tech.finnecto.com (ahí el usuario deja hacer cualquier cosa): las sesiones lo usan
# sin pedir permiso, también las `full`. El resto es REAL: pide permiso por acción y las `full` no lo tienen.
LOCAL = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\]|tech\.finnecto\.com)(:\d+)?(/|$)")


# siempre está (sin perfil ni cuenta): el navegador de las sesiones para probar en localhost. Es un Chrome
# aparte del del usuario: abre su propia ventana y nunca toca las de él (Claude in Chrome sí podía)
LOCAL_SERVER = "browser-local"


def base(root: Path) -> Path:
    return root / ".ide" / "browsers"


def _dir(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
        raise SessionError("bad_name", f"nombre de perfil inválido: {name!r} (minúsculas, números y guiones)")
    if f"browser-{name}" == LOCAL_SERVER:
        raise SessionError("bad_name", "`local` es el navegador fijo de las sesiones (sin cuenta): usa otro nombre")
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
    # `state.json` son las cookies de la cuenta (en prod, la sesión real): solo el usuario las lee
    base(root).mkdir(parents=True, exist_ok=True, mode=0o700)
    base(root).chmod(0o700)
    d.mkdir(mode=0o700)
    write_toml(d / "profile.toml", {"url": url, "note": note})
    fd = os.open(d / "state.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, b'{"cookies": [], "origins": []}\n')
    os.close(fd)
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
    rc = subprocess.run(argv).returncode
    if state.is_file():
        _keep_own_site(state, url)
        state.chmod(0o600)      # Playwright lo reescribe con los permisos por defecto
    return rc


def _keep_own_site(state: Path, url: str) -> None:
    """Deja en `state.json` solo la sesión del sitio exacto del perfil: fuera las cookies de otros
    dominios y las del dominio padre (`.finnecto.com` serviría en `acme.finnecto.com`, el prod de un
    cliente) y el localStorage de otros orígenes. Así un perfil sin permisos que navegue a otro sitio
    llega sin sesión. Las cookies no distinguen puerto: en local vale cualquier `localhost`."""
    host = urlparse(url).hostname or ""
    hosts = {"localhost", "127.0.0.1", "::1", "[::1]"} if LOCAL.match(url) and host != "tech.finnecto.com" else {host}
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    data["cookies"] = [c for c in data.get("cookies") or [] if str(c.get("domain") or "") in hosts]
    data["origins"] = [o for o in data.get("origins") or [] if urlparse(str(o.get("origin") or "")).hostname in hosts]
    state.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_mcp_config(root: Path, *, local_only: bool = False) -> Path:
    """`.ide/browsers/mcp.json`: `browser-local` (siempre) y un servidor por perfil (`mcp-local.json`: solo
    los locales, para las sesiones que no piden permiso, que no deben tener una cuenta REAL)."""
    f = base(root) / ("mcp-local.json" if local_only else "mcp.json")
    profiles = [p for p in list_profiles(root) if p["local"] or not local_only]
    base(root).mkdir(parents=True, exist_ok=True, mode=0o700)
    servers = {LOCAL_SERVER: {"command": "npx", "args": [
        "-y", f"@playwright/mcp@{MCP_VERSION}", "--isolated", "--browser", "chrome"]}}
    for p in profiles:
        servers[p["server"]] = {"command": "npx", "args": [
            "-y", f"@playwright/mcp@{MCP_VERSION}", "--isolated", "--browser", "chrome",
            "--storage-state", str(base(root) / p["name"] / "state.json")]}
    text = json.dumps({"mcpServers": servers}, indent=2) + "\n"
    if not f.is_file() or f.read_text(encoding="utf-8") != text:
        f.write_text(text, encoding="utf-8")
    return f


def allowed_tools(root: Path) -> list[str]:
    """`browser-local` y los servidores de los perfiles locales, enteros (`mcp__<servidor>`): no piden permiso."""
    return [f"mcp__{LOCAL_SERVER}"] + [f"mcp__{p['server']}" for p in list_profiles(root) if p["local"]]
