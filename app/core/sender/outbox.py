# -*- coding: utf-8 -*-
"""Durable SQLite outbox for user-triggered rec/update send jobs.

In-memory queue.Queue is still used for in-process dispatch. The table is the
source of truth across process restarts.
"""
import datetime
import json
import sqlite3
import threading

from config import db_path
from db.connection import connect_sqlite
from lib.tools.logger import logger

LEASE_SECONDS = 30 * 60
MAX_ATTEMPTS = 8
MAX_BACKOFF_SECONDS = 5 * 60
ACTIONS = ('rec', 'update')

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS send_outbox (
    id INTEGER PRIMARY KEY,
    created_at TEXT,
    action TEXT NOT NULL,
    user_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    leased_until TEXT NULL,
    available_at TEXT NOT NULL
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS send_outbox_claim_idx
    ON send_outbox (status, available_at, id)
"""

_timers_lock = threading.Lock()
_timers = []


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        '%Y-%m-%dT%H:%M:%SZ')


def iso_after(seconds):
    delta = datetime.timedelta(seconds=max(float(seconds), 0.0))
    when = datetime.datetime.now(datetime.timezone.utc) + delta
    return when.strftime('%Y-%m-%dT%H:%M:%SZ')


def _database(database):
    return db_path if database is None else database


def ensure_table(connection, database=None):
    connection.execute(CREATE_TABLE_SQL)
    connection.execute(CREATE_INDEX_SQL)
    try:
        connection.commit()
    except sqlite3.OperationalError:
        # autocommit connections have nothing to commit
        pass


def _connect(database):
    conn = connect_sqlite(database)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    ensure_table(conn, database)
    return conn


def _maybe_int(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _restore_id_map(value):
    if not isinstance(value, dict):
        return {}
    return {_maybe_int(key): item for key, item in value.items()}


def payload_for_storage(job):
    """JSON object stored in send_outbox.payload_json (no Telegram objects)."""
    action = job.get('action')
    if action not in ACTIONS:
        raise ValueError("outbox action must be 'rec' or 'update', got %r" % (
            action,))
    user_id = job.get('user_id')
    if user_id is None:
        raise ValueError("outbox job is missing user_id")

    func_params = job.get('func_params') or {}
    if action == 'rec':
        stored_params = {
            'link': func_params.get('link'),
            'chat_ids': _jsonable(func_params.get('chat_ids') or {}),
            'utglangs': _jsonable(func_params.get('utglangs') or {}),
            'bitratestg': _jsonable(func_params.get('bitratestg') or {}),
            'podcastInfo': _jsonable(func_params.get('podcastInfo') or {}),
        }
    else:
        data = func_params.get('data')
        chat_id = func_params.get('chat_id')
        language_code = func_params.get('language_code')
        if isinstance(data, dict):
            if chat_id is None:
                chat_id = data.get('chat_id', user_id)
            if language_code is None:
                language_code = data.get('language_code')
        elif data is not None:
            if chat_id is None:
                chat_id = getattr(data, 'chat_id', user_id)
            if language_code is None:
                language_code = getattr(data, 'language_code', None)
        elif chat_id is None:
            chat_id = user_id
        stored_params = {
            'chat_id': _maybe_int(chat_id),
            'language_code': language_code,
            'is_user_have_bot_subscription': bool(
                func_params.get('is_user_have_bot_subscription')),
        }

    return json.dumps({
        'action': action,
        'user_id': user_id,
        'func_params': stored_params,
    }, ensure_ascii=False)


def func_params_from_storage(action, stored_params):
    stored_params = stored_params or {}
    if action == 'rec':
        return {
            'link': stored_params.get('link'),
            'chat_ids': _restore_id_map(stored_params.get('chat_ids')),
            'utglangs': _restore_id_map(stored_params.get('utglangs')),
            'bitratestg': _restore_id_map(stored_params.get('bitratestg')),
            'podcastInfo': stored_params.get('podcastInfo') or {},
        }

    chat_id = _maybe_int(stored_params.get('chat_id'))
    language_code = stored_params.get('language_code')
    return {
        'data': {
            'chat_id': chat_id,
            'language_code': language_code,
            'callback': None,
            'message': None,
        },
        'is_user_have_bot_subscription': bool(
            stored_params.get('is_user_have_bot_subscription')),
        'chat_id': chat_id,
        'language_code': language_code,
    }


def job_from_row(row):
    row = dict(row)
    payload = json.loads(row['payload_json'])
    action = row['action']
    return {
        'action': action,
        'user_id': _maybe_int(payload.get('user_id', row['user_id'])),
        'outbox_id': row['id'],
        'outbox_attempts': row['attempts'],
        'func_params': func_params_from_storage(
            action, payload.get('func_params')),
    }


def _retry_delay(attempts, error):
    if error is not None:
        from lib.telegram.general.errors import (
            get_timeout_from_error_bot, get_timeout_from_error_client)
        pause = get_timeout_from_error_bot(error)
        if not pause:
            pause = get_timeout_from_error_client(error)
        if pause:
            return int(pause)
    return min(MAX_BACKOFF_SECONDS, 2 ** max(int(attempts), 1))


def _wake(job):
    from app.controller.builders import recsModule
    recsModule.t_podcast_sender.main_queue.put(job)


def _schedule_retry(outbox_id, delay, database):
    def _run():
        try:
            job = claim(database=database, outbox_id=outbox_id)
            if job is not None:
                _wake(job)
        except Exception as e:
            logger.err("outbox scheduled retry failed:", e)

    timer = threading.Timer(max(float(delay), 0.0), _run)
    timer.daemon = True
    with _timers_lock:
        _timers[:] = [item for item in _timers if item.is_alive()]
        _timers.append(timer)
    timer.start()


def enqueue(job, database=None, dispatch=True):
    """Insert a pending row and, in-process, claim it onto the memory queue."""
    database = _database(database)
    payload_json = payload_for_storage(job)
    action = job['action']
    user_id = str(job['user_id'])
    created_at = now_iso()
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = conn.execute(
                "INSERT INTO send_outbox "
                "(created_at, action, user_id, payload_json, status, attempts, "
                "leased_until, available_at) "
                "VALUES (?, ?, ?, ?, 'pending', 0, NULL, ?)",
                (created_at, action, user_id, payload_json, created_at),
            )
            outbox_id = cursor.lastrowid
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()

    if dispatch:
        claimed = claim(database=database, outbox_id=outbox_id)
        if claimed is not None:
            _wake(claimed)
    return outbox_id


def reclaim(database=None, force=False):
    """Move leased rows back to pending.

    Expired leases (leased_until in the past) are always reclaimed. force=True
    also reclaims unexpired leases — use that on process start, when the
    previous process is gone.
    """
    database = _database(database)
    now = now_iso()
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if force:
                conn.execute(
                    "UPDATE send_outbox "
                    "SET status = 'pending', leased_until = NULL "
                    "WHERE status = 'leased'")
            else:
                conn.execute(
                    "UPDATE send_outbox "
                    "SET status = 'pending', leased_until = NULL "
                    "WHERE status = 'leased' AND "
                    "(leased_until IS NULL OR leased_until <= ?)",
                    (now,),
                )
            count = conn.execute("SELECT changes()").fetchone()[0]
            conn.execute("COMMIT")
            return count
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def claim(database=None, outbox_id=None):
    """Claim one available pending row. Returns a memory-queue job or None."""
    database = _database(database)
    now = now_iso()
    leased_until = iso_after(LEASE_SECONDS)
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if outbox_id is not None:
                row = conn.execute(
                    "SELECT * FROM send_outbox "
                    "WHERE id = ? AND status = 'pending' AND available_at <= ?",
                    (outbox_id, now),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM send_outbox "
                    "WHERE status = 'pending' AND available_at <= ? "
                    "ORDER BY id LIMIT 1",
                    (now,),
                ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            attempts = int(row['attempts']) + 1
            conn.execute(
                "UPDATE send_outbox "
                "SET status = 'leased', attempts = ?, leased_until = ? "
                "WHERE id = ? AND status = 'pending'",
                (attempts, leased_until, row['id']),
            )
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                conn.execute("ROLLBACK")
                return None
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        job = job_from_row(row)
        job['outbox_attempts'] = attempts
        return job
    finally:
        conn.close()


def mark_done(outbox_id, database=None, attempts=None):
    database = _database(database)
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if attempts is None:
                conn.execute(
                    "UPDATE send_outbox "
                    "SET status = 'done', leased_until = NULL "
                    "WHERE id = ? AND status = 'leased'",
                    (outbox_id,),
                )
            else:
                conn.execute(
                    "UPDATE send_outbox "
                    "SET status = 'done', leased_until = NULL "
                    "WHERE id = ? AND status = 'leased' AND attempts = ?",
                    (outbox_id, attempts),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def fail_or_retry(
        outbox_id, error=None, database=None, attempts=None, dispatch=True):
    """On worker exception: pending + backoff, or failed after MAX_ATTEMPTS."""
    database = _database(database)
    delay = None
    outcome = 'skipped'
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM send_outbox WHERE id = ?",
                (outbox_id,),
            ).fetchone()
            if row is None or row['status'] != 'leased':
                conn.execute("COMMIT")
                return outcome
            current_attempts = int(row['attempts'])
            if attempts is not None and current_attempts != int(attempts):
                conn.execute("COMMIT")
                return outcome
            if current_attempts >= MAX_ATTEMPTS:
                conn.execute(
                    "UPDATE send_outbox "
                    "SET status = 'failed', leased_until = NULL "
                    "WHERE id = ?",
                    (outbox_id,),
                )
                conn.execute("COMMIT")
                return 'failed'
            delay = _retry_delay(current_attempts, error)
            conn.execute(
                "UPDATE send_outbox "
                "SET status = 'pending', leased_until = NULL, available_at = ? "
                "WHERE id = ?",
                (iso_after(delay), outbox_id),
            )
            conn.execute("COMMIT")
            outcome = 'pending'
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()

    if outcome == 'pending' and dispatch and delay is not None:
        _schedule_retry(outbox_id, delay, database)
    return outcome


def get_row(outbox_id, database=None):
    database = _database(database)
    conn = _connect(database)
    try:
        row = conn.execute(
            "SELECT * FROM send_outbox WHERE id = ?", (outbox_id,)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()
