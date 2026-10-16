# server/ide_server/db.py
"""Base local del workspace (`.ide/ide.db`, SQLite): cache de GitHub y estado propio del IDE.

Las sesiones NO viven acá (siguen en disco, `.ide/sessions/<id>/`). Todo lo de GitHub es
reconstruible: ante una base corrupta se renombra a `.bak` y se arma de nuevo. Lo único propio
(`merges`, `kv`) se migra desde los JSON viejos (`merges.json`, `reviews.json`) la primera vez."""
from __future__ import annotations
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)
SCHEMA_VERSION = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS prs (          -- PRs abiertas: nodo GraphQL completo
  url TEXT PRIMARY KEY, id TEXT, node TEXT NOT NULL, updated_at TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS ref_prs (      -- PRs ya mergeadas/cerradas referidas (no cambian)
  key TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS members (
  org TEXT NOT NULL, login TEXT NOT NULL, name TEXT, PRIMARY KEY (org, login));
CREATE TABLE IF NOT EXISTS merges (       -- trabajos de merge del IDE
  url TEXT PRIMARY KEY, job TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv (           -- ajustes y marcas de tiempo
  key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
# v2: desarrollos (fuente de verdad de su estado) + historial + fotos de PRs para detectar cambios
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS devs (         -- un desarrollo con sesión (id = id de la sesión)
  id TEXT PRIMARY KEY, kind TEXT, title TEXT, notion_url TEXT, pr_url TEXT, status TEXT,
  archived INTEGER NOT NULL DEFAULT 0, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS events (       -- historial: quién hizo qué y cuándo
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, dev TEXT, pr_url TEXT,
  actor TEXT NOT NULL, kind TEXT NOT NULL, data TEXT);
CREATE INDEX IF NOT EXISTS events_dev ON events (dev, id);
CREATE INDEX IF NOT EXISTS events_pr ON events (pr_url, id);
CREATE TABLE IF NOT EXISTS pr_snaps (     -- última foto de cada PR relevante (para el historial)
  url TEXT PRIMARY KEY, snap TEXT NOT NULL);
"""


def db_path(root: Path) -> Path:
    return root / ".ide" / "ide.db"


class Db:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.RLock()          # una conexión compartida entre threads
        self._conn = self._open()

    def _open(self) -> sqlite3.Connection:
        path = db_path(self._root)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = self._connect(path)
            conn.execute("PRAGMA quick_check").fetchone()
        except sqlite3.DatabaseError as exc:
            bak = path.with_suffix(".db.bak")
            log.error("base %s corrupta (%s): la renombro a %s y la reconstruyo", path, exc, bak)
            path.replace(bak)
            conn = self._connect(path)
        self._migrate(conn)
        return conn

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2)
        if version == 0:
            self._import_json(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _import_json(self, conn: sqlite3.Connection) -> None:
        """Primera vez: `merges.json` y `reviews.json` pasan a la base (quedan como `.migrated`)."""
        ide = self._root / ".ide"
        merges, reviews = ide / "merges.json", ide / "reviews.json"
        try:
            if merges.is_file():
                for url, job in json.loads(merges.read_text(encoding="utf-8")).items():
                    conn.execute("INSERT OR REPLACE INTO merges VALUES (?, ?)", (url, json.dumps(job)))
                merges.replace(merges.with_suffix(".json.migrated"))
            if reviews.is_file():
                data = json.loads(reviews.read_text(encoding="utf-8"))
                if isinstance(data.get("reviewers"), list):
                    conn.execute("INSERT OR REPLACE INTO kv VALUES ('reviewers', ?)",
                                 (json.dumps(data["reviewers"]),))
                reviews.replace(reviews.with_suffix(".json.migrated"))
        except (OSError, ValueError, AttributeError) as exc:
            log.error("no pude migrar los JSON viejos a la base: %s", exc)

    # -- kv --------------------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))

    def with_prefix(self, prefix: str) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM kv WHERE substr(key, 1, ?) = ?",
                                      (len(prefix), prefix)).fetchall()
        return {k[len(prefix):]: json.loads(v) for k, v in rows}

    # -- nombres de desarrollos (solo del IDE; clave = la de la UI: s:<sesión>, st:<stack>, p:<url>) ----
    def dev_names(self) -> dict[str, str]:
        return self.with_prefix("devname:")

    def hidden_devs(self) -> list[str]:
        return sorted(self.with_prefix("devhidden:"))

    def set_dev_hidden(self, key: str, hidden: bool) -> None:
        if hidden:
            self.set(f"devhidden:{key}", True)
        else:
            self.delete(f"devhidden:{key}")

    # -- PRs vinculadas a una sesión (pegajoso: siguen en el desarrollo aunque el worktree cambie de rama) --
    def dev_prs(self) -> dict[str, dict]:
        """url -> {"sid": sesión, "out": True si se sacó a mano (no vuelve por rama)}."""
        return self.with_prefix("devpr:")

    def link_pr(self, url: str, sid: str, *, out: bool = False) -> None:
        self.set(f"devpr:{url}", {"sid": sid, **({"out": True} if out else {})})

    def set_dev_name(self, key: str, name: str | None) -> None:
        if name:
            self.set(f"devname:{key}", name)
        else:
            self.delete(f"devname:{key}")

    # -- prs ---------------------------------------------------------------------------------
    def upsert_prs(self, nodes: Iterable[dict], fetched_at: str) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            for n in nodes:
                self._conn.execute("INSERT OR REPLACE INTO prs VALUES (?, ?, ?, ?, ?)",
                                   (n["url"], n.get("id"), json.dumps(n), n.get("updatedAt"), fetched_at))
            self._conn.execute("COMMIT")

    def delete_prs(self, urls: Iterable[str]) -> None:
        with self._lock:
            self._conn.executemany("DELETE FROM prs WHERE url = ?", [(u,) for u in urls])

    def open_prs(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT node FROM prs").fetchall()
        return [json.loads(r[0]) for r in rows]

    # -- referencias cerradas/mergeadas -----------------------------------------------------------
    def get_refs(self, keys: Iterable[str]) -> dict[str, dict]:
        keys = list(keys)
        if not keys:
            return {}
        with self._lock:
            rows = self._conn.execute(
                f"SELECT key, data FROM ref_prs WHERE key IN ({','.join('?' * len(keys))})", keys).fetchall()
        return {k: json.loads(d) for k, d in rows}

    def put_refs(self, refs: dict[str, dict]) -> None:
        with self._lock:
            self._conn.executemany("INSERT OR REPLACE INTO ref_prs VALUES (?, ?)",
                                   [(k, json.dumps(v)) for k, v in refs.items()])

    # -- miembros ---------------------------------------------------------------------------------
    def members(self, orgs: list[str]) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT DISTINCT login, name FROM members WHERE org IN ({','.join('?' * len(orgs))})",
                orgs).fetchall() if orgs else []
        return sorted(({"login": l, "name": n} for l, n in rows), key=lambda m: m["login"].lower())

    def set_members(self, org: str, members: list[dict]) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            self._conn.execute("DELETE FROM members WHERE org = ?", (org,))
            self._conn.executemany("INSERT INTO members VALUES (?, ?, ?)",
                                   [(org, m["login"], m.get("name")) for m in members])
            self._conn.execute("COMMIT")

    # -- merges -----------------------------------------------------------------------------------
    def merges(self) -> dict[str, dict]:
        with self._lock:
            rows = self._conn.execute("SELECT url, job FROM merges").fetchall()
        return {u: json.loads(j) for u, j in rows}

    def delete_merge(self, url: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM merges WHERE url = ?", (url,))

    def put_merge(self, url: str, job: dict) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO merges VALUES (?, ?)", (url, json.dumps(job)))

    # -- desarrollos ------------------------------------------------------------------------------
    def devs(self, include_archived: bool = False) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, kind, title, notion_url, pr_url, status, archived, created, updated FROM devs"
                + ("" if include_archived else " WHERE archived = 0")).fetchall()
        keys = ("id", "kind", "title", "notionUrl", "prUrl", "status", "archived", "created", "updated")
        return [dict(zip(keys, r)) for r in rows]

    def dev(self, dev_id: str) -> dict | None:
        return next((d for d in self.devs(include_archived=True) if d["id"] == dev_id), None)

    def put_dev(self, dev: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO devs (id, kind, title, notion_url, pr_url, status, archived, created, updated)"
                " VALUES (:id, :kind, :title, :notionUrl, :prUrl, :status, :archived, :created, :updated)"
                " ON CONFLICT(id) DO UPDATE SET kind=:kind, title=:title, notion_url=:notionUrl,"
                " pr_url=:prUrl, status=:status, archived=:archived, updated=:updated",
                {"archived": 0, "created": None, **dev})

    # -- historial ----------------------------------------------------------------------------------
    def event(self, at: str, actor: str, kind: str, *, dev: str | None = None,
              pr_url: str | None = None, data: dict | None = None) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO events (at, dev, pr_url, actor, kind, data) VALUES (?, ?, ?, ?, ?, ?)",
                               (at, dev, pr_url, actor, kind, json.dumps(data or {})))

    def events(self, *, dev: str | None = None, pr_urls: list[str] | None = None, limit: int = 50) -> list[dict]:
        conds, args = [], []
        if dev:
            conds.append("dev = ?"); args.append(dev)
        if pr_urls:
            conds.append(f"pr_url IN ({','.join('?' * len(pr_urls))})"); args += pr_urls
        where = f"WHERE {' OR '.join(conds)}" if conds else ""
        with self._lock:
            rows = self._conn.execute(f"SELECT at, dev, pr_url, actor, kind, data FROM events {where}"
                                      " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
        return [{"at": a, "dev": d, "prUrl": u, "actor": ac, "kind": k, "data": json.loads(x or "{}")}
                for a, d, u, ac, k, x in rows]

    # -- fotos de PRs ---------------------------------------------------------------------------------
    def pr_snaps(self, urls: list[str]) -> dict[str, dict]:
        if not urls:
            return {}
        with self._lock:
            rows = self._conn.execute(
                f"SELECT url, snap FROM pr_snaps WHERE url IN ({','.join('?' * len(urls))})", urls).fetchall()
        return {u: json.loads(x) for u, x in rows}

    def put_pr_snaps(self, snaps: dict[str, dict]) -> None:
        with self._lock:
            self._conn.executemany("INSERT OR REPLACE INTO pr_snaps VALUES (?, ?)",
                                   [(u, json.dumps(x)) for u, x in snaps.items()])
