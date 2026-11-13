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
PR_REVIEW = "PR Review"
# los Status de antes de la revisión: de ahí pasa a PR Review al mandarlo a revisión
BEFORE_REVIEW = ("Backlog", "To Do", "In progress", "Returned")
_ID_RE = re.compile(r"([0-9a-f]{32})(?:[?#/]|$)")


def check_url(url: str) -> str:
    """Un link de Notion de verdad (https, a un dominio de Notion, sin caracteres de control): la card lo abre."""
    from urllib.parse import urlparse
    url = str(url or "").strip()
    u = urlparse(url)
    host = (u.hostname or "").rstrip(".").lower()
    # sin `\\`, `@` ni usuario/puerto: links que el navegador podría leer con otro dominio que Python
    if any(ord(c) < 32 for c in url) or "\\" in url or "@" in url or u.username or u.password or u.port \
            or u.scheme != "https" or u.netloc.lower().rstrip(".") != host or not (
            host in ("notion.so", "www.notion.so", "app.notion.com", "notion.com", "www.notion.com")
            or host.endswith(".notion.site")):
        raise SessionError("bad_notion_url", f"tiene que ser un link https de Notion: {url[:120]!r}")
    page_id(url)
    # se guarda reconstruido desde sus partes (lo que se abre es exactamente lo que se validó)
    return f"https://{host}{u.path}" + (f"?{u.query}" if u.query else "")


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
    # de una conexión interna (ntn_…/secret_…) o un token personal (Developer tools → Personal access tokens)
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", token):
        raise SessionError("bad_request", "eso no parece un token de Notion (sin espacios ni comillas)")
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


def _children(page: dict) -> list[str]:
    """Las tarjetas hijas: la relación «Tickets» (se llena sola cuando la hija apunta a la madre en «Historia»)."""
    for name, prop in (page.get("properties") or {}).items():
        if name.lower() == "tickets" and prop.get("type") == "relation":
            return [r["id"].replace("-", "") for r in prop.get("relation") or [] if r.get("id")]
    return []


def page_url(pid: str) -> str:
    return f"https://app.notion.com/p/{pid.replace('-', '')}"


