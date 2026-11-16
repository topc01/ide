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
import time
from pathlib import Path
from urllib.parse import urlparse
from ide_server.sessions_fs import SessionError, read_toml, write_toml

MCP_VERSION = "0.0.83"          # @playwright/mcp
PLAYWRIGHT_VERSION = "1.64.1"   # el CLI `playwright open` del login
# "local": localhost (con sus subdominios: el embed elige la sociedad por ellos, p.ej. demo-cl.localhost)
# y tech.finnecto.com (ahí el usuario deja hacer cualquier cosa): las sesiones lo usan sin pedir permiso,
# también las `full`. El resto es REAL: pide permiso por acción y las `full` no lo tienen.
LOCAL = re.compile(r"^https?://(([a-z0-9-]+\.)*localhost|127\.0\.0\.1|\[::1\]|tech\.finnecto\.com)(:\d+)?(/|$)", re.I)


# siempre está (sin perfil ni cuenta): el navegador de las sesiones para probar en localhost. Es un Chrome
# aparte del del usuario: abre su propia ventana y nunca toca las de él (Claude in Chrome sí podía)
LOCAL_SERVER = "browser-local"
# la sesión de localhost que comparte browser-local (`ide browser login local`): el embed guarda el token
# en localStorage, que es por origen (puerto); un script la copia en cada puerto local que se abra
SHARED = "_local"


def base(root: Path) -> Path:
    return root / ".ide" / "browsers"


def _dir(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
        raise SessionError("bad_name", f"nombre de perfil inválido: {name!r} (minúsculas, números y guiones)")
    if f"browser-{name}" == LOCAL_SERVER:
        raise SessionError("bad_name", "`local` es el navegador fijo de las sesiones (su sesión de localhost se inicia "
                                       "con `ide browser login local --url …`): usa otro nombre")
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
    """Tiene una sesión guardada: cookies, o localStorage (donde el embed guarda el token de Cognito)."""
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data.get("cookies") or any(o.get("localStorage") for o in data.get("origins") or []))


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


def shared_state(root: Path) -> Path:
    return base(root) / SHARED / "state.json"


def login(root: Path, name: str, url: str | None = None) -> int:
    """Abre una ventana de Chrome con la cuenta del perfil (si ya tenía una, con esa); el usuario inicia
    sesión y la cierra: Playwright guarda las cookies en `state.json`. `local`: la sesión de localhost que
    usa browser-local en cualquier puerto (`url`: dónde iniciarla; la primera vez es obligatoria)."""
    if name == "local":
        d = base(root) / SHARED
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        saved = (d / "url").read_text(encoding="utf-8").strip() if (d / "url").is_file() else ""
        url = url or saved
        if not url or not LOCAL.match(url) or (urlparse(url).hostname or "") == "tech.finnecto.com":
            raise SessionError("bad_url", "`ide browser login local --url http://localhost:<puerto>`: la url de un "
                                          "front local corriendo (mira `ide server ls`)")
        (d / "url").write_text(url + "\n", encoding="utf-8")
    else:
        d = _dir(root, name)
        if not (d / "profile.toml").is_file():
            raise SessionError("unknown_profile", f"no hay perfil {name} (créalo con `ide browser new`)")
        url = str(read_toml(d / "profile.toml").get("url") or "")
    state = d / "state.json"
    argv = ["npx", "-y", f"playwright@{PLAYWRIGHT_VERSION}", "open", "--channel", "chrome",
            *(["--load-storage", str(state)] if _logged(state) else []), "--save-storage", str(state), url]
    rc = subprocess.run(argv).returncode
    if state.is_file():
        _keep_own_site(state, url)
        state.chmod(0o600)      # Playwright lo reescribe con los permisos por defecto
        if name != "local":
            write_cookies_txt(state, d / "cookies.txt")
    write_mcp_config(root)
    return rc


def write_cookies_txt(state: Path, out: Path) -> None:
    """Las cookies del perfil en formato Netscape (`cookies.txt`, solo las de su sitio: ver _keep_own_site), para
    herramientas de línea de comandos (p.ej. `gallery-dl --cookies`): así no leen las de tu Chrome, que pasan por
    el llavero de macOS (te pide la contraseña) y traen todas tus cuentas."""
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    lines = ["# Netscape HTTP Cookie File", "# generado por `ide browser login` (solo el sitio del perfil)"]
    for c in data.get("cookies") or []:
        dom = str(c.get("domain") or "")
        exp = int(c["expires"]) if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0 else 0
        lines.append("\t".join([dom, "TRUE" if dom.startswith(".") else "FALSE", str(c.get("path") or "/"),
                                "TRUE" if c.get("secure") else "FALSE", str(exp), str(c.get("name") or ""),
                                str(c.get("value") or "")]))
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, ("\n".join(lines) + "\n").encode())
    os.close(fd)


