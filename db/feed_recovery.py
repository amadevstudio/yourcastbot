"""Durable feed repair jobs. A feed pause never changes a listener's notify flag."""
import sqlite3
import threading
import time
import uuid

from config import db_path
from db.connection import connect_sqlite

RECHECK_SECONDS = 24 * 60 * 60
MANUAL_GAP_SECONDS = 5 * 60
LEASE_SECONDS = 5 * 60
_ready = set()
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS feed_recovery (
    channel_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    available_at REAL NOT NULL,
    leased_until REAL,
    lease_token TEXT,
    checked_at REAL,
    recovered_at REAL,
    result TEXT,
    notice_cursor INTEGER NOT NULL DEFAULT 0,
    notice_done INTEGER NOT NULL DEFAULT 0,
    notice_after REAL NOT NULL DEFAULT 0,
    notice_token TEXT
);
CREATE INDEX IF NOT EXISTS feed_recovery_due
    ON feed_recovery(status, available_at);
"""


def connect(database=None):
    database = db_path if database is None else database
    conn = connect_sqlite(database)
    conn.row_factory = sqlite3.Row
    with _lock:
        if database not in _ready or database == ':memory:':
            conn.executescript(SCHEMA)
            _ready.add(database)
    return conn


def enqueue(channel_id, reason, paused=False, manual=False, now=None, database=None):
    """Coalesce failures. Repeated circles/clicks cannot bypass a check's cooldown."""
    stamp = time.time() if now is None else now
    conn = connect(database)
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM feed_recovery WHERE channel_id=?", (channel_id,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO feed_recovery "
                    "(channel_id,status,paused,reason,available_at) VALUES (?,'pending',?,?,?)",
                    (channel_id, int(paused), reason, stamp))
                return True
            # A job already in flight owns its result. The updater may only add a pause.
            due = row['available_at']
            status = row['status']
            if status == 'healthy':
                status = 'pending'
                due = max(stamp, (row['checked_at'] or 0) + MANUAL_GAP_SECONDS)
            elif manual and status != 'leased':
                due = min(due, max(stamp, (row['checked_at'] or 0) + MANUAL_GAP_SECONDS))
            conn.execute(
                "UPDATE feed_recovery SET status=?, paused=max(paused,?), reason=?, "
                "available_at=?,notice_done=CASE WHEN paused=0 AND ?=1 THEN 0 "
                "ELSE notice_done END,notice_cursor=CASE WHEN paused=0 AND ?=1 THEN 0 "
                "ELSE notice_cursor END,notice_after=CASE WHEN paused=0 AND ?=1 THEN 0 "
                "ELSE notice_after END,notice_token=CASE WHEN paused=0 AND ?=1 THEN NULL "
                "ELSE notice_token END WHERE channel_id=?",
                (status, int(paused), reason, due, int(paused), int(paused),
                 int(paused), int(paused), channel_id))
            return status != 'leased' and due <= stamp
    finally:
        conn.close()


def seed_legacy(database=None, now=None):
    """Check old dead feeds once. Never infer why a listener has notify=0."""
    stamp = time.time() if now is None else now
    conn = connect(database)
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO feed_recovery "
                "(channel_id,status,paused,reason,available_at,notice_done) "
                "SELECT c.id,'pending',1,'legacy',?,1 FROM channels c "
                "JOIN bot_runtime_kv k ON k.key='channel_feed_dead_until_'||c.id",
                (stamp,))
    finally:
        conn.close()


def claim(database=None, now=None):
    stamp = time.time() if now is None else now
    conn = connect(database)
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM feed_recovery WHERE "
                "(status='pending' AND available_at<=?) OR "
                "(status='leased' AND leased_until<=?) "
                "ORDER BY available_at,channel_id LIMIT 1", (stamp, stamp)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            conn.execute(
                "UPDATE feed_recovery SET status='leased',leased_until=?,lease_token=? "
                "WHERE channel_id=?", (stamp + LEASE_SECONDS, token, row['channel_id']))
            return {**dict(row), 'lease_token': token}
    finally:
        conn.close()


