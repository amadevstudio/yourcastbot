# -*- coding: utf-8 -*-
"""SQLite queue of nosub digest recipients.

Updater only enqueues user ids. The jobs process drains the table so the
RSS circle is not blocked by sleep(1) per user.

Rows are user ids only — no message bodies. One row per user. INSERT
coalesces a user already pending/leased; a done/failed user is requeued.
Claim uses the same lease protocol as send_outbox: pending → leased →
done/failed, 429 sets available_at.
"""
import sqlite3
import threading

from app.core.sender.outbox import (
    DONE_KEEP_DAYS,
    FAILED_KEEP_DAYS,
    LEASE_SECONDS,
    MAX_ATTEMPTS,
    MAX_BACKOFF_SECONDS,
    flood_wait_seconds,
    iso_after,
    now_iso,
)
from config import db_path
from db.connection import connect_sqlite
from db.runtime_kv import delete_kv, get_kv
from lib.tools.logger import logger

KV_FLAG_KEY = "new_podcast_available_flag"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS digest_outbox (
    user_telegram_id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    leased_until TEXT NULL,
    available_at TEXT NOT NULL
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS digest_outbox_claim_idx
    ON digest_outbox (status, available_at, user_telegram_id)
"""

_ready = set()
_ready_lock = threading.Lock()
_in_flight_lock = threading.Lock()
_in_flight = set()


def _database(database):
    return db_path if database is None else database


def _inflight_add(database, user_id):
    with _in_flight_lock:
        _in_flight.add((_database(database), int(user_id)))


def _inflight_discard(database, user_id):
    with _in_flight_lock:
        _in_flight.discard((_database(database), int(user_id)))


def _inflight_ids(database):
    database = _database(database)
    with _in_flight_lock:
        return [uid for db, uid in _in_flight if db == database]


def clear_in_flight():
    with _in_flight_lock:
        _in_flight.clear()


def _table_columns(connection):
    return [
        row[1] for row in
        connection.execute("PRAGMA table_info(digest_outbox)").fetchall()]


def _add_column(connection, sql):
    try:
        connection.execute(sql)
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise


def _ensure_lease_columns(connection):
    columns = _table_columns(connection)
    if not columns:
        return
    if "status" not in columns:
        _add_column(
            connection,
            "ALTER TABLE digest_outbox ADD COLUMN "
            "status TEXT NOT NULL DEFAULT 'pending'")
    if "attempts" not in columns:
        _add_column(
            connection,
            "ALTER TABLE digest_outbox ADD COLUMN "
            "attempts INTEGER NOT NULL DEFAULT 0")
    if "leased_until" not in columns:
        _add_column(
            connection,
            "ALTER TABLE digest_outbox ADD COLUMN leased_until TEXT NULL")
    if "available_at" not in columns:
        _add_column(
            connection,
            "ALTER TABLE digest_outbox ADD COLUMN available_at TEXT")
    connection.execute(
        "UPDATE digest_outbox SET available_at = created_at "
        "WHERE available_at IS NULL")
    connection.execute(CREATE_INDEX_SQL)


def ensure_table(connection, database=None):
    key = database
    if key is not None and key in _ready:
        return
    with _ready_lock:
        if key is not None and key in _ready:
            return
        connection.execute(CREATE_TABLE_SQL)
        _ensure_lease_columns(connection)
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


def _retry_delay(attempts, error):
    pause = flood_wait_seconds(error)
    if pause:
        return pause
    return min(MAX_BACKOFF_SECONDS, 2 ** max(int(attempts), 1))


def enqueue(user_id, database=None):
    """Flag a user for digest. Same user already queued stays one row."""
    database = _database(database)
    uid = _as_user_id(user_id)
    created_at = now_iso()
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO digest_outbox ("
                "user_telegram_id, created_at, status, attempts, "
                "leased_until, available_at) "
                "VALUES (?, ?, 'pending', 0, NULL, ?) "
                "ON CONFLICT(user_telegram_id) DO UPDATE SET "
                "status = CASE "
                "WHEN digest_outbox.status IN ('done', 'failed') "
                "THEN 'pending' ELSE digest_outbox.status END, "
                "attempts = CASE "
                "WHEN digest_outbox.status IN ('done', 'failed') "
                "THEN 0 ELSE digest_outbox.attempts END, "
                "leased_until = CASE "
                "WHEN digest_outbox.status IN ('done', 'failed') "
                "THEN NULL ELSE digest_outbox.leased_until END, "
                "available_at = CASE "
                "WHEN digest_outbox.status IN ('done', 'failed') "
                "THEN excluded.available_at "
                "ELSE digest_outbox.available_at END, "
                "created_at = CASE "
                "WHEN digest_outbox.status IN ('done', 'failed') "
                "THEN excluded.created_at "
                "ELSE digest_outbox.created_at END",
                (uid, created_at, created_at),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return uid


def reclaim(database=None, force=False):
    """Move leased rows back to pending when the worker is gone."""
    database = _database(database)
    now = now_iso()
    skip_ids = [] if force else _inflight_ids(database)
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if force:
                where = "status = 'leased'"
                params = []
            else:
                where = (
                    "status = 'leased' AND "
                    "(leased_until IS NULL OR leased_until <= ?)")
                params = [now]
            if skip_ids:
                placeholders = ",".join("?" * len(skip_ids))
                where += " AND user_telegram_id NOT IN (%s)" % placeholders
                params.extend(skip_ids)
            to_reclaim = conn.execute(
                "SELECT user_telegram_id, attempts FROM digest_outbox "
                "WHERE " + where,
                params,
            ).fetchall()
            for row in to_reclaim:
                logger.warn(
                    "digest reclaiming %s lease user=%s attempts=%s" % (
                        "force" if force else "expired",
                        row["user_telegram_id"], row["attempts"]))
            if to_reclaim:
                conn.execute(
                    "UPDATE digest_outbox "
                    "SET status = 'pending', leased_until = NULL "
                    "WHERE " + where,
                    params,
                )
            conn.execute("COMMIT")
            return len(to_reclaim)
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def claim(database=None):
    """Lease one available pending user. Returns a dict or None."""
    database = _database(database)
    now = now_iso()
    leased_until = iso_after(LEASE_SECONDS)
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM digest_outbox "
                "WHERE status = 'pending' AND available_at <= ? "
                "ORDER BY created_at ASC, user_telegram_id ASC LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            uid = int(row["user_telegram_id"])
            attempts = int(row["attempts"]) + 1
            conn.execute(
                "UPDATE digest_outbox "
                "SET status = 'leased', attempts = ?, leased_until = ? "
                "WHERE user_telegram_id = ? AND status = 'pending'",
                (attempts, leased_until, uid),
            )
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                conn.execute("ROLLBACK")
                return None
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        _inflight_add(database, uid)
        return {
            "user_telegram_id": uid,
            "attempts": attempts,
        }
    finally:
        conn.close()


def mark_done(user_id, database=None, attempts=None):
    database = _database(database)
    uid = _as_user_id(user_id)
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if attempts is None:
                conn.execute(
                    "UPDATE digest_outbox "
                    "SET status = 'done', leased_until = NULL "
                    "WHERE user_telegram_id = ? AND status = 'leased'",
                    (uid,),
                )
            else:
                conn.execute(
                    "UPDATE digest_outbox "
                    "SET status = 'done', leased_until = NULL "
                    "WHERE user_telegram_id = ? AND status = 'leased' "
                    "AND attempts = ?",
                    (uid, int(attempts)),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    _inflight_discard(database, uid)


def fail_or_retry(user_id, error=None, database=None, attempts=None):
    """On send exception: pending + backoff, or failed after MAX_ATTEMPTS."""
    database = _database(database)
    uid = _as_user_id(user_id)
    outcome = "skipped"
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM digest_outbox WHERE user_telegram_id = ?",
                (uid,),
            ).fetchone()
            if row is None or row["status"] != "leased":
                conn.execute("COMMIT")
                return outcome
            current_attempts = int(row["attempts"])
            if attempts is not None and current_attempts != int(attempts):
                conn.execute("COMMIT")
                return outcome
            if current_attempts >= MAX_ATTEMPTS:
                conn.execute(
                    "UPDATE digest_outbox "
                    "SET status = 'failed', leased_until = NULL "
                    "WHERE user_telegram_id = ?",
                    (uid,),
                )
                conn.execute("COMMIT")
                outcome = "failed"
            else:
                delay = _retry_delay(current_attempts, error)
                conn.execute(
                    "UPDATE digest_outbox "
                    "SET status = 'pending', leased_until = NULL, "
                    "available_at = ? "
                    "WHERE user_telegram_id = ?",
                    (iso_after(delay), uid),
                )
                conn.execute("COMMIT")
                outcome = "pending"
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    if outcome in ("failed", "pending"):
        _inflight_discard(database, uid)
    if outcome == "failed":
        logger.err(
            "digest permanently failed user=%s attempts=%s error=%s" % (
                uid, attempts, error))
    return outcome


def get_row(user_id, database=None):
    database = _database(database)
    uid = _as_user_id(user_id)
    conn = _connect(database)
    try:
        row = conn.execute(
            "SELECT * FROM digest_outbox WHERE user_telegram_id = ?",
            (uid,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def pending_count(database=None):
    """Users still to send: pending or currently leased."""
    database = _database(database)
    conn = _connect(database)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM digest_outbox "
            "WHERE status IN ('pending', 'leased')"
        ).fetchone()
        return int(row["n"] if row is not None else 0)
    finally:
        conn.close()


def _keep_days(value, default):
    days = default if value is None else int(value)
    if days < 1:
        raise ValueError("digest keep days must be at least 1")
    return days


def iso_before(days):
    import datetime
    delta = datetime.timedelta(days=max(int(days), 0))
    when = datetime.datetime.now(datetime.timezone.utc) - delta
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def purge_old(database=None, done_after_days=None, failed_after_days=None):
    """Delete old done/failed digest rows. Never touches pending or leased."""
    database = _database(database)
    done_days = _keep_days(done_after_days, DONE_KEEP_DAYS)
    failed_days = _keep_days(failed_after_days, FAILED_KEEP_DAYS)
    done_cutoff = iso_before(done_days)
    failed_cutoff = iso_before(failed_days)
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "DELETE FROM digest_outbox "
                "WHERE status = 'done' AND created_at IS NOT NULL "
                "AND created_at < ?",
                (done_cutoff,),
            )
            done_deleted = conn.execute("SELECT changes()").fetchone()[0]
            conn.execute(
                "DELETE FROM digest_outbox "
                "WHERE status = 'failed' AND created_at IS NOT NULL "
                "AND created_at < ?",
                (failed_cutoff,),
            )
            failed_deleted = conn.execute("SELECT changes()").fetchone()[0]
            conn.execute("COMMIT")
            return {
                "done": int(done_deleted),
                "failed": int(failed_deleted),
            }
        except Exception:
            conn.execute("ROLLBACK")
            raise
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
    clear_in_flight()