def _keep_own_site(state: Path, url: str) -> None:
    """Deja en `state.json` solo la sesión del sitio exacto del perfil: fuera las cookies de otros
    dominios y las del dominio padre (`.finnecto.com` serviría en `acme.finnecto.com`, el prod de un
    cliente) y el localStorage de otros orígenes. Así un perfil sin permisos que navegue a otro sitio
    llega sin sesión. Las cookies no distinguen puerto: en local vale cualquier `localhost` (y sus
    subdominios, p.ej. `demo-cl.localhost`)."""
    host = (urlparse(url).hostname or "").lower()
    local = bool(LOCAL.match(url)) and host != "tech.finnecto.com"

    def ok(h: str) -> bool:
        h = h.lstrip(".").lower()
        if local:
            return h in ("localhost", "127.0.0.1", "::1", "[::1]") or h.endswith(".localhost")
        return h == host
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    # la cookie del dominio padre trae el punto adelante (`.finnecto.com`): solo vale el host exacto, sin punto
    data["cookies"] = [c for c in data.get("cookies") or []
                       if ok(str(c.get("domain") or "")) and (local or str(c.get("domain") or "") == host)]
    data["origins"] = [o for o in data.get("origins") or [] if ok(urlparse(str(o.get("origin") or "")).hostname or "")]
    state.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _shared_local(root: Path) -> tuple[Path, Path]:
    """La sesión local compartida para browser-local: (storage con sus cookies —en localhost valen para
    cualquier puerto—, script que en cada página de localhost —o un subdominio suyo— copia su localStorage —que es por origen, y
    ahí guarda el embed el token de Cognito— si esa página no tiene ya el suyo). Los dos existen siempre
    (vacíos sin login): el MCP los lee al abrir el navegador, así un login nuevo sirve sin relanzar."""
    src = shared_state(root)
    src.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for f in (src, src.parent / "url"):         # la sesión del usuario: solo él la lee
        if f.is_file():
            f.chmod(0o600)
    data = json.loads(src.read_text(encoding="utf-8")) if _logged(src) else {"cookies": [], "origins": []}
    store = {i["name"]: i["value"] for o in data.get("origins") or [] for i in o.get("localStorage") or []}
    script = ("(() => { if (!/(^|\\.)localhost$|^127\\.0\\.0\\.1$/.test(location.hostname)) return;\n"
              f"  const items = {json.dumps(store)};\n"
              "  try { for (const [k, v] of Object.entries(items)) if (localStorage.getItem(k) === null) localStorage.setItem(k, v); }"
              " catch (e) {}\n})();\n")
    outs = []
    for name, text in (("cookies.json", json.dumps({"cookies": data.get("cookies") or [], "origins": []}) + "\n"),
                       ("login.js", script)):
        out = src.parent / name
        if not out.is_file() or out.read_text(encoding="utf-8") != text:
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.write(fd, text.encode())
            os.close(fd)
        outs.append(out)
    (src.parent / "expanded.json").unlink(missing_ok=True)
    return outs[0], outs[1]


def _specs(root: Path) -> dict[str, list[str]]:
    """Por servidor (`browser-local`, `browser-<perfil>`): los argumentos de su Playwright MCP."""
    cookies, script = _shared_local(root)
    out = {LOCAL_SERVER: ["--storage-state", str(cookies), "--init-script", str(script)]}
    for p in list_profiles(root):
        if p["local"]:      # los de cuentas REAL no se comparten por un puerto sin clave (ver write_mcp_config)
            out[p["server"]] = ["--storage-state", str(base(root) / p["name"] / "state.json")]
    return out


def _ports(root: Path, names) -> dict[str, int]:
    """Un puerto fijo por servidor (`.ide/browsers/ports.json`): las sesiones que ya corren lo siguen usando."""
    f = base(root) / "ports.json"
    try:
        ports = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ports = {}
    for n in names:
        if n not in ports:
            ports[n] = max([PORT0 - 1, *ports.values()]) + 1
    f.write_text(json.dumps(ports, indent=2) + "\n", encoding="utf-8")
    return ports


PORT0 = 18920


def _listeners(port: int) -> set[int]:
    """Los pids que escuchan en ese puerto (lsof)."""
    out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True).stdout
    return {int(x) for x in out.split() if x.isdigit()}