def channel(channel_id, database=None):
    conn = connect(database)
    try:
        row = conn.execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def finish(job, channel_before, new_url=None, result='unavailable', database=None, now=None):
    """Fence stale leases and concurrent URL edits; replace only URL and validators.

    Subscription/channel cursors, notify, tariff and delivery queues are untouched.
    Clearing the old refetch guard lets the ordinary updater catch up after repair.
    """
    stamp = time.time() if now is None else now
    conn = connect(database)
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            owns = conn.execute(
                "SELECT 1 FROM feed_recovery WHERE channel_id=? AND status='leased' "
                "AND lease_token=? AND leased_until>?",
                (job['channel_id'], job['lease_token'], stamp)).fetchone()
            if owns is None:
                return False
            current = conn.execute(
                "SELECT rss_link,itunes_id FROM channels WHERE id=?",
                (job['channel_id'],)).fetchone()
            unchanged = current is not None and channel_before is not None and (
                current['rss_link'] == channel_before['rss_link']
                and current['itunes_id'] == channel_before['itunes_id'])
            if current is None:
                conn.execute("UPDATE feed_recovery SET status='deleted',paused=0,"
                             "checked_at=?,result='channel_deleted',leased_until=NULL,lease_token=NULL "
                             "WHERE channel_id=?", (stamp, job['channel_id']))
                return False
            if new_url and unchanged:
                conn.execute(
                    "UPDATE channels SET rss_link=?,http_etag=NULL,http_last_modified=NULL "
                    "WHERE id=?", (new_url, job['channel_id']))
                conn.execute(
                    "DELETE FROM bot_runtime_kv WHERE key IN (?,?,?)",
                    tuple(prefix + str(job['channel_id']) for prefix in (
                        'channel_feed_dead_until_', 'channel_feed_failures_', 'feed_refetch_')))
                conn.execute(
                    "UPDATE feed_recovery SET status='healthy',paused=0,checked_at=?, "
                    "recovered_at=?,result='recovered',leased_until=NULL,lease_token=NULL "
                    "WHERE channel_id=?", (stamp, stamp, job['channel_id']))
                return True
            conn.execute(
                "UPDATE feed_recovery SET status='pending',available_at=?,checked_at=?, "
                "result=?,leased_until=NULL,lease_token=NULL WHERE channel_id=?",
                (stamp + RECHECK_SECONDS, stamp,
                 result if unchanged else 'channel_changed', job['channel_id']))
            return False
    finally:
        conn.close()


def note_ok(channel_id, database=None, now=None):
    """A normal successful feed fetch also ends a pause and cancels obsolete repairs."""
    conn = connect(database)
    try:
        with conn:
            conn.execute(
                "UPDATE feed_recovery SET status='healthy',paused=0,result='available', "
                "checked_at=?,leased_until=NULL,lease_token=NULL WHERE channel_id=?",
                (time.time() if now is None else now, channel_id))
    finally:
        conn.close()


def statuses(channel_ids, database=None):
    ids = list(channel_ids)
    if not ids:
        return {}
    conn = connect(database)
    try:
        return {r['channel_id']: dict(r) for r in conn.execute(
            "SELECT * FROM feed_recovery WHERE channel_id IN (%s)" % ','.join('?' * len(ids)), ids)}
    finally:
        conn.close()


def next_notice(database=None, now=None):
    """One private-chat pause notice at a time, outside the updater/send pools."""
    stamp = time.time() if now is None else now
    conn = connect(database)
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            state = conn.execute(
                "SELECT * FROM feed_recovery WHERE paused=1 AND notice_done=0 "
                "AND notice_after<=? ORDER BY notice_after,channel_id LIMIT 1", (stamp,)).fetchone()
            if state is None:
                return None
            row = conn.execute(
                "SELECT s.id AS sub_id,s.user_telegram_id,u.lang,c.name "
                "FROM user_channel_cs s JOIN users u ON u.telegramId=s.user_telegram_id "
                "JOIN channels c ON c.id=s.channel_id WHERE s.channel_id=? "
                "AND s.id>? AND s.notify=1 AND u.deleted_at IS NULL "
                "AND s.user_telegram_id>0 ORDER BY s.id LIMIT 1",
                (state['channel_id'], state['notice_cursor'])).fetchone()
            if row is None:
                conn.execute('UPDATE feed_recovery SET notice_done=1 WHERE channel_id=?',
                             (state['channel_id'],))
                return None
            token = uuid.uuid4().hex
            conn.execute(
                'UPDATE feed_recovery SET notice_after=?,notice_token=? WHERE channel_id=?',
                (stamp + 60, token, state['channel_id']))
            return {**dict(row), 'channel_id': state['channel_id'], 'token': token}
    finally:
        conn.close()


def finish_notice(notice, retry_after=None, database=None, now=None):
    stamp = time.time() if now is None else now
    conn = connect(database)
    try:
        with conn:
            if retry_after is None:
                conn.execute(
                    'UPDATE feed_recovery SET notice_cursor=?,notice_after=?,notice_token=NULL '
                    'WHERE channel_id=? AND notice_token=? AND paused=1',
                    (notice['sub_id'], stamp, notice['channel_id'], notice['token']))
            else:
                conn.execute(
                    'UPDATE feed_recovery SET notice_after=?,notice_token=NULL '
                    'WHERE channel_id=? AND notice_token=?',
                    (stamp + retry_after, notice['channel_id'], notice['token']))
    finally:
        conn.close()
