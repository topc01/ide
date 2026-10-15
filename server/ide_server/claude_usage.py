# server/ide_server/claude_usage.py
"""Usage de Claude Code sin gastar tokens: ventanas de 5 h / semanal (endpoint OAuth que usa
`/usage`, con el token que Claude Code guarda en el llavero) y contexto de una sesión (leído de
su transcript `.jsonl`)."""
from __future__ import annotations
import asyncio
import getpass
import json
import logging
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from ide_server.supervisor import _transcripts

log = logging.getLogger(__name__)

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"
TAIL_BYTES = 512 * 1024
CONTEXT_DEFAULT, CONTEXT_1M = 200_000, 1_000_000


class UsageError(Exception):
    pass


def _keychain(*extra: str) -> str | None:
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, *extra, "-w"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def read_oauth_token(home: Path) -> str:
    """Token OAuth del login de Claude Code (`claudeAiOauth.accessToken`): llavero de macOS
    (puede haber varias entradas con ese servicio; la del usuario primero) o
    `~/.claude/.credentials.json`. Nunca otro token (p.ej. los de MCP en la misma entrada)."""
    f = home / ".claude" / ".credentials.json"
    sources = [lambda: _keychain("-a", getpass.getuser()), lambda: _keychain(),
               lambda: f.read_text(encoding="utf-8") if f.is_file() else None]
    seen: list[str] = []
    for src in sources:
        raw = src()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        token = (data.get("claudeAiOauth") or {}).get("accessToken") if isinstance(data, dict) else None
        if isinstance(token, str) and token:
            return token
        seen.append(",".join(sorted(data)) if isinstance(data, dict) else "?")
    raise UsageError("no encontré el login de Claude Code (claudeAiOauth) en el llavero "
                     f"'{KEYCHAIN_SERVICE}' ni en ~/.claude/.credentials.json"
                     + (f" (entradas vistas: {'; '.join(seen)})" if seen else ""))


def _window(d: dict | None) -> dict | None:
    if not isinstance(d, dict) or d.get("utilization") is None:
        return None
    return {"percent": float(d["utilization"]), "resetsAt": d.get("resets_at")}


def fetch_limits(token: str) -> dict:
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "ide-server"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
    return {"fiveHour": _window(data.get("five_hour")), "weekly": _window(data.get("seven_day"))}


class LimitsPoller:
    """Ventanas de 5 h / semanal cada `interval` s; ante 429 duplica la espera (tope 5 min)."""

    def __init__(self, *, interval: float = 15, home: Path | None = None,
                 fetch: Callable[[], dict] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._interval, self._home = interval, home or Path.home()
        self._fetch = fetch or (lambda: fetch_limits(read_oauth_token(self._home)))
        self._clock = clock
        self._delay = interval
        self.state: dict = {"fiveHour": None, "weekly": None, "error": None, "lastOk": None}

    async def poll_once(self) -> None:
        try:
            data = await asyncio.to_thread(self._fetch)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                self._delay = min(self._delay * 2, 300)
                msg = f"Anthropic limitó las consultas (429); reintento en {int(self._delay)}s"
            elif exc.code == 401:
                msg = "token de Claude Code vencido: abre `claude` para que lo renueve"
            else:
                msg = f"endpoint de usage respondió {exc.code}"
            self.state = {**self.state, "error": msg}
            return
        except Exception as exc:  # noqa: BLE001 — queda visible en la barra, nunca silencioso
            self.state = {**self.state, "error": str(exc) or type(exc).__name__}
            return
        self._delay = self._interval
        ts = datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(timespec="seconds")
        self.state = {**data, "error": None, "lastOk": ts}

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.poll_once()
            try:
                await asyncio.wait_for(stop.wait(), self._delay)
            except asyncio.TimeoutError:
                pass


def _uses_1m(home: Path) -> bool:
    f = home / ".claude" / "settings.json"
    try:
        return "[1m]" in str(json.loads(f.read_text(encoding="utf-8")).get("model", ""))
    except (OSError, ValueError):
        return False


def session_context(session_dir: Path, home: Path) -> dict | None:
    """Tokens en contexto según el último turno del transcript más reciente de la sesión."""
    files = _transcripts(session_dir, home)
    if not files:
        return None
    f = max(files, key=lambda p: p.stat().st_mtime)
    with f.open("rb") as fh:
        size = fh.seek(0, 2)
        fh.seek(max(0, size - TAIL_BYTES))
        lines = fh.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        if ev.get("type") != "assistant" or ev.get("isSidechain") or not isinstance(msg, dict):
            continue
        u = msg.get("usage") or {}
        used = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                 "cache_creation_input_tokens", "output_tokens"))
        if used == 0:
            continue
        window = CONTEXT_1M if (used > CONTEXT_DEFAULT or _uses_1m(home)) else CONTEXT_DEFAULT
        return {"used": used, "window": window, "model": msg.get("model")}
    return None