def _pgid(pid: int) -> int | None:
    out = subprocess.run(["ps", "-o", "pgid=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else None


def _foreign(port: int, ours: int | None) -> bool:
    """El puerto lo tiene otro proceso (no el servidor que levantó el IDE, que es líder de su grupo): las
    sesiones le hablarían a él como si fuera el navegador."""
    return any(_pgid(pid) != ours for pid in _listeners(port)) if ours else bool(_listeners(port))


def write_mcp_config(root: Path, *, local_only: bool = False) -> Path:
    """`.ide/browsers/mcp.json`: `browser-local` (siempre) y uno por perfil (`mcp-local.json`: solo los locales,
    para las sesiones que no piden permiso, que no deben tener una cuenta REAL). Cada uno es un servidor
    Playwright MCP **compartido** entre todas las sesiones (`BrowserServers`; por HTTP, cada sesión con su
    propio navegador aislado): antes cada sesión levantaba los suyos (~150 MB por perfil y sesión)."""
    f = base(root) / ("mcp-local.json" if local_only else "mcp.json")
    base(root).mkdir(parents=True, exist_ok=True, mode=0o700)
    specs = _specs(root)
    ports = _ports(root, specs)
    bs = BrowserServers.of(root)
    bs.ensure()
    ports = _ports(root, specs)                 # (ensure pudo mover alguno a otro puerto)
    servers = {n: {"type": "http", "url": f"http://localhost:{ports[n]}/mcp"}
               for n in specs if not _foreign(ports[n], bs.pid(n))}
    if not local_only:
        # una cuenta REAL (prod) no va en un servidor compartido (cualquier proceso local podría usarla): un
        # Playwright MCP propio por sesión, solo en las que pueden (nunca las `full`)
        for p in list_profiles(root):
            if not p["local"]:
                servers[p["server"]] = {"command": "npx", "args": [
                    "-y", f"@playwright/mcp@{MCP_VERSION}", "--isolated", "--browser", "chrome",
                    "--storage-state", str(base(root) / p["name"] / "state.json")]}
    text = json.dumps({"mcpServers": servers}, indent=2) + "\n"
    if not f.is_file() or f.read_text(encoding="utf-8") != text:
        f.write_text(text, encoding="utf-8")
    return f


class BrowserServers:
    """Los servidores Playwright MCP compartidos, uno por perfil, como procesos aparte (siguen vivos si el
    IDE se reinicia: se reconocen por su pid en `.ide/browsers/servers/<nombre>.json`). `ensure` levanta los
    que faltan, reinicia los que cambiaron de argumentos y para los de perfiles que ya no están. El
    navegador de cada uno se abre recién cuando una sesión lo usa."""
    _by_root: dict[str, "BrowserServers"] = {}

    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def of(cls, root: Path) -> "BrowserServers":
        return cls._by_root.setdefault(str(root.resolve()), cls(root))

    def _dir(self) -> Path:
        d = base(self.root) / "servers"
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        return d

    @staticmethod
    def _alive(pid: int | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
        return "playwright/mcp" in out

    def pid(self, name: str) -> int | None:
        try:
            return json.loads((self._dir() / f"{name}.json").read_text(encoding="utf-8")).get("pid")
        except (OSError, ValueError):
            return None

    def ensure(self) -> None:
        import signal
        specs = _specs(self.root)
        ports = _ports(self.root, specs)
        for f in self._dir().glob("*.json"):            # perfiles que ya no están
            if f.stem not in specs:
                info = json.loads(f.read_text(encoding="utf-8"))
                if self._alive(info.get("pid")):
                    os.killpg(info["pid"], signal.SIGTERM)
                f.unlink()
        for name, args in specs.items():
            f = self._dir() / f"{name}.json"
            want = [*args, "--port", str(ports[name])]
            try:
                info = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                info = {}
            if self._alive(info.get("pid")):
                if info.get("args") == want:
                    continue
                os.killpg(info["pid"], signal.SIGTERM)  # cambió (p.ej. otro archivo de sesión): se relanza
                time.sleep(1)
            if _listeners(ports[name]):                 # el puerto lo tiene otro proceso: se usa otro
                pmap = json.loads((base(self.root) / "ports.json").read_text(encoding="utf-8"))
                pmap[name] = max(pmap.values()) + 1
                (base(self.root) / "ports.json").write_text(json.dumps(pmap, indent=2) + "\n", encoding="utf-8")
                ports[name] = pmap[name]
                want = [*args, "--port", str(ports[name])]
            log = open(self._dir() / f"{name}.log", "ab")
            proc = subprocess.Popen(["npx", "-y", f"@playwright/mcp@{MCP_VERSION}", "--isolated", "--browser", "chrome", *want],
                                    stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
            f.write_text(json.dumps({"pid": proc.pid, "args": want}) + "\n", encoding="utf-8")


def allowed_tools(root: Path) -> list[str]:
    """`browser-local` y los servidores de los perfiles locales, enteros (`mcp__<servidor>`): no piden permiso."""
    return [f"mcp__{LOCAL_SERVER}"] + [f"mcp__{p['server']}" for p in list_profiles(root) if p["local"]]
