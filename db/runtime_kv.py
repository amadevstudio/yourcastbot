# -*- coding: utf-8 -*-
"""Small SQLite key-value store for state shared across processes.

The updater cursor, feed-failure counters, digest flags, and resend flags
must not live in gdbm/shelve: that file stays open in the bot process and
cannot be opened by updater/jobs. WAL SQLite is already the shared DB.
"""
import sqlite3
import threading

from config import db_path, shelve_name
from db.connection import connect_sqlite
from lib.tools.logger import logger

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bot_runtime_kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_ensure_lock = threading.Lock()
_ready = set()


def _database(database):
    return db_path if database is None else database


def ensure_table(connection, database=None):
    key = database
    if key is not None and key in _ready:
        return
    with _ensure_lock:
        if key is not None and key in _ready:
            return
        connection.execute(CREATE_TABLE_SQL)
        try:
            connection.commit()
        except sqlite3.OperationalError:
            pass
        if key is not None:
            _ready.add(key)


def _connect(database):
    database = _database(database)
    conn = connect_sqlite(database)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    ensure_table(conn, database)
    return conn


def get_kv(key, default=None, database=None):
    conn = _connect(database)
    try:
        row = conn.execute(
            "SELECT value FROM bot_runtime_kv WHERE key = ?",
            (str(key),),
        ).fetchone()
        if row is None:
            return default
        return row["value"]
    finally:
        conn.close()


def set_kv(key, value, database=None):
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO bot_runtime_kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(key), str(value)),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def delete_kv(key, database=None):
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "DELETE FROM bot_runtime_kv WHERE key = ?", (str(key),))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def incr_kv(key, database=None):
    """Atomically increment an integer value, starting from 0."""
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT value FROM bot_runtime_kv WHERE key = ?",
                (str(key),),
            ).fetchone()
            next_value = int(row["value"]) + 1 if row is not None else 1
            conn.execute(
                "INSERT INTO bot_runtime_kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(key), str(next_value)),
            )
            conn.execute("COMMIT")
            return next_value
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def migrate_updater_state_from_shelve(
        shelve_path=None, database=None):
    """Copy updater cursor out of gdbm before children open anything.

    Failures counters are left behind on purpose: iterating a 300MB+ shelve
    at deploy is not worth resetting a few feed-failure counts.
    """
    if get_kv("last_channel_id", database=database) is not None:
        return False
    path = shelve_name if shelve_path is None else shelve_path
    db = None
    try:
        import shelve
        db = shelve.open(path)
        copied = False
        if "last_channel_id" in db:
            set_kv(
                "last_channel_id", str(db["last_channel_id"]),
                database=database)
            copied = True
        if "last_channel_restarted" in db:
            set_kv(
                "last_channel_restarted",
                str(db["last_channel_restarted"]),
                database=database)
            copied = True
        if "new_podcast_available_flag" in db:
            set_kv(
                "new_podcast_available_flag",
                str(db["new_podcast_available_flag"]),
                database=database)
            copied = True
        if copied:
            logger.log("Migrated updater cursor from shelve to sqlite")
        return copied
    except Exception as e:
        logger.err("Could not migrate updater cursor from shelve:", e)
        return False
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
