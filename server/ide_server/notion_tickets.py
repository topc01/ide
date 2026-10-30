# server/ide_server/notion_tickets.py
"""El ticket de Notion de cada desarrollo: el IDE lee su Status (con caché) y lo mueve a «Live Staging»
cuando se mergea la última PR abierta. Usa una integración interna de Notion (token en el llavero,
`ide notion token`) con acceso a la base Desarrollo.

En la base (`kv`): `notion:<page id>` = {status, title, at, error} (caché); `devtickets:<sid>` = las URLs
de los tickets de pendientes que la sesión creó para lo que quedó fuera."""
from __future__ import annotations
import asyncio
import json
import logging
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from ide_server.db import Db
from ide_server.sessions_fs import SessionError

log = logging.getLogger(__name__)
SERVICE = "ide-notion"
API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
TTL = 10 * 60                      # cada cuánto se vuelve a leer el Status de un ticket
LIVE_STAGING = "Live Staging"
_ID_RE = re.compile(r"([0-9a-f]{32})(?:[?#/]|$)")


def check_url(url: str) -> str:
    """Un link de Notion de verdad (https, a un dominio de Notion, sin caracteres de control): la card lo abre."""
    from urllib.parse import urlparse
    url = str(url or "").strip()
    host = (urlparse(url).hostname or "").rstrip(".").lower()
    if any(ord(c) < 32 for c in url) or urlparse(url).scheme != "https" or not (
            host in ("notion.so", "www.notion.so", "app.notion.com", "notion.com", "www.notion.com")
            or host.endswith(".notion.site")):
        raise SessionError("bad_notion_url", f"tiene que ser un link https de Notion: {url[:120]!r}")
    page_id(url)
    return url


def page_id(url: str) -> str:
    """El id de la página: los últimos 32 hex del último tramo de la ruta (no del `?v=…`, que es la vista)."""
    from urllib.parse import urlparse
    raw = str(url or "").strip()
    last = (urlparse(raw).path.rstrip("/").rsplit("/", 1)[-1] if "://" in raw else raw).lower().replace("-", "")
    m = re.search(r"([0-9a-f]{32})$", last)
    if not m:
        raise SessionError("bad_notion_url", f"no encuentro el page id en la URL de Notion: {url!r}")
    return m.group(1)


def get_token() -> str | None:
    import os
    if os.environ.get("NOTION_TOKEN"):
        return os.environ["NOTION_TOKEN"]
    if sys.platform != "darwin":
        return None
    out = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", "integration", "-w"],
                         capture_output=True, text=True)
    return out.stdout.strip() or None if out.returncode == 0 else None


def set_token(token: str) -> None:
    """Al llavero por stdin (`security -i`): como argumento quedaría a la vista en `ps`."""
    if not re.fullmatch(r"(secret_|ntn_)[A-Za-z0-9]{20,80}", token):
        raise SessionError("bad_request", "eso no parece un token de integración de Notion (empieza con ntn_ o secret_)")
    out = subprocess.run(["security", "-i"], input=f'add-generic-password -U -s {SERVICE} -a integration -w "{token}"\n',
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SessionError("keychain", f"no pude guardar el token en el llavero: {out.stderr.strip()}")


def _call(method: str, path: str, body: dict | None = None) -> dict:
    token = get_token()
    if not token:
        raise SessionError("no_notion", "falta el token de Notion: `ide notion token`")
    req = urllib.request.Request(f"{API}{path}", method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}", "Notion-Version": VERSION,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", "replace")[:300]
        if exc.code in (401, 403, 404):
            raise SessionError("notion_access", f"Notion respondió {exc.code}: ¿la integración tiene acceso a la base "
                                                f"Desarrollo? ({msg})")
        raise SessionError("notion_failed", f"Notion respondió {exc.code}: {msg}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SessionError("notion_failed", f"no pude hablar con Notion: {exc}")


def _status_prop(page: dict) -> tuple[str | None, str | None, str | None]:
    """(nombre de la propiedad, tipo `status`|`select`, valor) del Status del ticket."""
    for name, prop in (page.get("properties") or {}).items():
        if name.lower() == "status" and prop.get("type") in ("status", "select"):
            val = prop.get(prop["type"]) or {}
            return name, prop["type"], val.get("name")
    return None, None, None


def _title(page: dict) -> str | None:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title") or []) or None
    return None


def read(db: Db, url: str, *, fresh: bool = False) -> dict:
    """{status, title, at, error} del ticket (de la caché si tiene menos de TTL)."""
    pid = page_id(url)
    cached = db.get(f"notion:{pid}") or {}
    if not fresh and cached.get("ts") and time.time() - cached["ts"] < TTL:
        return cached
    try:
        page = _call("GET", f"/pages/{pid}")
        _, _, status = _status_prop(page)
        info = {"status": status, "title": _title(page), "ts": time.time(),
                "at": datetime.now().isoformat(timespec="minutes"), "error": None}
    except SessionError as exc:
        info = {**cached, "ts": time.time(), "error": str(exc)}
    db.set(f"notion:{pid}", info)
    return info


def set_status(db: Db, url: str, status: str) -> dict:
    pid = page_id(url)
    page = _call("GET", f"/pages/{pid}")
    name, kind, cur = _status_prop(page)
    if not name:
        raise SessionError("notion_status", "el ticket no tiene una propiedad Status")
    if cur != status:
        _call("PATCH", f"/pages/{pid}", {"properties": {name: {kind: {"name": status}}}})
    return read(db, url, fresh=True)


def cached(db: Db, url: str | None) -> dict | None:
    if not url:
        return None
    try:
        return db.get(f"notion:{page_id(url)}")
    except SessionError:
        return None


def pending(db: Db, sid: str) -> list[str]:
    return list(db.get(f"devtickets:{sid}") or [])


def add_pending(db: Db, sid: str, url: str) -> list[str]:
    url = check_url(url)
    items = pending(db, sid)
    if url not in items:
        items.append(url)
    db.set(f"devtickets:{sid}", items)
    return items


async def refresh_loop(db: Db, urls, stop: asyncio.Event, on_change) -> None:
    """Cada TTL relee el Status de los tickets de los desarrollos abiertos (`urls()`); sin token, nada."""
    while not stop.is_set():
        if get_token():
            changed = False
            for u in list(urls()):
                before = (cached(db, u) or {}).get("status")
                try:
                    info = await asyncio.to_thread(read, db, u)
                except Exception:  # noqa: BLE001
                    log.exception("Status de Notion de %s", u)
                    continue
                changed |= info.get("status") != before
            if changed:
                on_change()
        try:
            await asyncio.wait_for(stop.wait(), TTL)
        except asyncio.TimeoutError:
            pass
