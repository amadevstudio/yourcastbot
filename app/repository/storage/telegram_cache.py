import datetime
import json
import sqlite3
import threading
import time
from typing import Literal, Any

from config import db_path, use_cache
from db.connection import connect_sqlite

# Telegram file_ids and short-lived search results, shared by bot and updater.
# This lived in a gdbm shelve, which never gives space back: 20 MB of entries
# grew to 527 MB, and compacting it meant stopping the bot. SQLite with an
# expiry column drops old rows as new ones arrive.

file_types = Literal['img', 'audio']

CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS telegram_cache ("
    " key TEXT PRIMARY KEY,"
    " value TEXT NOT NULL,"
    " expires_at REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS telegram_cache_expires ON telegram_cache (expires_at)",
)

_ready = set()
_ready_lock = threading.Lock()


def _connect(database=None):
    database = db_path if database is None else database
    conn = connect_sqlite(database)
    conn.isolation_level = None
    if database not in _ready:
        with _ready_lock:
            if database not in _ready:
                for sql in CREATE_SQL:
                    conn.execute(sql)
                _ready.add(database)
    return conn


def _get(key, now=None, database=None) -> Any:
    now = time.time() if now is None else now
    conn = _connect(database)
    try:
        row = conn.execute(
            "SELECT value, expires_at FROM telegram_cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        if row[1] < now:
            conn.execute("DELETE FROM telegram_cache WHERE key = ?", (key,))
            return None
        try:
            return json.loads(row[0])
        except ValueError:
            return None
    finally:
        conn.close()


def _save(key, value, expires_at: float, now=None, database=None):
    now = time.time() if now is None else now
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO telegram_cache (key, value, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "expires_at = excluded.expires_at",
                (key, json.dumps(value), expires_at))
            # Entries nobody reads again would otherwise stay forever
            conn.execute("DELETE FROM telegram_cache WHERE expires_at < ?", (now,))
            conn.execute("COMMIT")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def import_entries(entries, now=None, database=None) -> int:
    """Bulk insert (key, value, expires_at) rows, skipping expired ones and
    keys already present. For the one-time move out of the shelve."""
    now = time.time() if now is None else now
    rows = [(k, json.dumps(v), exp) for k, v, exp in entries if exp >= now]
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "INSERT OR IGNORE INTO telegram_cache (key, value, expires_at) VALUES (?, ?, ?)",
            rows)
        conn.execute("COMMIT")
    finally:
        conn.close()
    return len(rows)


def get_file_id(file: str, file_type: file_types):
    if not use_cache:
        return None

    return _get(f'{file_type}:{file}')


def add_file_id(
        file: str, file_id: str, file_type: file_types,
        expiration_date: datetime.datetime | None = None):
    # Default arguments are evaluated once on import, so the expiration has to be built on every call,
    # otherwise every entry expires at "process start + 3 days" and the cache dies for good
    if expiration_date is None:
        expiration_date = datetime.datetime.now() + datetime.timedelta(days=3)

    _save(f'{file_type}:{file}', file_id, expiration_date.timestamp())


def get_cached(unique: str):
    return _get(f'strCache:{unique}')


def add_cache(
        unique: str, value: Any,
        expiration_date: datetime.datetime | None = None):
    if expiration_date is None:
        expiration_date = datetime.datetime.now() + datetime.timedelta(hours=1)

    _save(f'strCache:{unique}', value, expiration_date.timestamp())


def close_storage():
    # Per-call connections; nothing long-lived to shut down.
    pass