def read(db: Db, url: str, *, fresh: bool = False) -> dict:
    """{status, title, at, error} del ticket (de la caché si tiene menos de TTL)."""
    pid = page_id(url)
    cached = db.get(f"notion:{pid}") or {}
    if not fresh and cached.get("ts") and time.time() - cached["ts"] < TTL:
        return cached
    try:
        page = _call("GET", f"/pages/{pid}")
        _, _, status = _status_prop(page)
        info = {"status": status, "title": _title(page), "children": _children(page), "ts": time.time(),
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


def subs(db: Db, sid: str, main_url: str | None) -> list[str]:
    """Los subtickets del desarrollo: las hijas del ticket (relación «Tickets» de la caché) + las sumadas a mano
    (`ide ticket add-sub`), sin las sacadas (`rm-sub`) ni el ticket mismo."""
    main = cached(db, main_url) or {}
    hidden = set(db.get(f"devsubshide:{sid}") or [])
    out: list[str] = []
    # los «pendientes» de antes (`add-pending`, `devtickets:`) también son subtickets
    for u in [page_url(c) for c in main.get("children") or []] + list(db.get(f"devsubs:{sid}") or []) + pending(db, sid):
        try:
            pid = page_id(u)
        except SessionError:
            continue
        if pid in hidden or (main_url and _same(u, main_url)) or any(_same(u, x) for x in out):
            continue
        out.append(u)
    return out


def _same(a: str, b: str) -> bool:
    try:
        return page_id(a) == page_id(b)
    except SessionError:
        return False


def add_sub(db: Db, sid: str, url: str) -> None:
    """`ide ticket add-sub` (y `add-pending`, que quedó como sinónimo)."""
    url = check_url(url)
    pid = page_id(url)
    db.set(f"devsubshide:{sid}", [x for x in db.get(f"devsubshide:{sid}") or [] if x != pid])
    items = list(db.get(f"devsubs:{sid}") or [])
    if not any(_same(url, x) for x in items):
        db.set(f"devsubs:{sid}", items + [url])


def card_hidden(db: Db, sid: str) -> set[str]:
    """Los subtickets que no se muestran en la card (el interruptor del módulo Notion); siguen siendo subtickets."""
    return set(db.get(f"devsubscard:{sid}") or [])


def set_card(db: Db, sid: str, url: str, show: bool) -> None:
    pid = page_id(url)
    hidden = card_hidden(db, sid)
    hidden = hidden - {pid} if show else hidden | {pid}
    db.set(f"devsubscard:{sid}", sorted(hidden))


def rm_sub(db: Db, sid: str, url: str) -> None:
    """Saca uno sumado a mano y esconde una hija de la relación (no toca Notion)."""
    pid = page_id(url)
    db.set(f"devsubs:{sid}", [x for x in db.get(f"devsubs:{sid}") or [] if not _same(url, x)])
    db.set(f"devtickets:{sid}", [x for x in pending(db, sid) if not _same(url, x)])
    hidden = list(db.get(f"devsubshide:{sid}") or [])
    if pid not in hidden:
        db.set(f"devsubshide:{sid}", hidden + [pid])


async def refresh_loop(db: Db, urls, stop: asyncio.Event, on_change) -> None:
    """Relee el Status de los tickets de los desarrollos abiertos (`urls()`) cada TTL; los que todavía no tienen
    caché (un ticket recién asociado, una hija nueva de la relación «Tickets»), en el minuto. Sin token, nada."""
    last_full = 0.0
    while not stop.is_set():
        if get_token():
            changed = False
            full = time.time() - last_full >= TTL
            for u in list(urls()):
                prev = cached(db, u)
                if not full and prev and prev.get("ts"):
                    continue                        # entre vueltas completas, solo los que nunca se leyeron
                before = (prev or {}).get("status")
                try:
                    # fresh: el loop ya espera TTL entre vueltas (con la caché además, un cambio tardaba hasta 2×TTL)
                    info = await asyncio.to_thread(read, db, u, fresh=True)
                except Exception:  # noqa: BLE001
                    log.exception("Status de Notion de %s", u)
                    continue
                changed |= info.get("status") != before or prev is None
            if full:
                last_full = time.time()
            if changed:
                on_change()
        try:
            await asyncio.wait_for(stop.wait(), 60)
        except asyncio.TimeoutError:
            pass


# -- la tarjeta en el IDE (tab «Notion» del panel principal): su contenido como Markdown ------------------------------
MAX_BLOCKS = 600


def _rich(rt: list[dict]) -> str:
    out = []
    for t in rt or []:
        txt = t.get("plain_text", "")
        if not txt:
            continue
        a = t.get("annotations") or {}
        if a.get("code"):
            txt = f"`{txt}`"
        if a.get("bold"):
            txt = f"**{txt.strip()}** " if txt.endswith(" ") else f"**{txt}**"
        if a.get("italic"):
            txt = f"*{txt}*"
        if a.get("strikethrough"):
            txt = f"~~{txt}~~"
        href = t.get("href")
        if href and href.startswith(("http://", "https://")):
            txt = f"[{txt}]({href})"
        out.append(txt)
    return "".join(out)


def _children_of(bid: str) -> list[dict]:
    out, cursor = [], None
    while True:
        q = f"/blocks/{bid}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        r = _call("GET", q)
        out += r.get("results") or []
        if not r.get("has_more") or len(out) >= MAX_BLOCKS:
            return out
        cursor = r.get("next_cursor")


def _blocks_md(blocks: list[dict], depth: int, count: list[int]) -> list[str]:
    lines: list[str] = []
    ind = "  " * depth
    n = 0
    for b in blocks:
        count[0] += 1
        if count[0] > MAX_BLOCKS:
            lines.append(f"{ind}*(… la tarjeta sigue: ábrela en Notion)*")
            break
        t = b.get("type")
        d = b.get(t) or {}
        txt = _rich(d.get("rich_text") or [])
        if t != "numbered_list_item":
            n = 0
        if t == "paragraph":
            lines.append(f"{ind}{txt}" if txt else "")
        elif t in ("heading_1", "heading_2", "heading_3"):
            lines += ["", f"{'#' * int(t[-1]) } {txt}", ""]
        elif t == "bulleted_list_item":
            lines.append(f"{ind}- {txt}")
        elif t == "numbered_list_item":
            n += 1
            lines.append(f"{ind}{n}. {txt}")
        elif t == "to_do":
            lines.append(f"{ind}- [{'x' if d.get('checked') else ' '}] {txt}")
        elif t == "toggle":
            lines.append(f"{ind}- ▸ {txt}")
        elif t == "quote":
            lines.append(f"{ind}> {txt}")
        elif t == "callout":
            icon = (d.get("icon") or {}).get("emoji") or "💡"
            lines.append(f"{ind}> {icon} {txt}")
        elif t == "code":
            lines += [f"{ind}```{d.get('language') or ''}", *[ind + x for x in "".join(r.get("plain_text", "") for r in d.get("rich_text") or []).splitlines()], f"{ind}```"]
        elif t == "divider":
            lines.append(f"{ind}---")
        elif t in ("image", "file", "pdf", "video"):
            src = (d.get("file") or d.get("external") or {}).get("url") or ""
            cap = _rich(d.get("caption") or []) or t
            if src.startswith("https://"):
                lines.append(f"{ind}![{cap}]({src})" if t == "image" else f"{ind}[📎 {cap}]({src})")
        elif t == "bookmark" or t == "embed" or t == "link_preview":
            u = d.get("url") or ""
            if u.startswith(("http://", "https://")):
                lines.append(f"{ind}[🔗 {_rich(d.get('caption') or []) or u}]({u})")
        elif t == "child_page":
            lines.append(f"{ind}📄 {d.get('title') or 'subpágina'}")
        elif t == "child_database":
            lines.append(f"{ind}🗃 {d.get('title') or 'base de datos'}")
        elif t == "table_row":
            lines.append(f"{ind}| " + " | ".join(_rich(c) for c in d.get("cells") or []) + " |")
        elif txt:
            lines.append(f"{ind}{txt}")
        # hijos: sublistas, el contenido de un toggle, las filas de una tabla, columnas
        if b.get("has_children") and depth < 4 and t not in ("child_page", "child_database"):
            kids = _children_of(b["id"])
            if t == "table":
                rows = _blocks_md(kids, depth, count)
                if rows:
                    cols = rows[0].count("|") - 1
                    lines += ["", rows[0], "|" + "---|" * max(cols, 1), *rows[1:], ""]
            else:
                lines += _blocks_md(kids, depth + (1 if t in ("bulleted_list_item", "numbered_list_item", "to_do", "toggle") else 0), count)
    return lines


def page_markdown(db: Db, url: str) -> dict:
    """{url, title, status, markdown} de una tarjeta (para la tab «Notion» del IDE). Actualiza la caché del Status."""
    url = check_url(url)
    pid = page_id(url)
    page = _call("GET", f"/pages/{pid}")
    _, _, status = _status_prop(page)
    title = _title(page)
    md = "\n".join(_blocks_md(_children_of(pid), 0, [0]))
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    cur = db.get(f"notion:{pid}") or {}
    db.set(f"notion:{pid}", {**cur, "status": status, "title": title, "children": _children(page), "ts": time.time(),
                             "at": datetime.now().isoformat(timespec="minutes"), "error": None})
    return {"url": url, "title": title, "status": status, "markdown": md, "notionUrl": page.get("url")}
