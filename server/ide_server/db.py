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
SCHEMA_VERSION = 1
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
