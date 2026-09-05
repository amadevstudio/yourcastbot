# -*- coding: utf-8 -*-
"""SQLite queue of nosub digest recipients.

Updater only enqueues user ids. The jobs process drains the table so the
RSS circle is not blocked by sleep(1) per user.

Rows are user ids only — no message bodies. INSERT OR IGNORE keeps the
table small when the same user is flagged on several podcasts.
"""
import sqlite3

from config import db_path
from db.connection import connect_sqlite
from db.runtime_kv import delete_kv, get_kv
from lib.tools.logger import logger

KV_FLAG_KEY = "new_podcast_available_flag"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS digest_outbox (
    user_telegram_id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL
)
"""

_ready = set()


def _database(database):
    return db_path if database is None else database


def now_iso():
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def ensure_table(connection, database=None):
    key = database
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


def _as_user_id(user_id):
    return int(user_id)


def enqueue(user_id, database=None):
    """Flag a user for digest. Same user twice stays one row."""
    database = _database(database)
    uid = _as_user_id(user_id)
    created_at = now_iso()
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO digest_outbox "
                "(user_telegram_id, created_at) VALUES (?, ?)",
                (uid, created_at),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return uid


def take_one(database=None):
    """Remove and return one user id, or None if the queue is empty.

    Delete-then-send is at-most-once: a crash after take_one skips this
    circle for that user until they are flagged again. A weekly reminder
    can miss once; a duplicate after restart is worse.
    """
    database = _database(database)
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT user_telegram_id FROM digest_outbox "
                "ORDER BY created_at ASC, user_telegram_id ASC LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            uid = int(row["user_telegram_id"])
            conn.execute(
                "DELETE FROM digest_outbox WHERE user_telegram_id = ?",
                (uid,),
            )
            conn.execute("COMMIT")
            return uid
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def pending_count(database=None):
    database = _database(database)
    conn = _connect(database)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM digest_outbox"
        ).fetchone()
        return int(row["n"] if row is not None else 0)
    finally:
        conn.close()


def migrate_from_kv(database=None):
    """Move the old JSON flag array into digest_outbox, then drop the key."""
    raw = get_kv(KV_FLAG_KEY, default=None, database=database)
    if not raw:
        return 0
    try:
        flags = __import__("json").loads(raw)
    except Exception:
        flags = []
    if not isinstance(flags, list):
        flags = []
    moved = 0
    for user_id in flags:
        try:
            enqueue(user_id, database=database)
            moved += 1
        except Exception as e:
            logger.err("digest_outbox migrate skip", user_id, e)
    delete_kv(KV_FLAG_KEY, database=database)
    if moved:
        logger.log("Migrated", moved, "digest flags from runtime_kv")
    return moved


def clear_ready_for_tests():
    _ready.clear()
