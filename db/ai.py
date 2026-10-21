"""AI summaries: the episodes a summary can be asked for, cached transcripts
and summaries, and the queue the jobs process drains.

An episode is known by its ref (db.usage.episode_ref of the enclosure URL):
the sender remembers it when it delivers the file, the button carries only
the ref. A transcript is made once per episode; a summary once per episode
and language, and then it is free for everyone who asks.

Prod SQLite is 3.31: no RETURNING, claims use BEGIN IMMEDIATE.
"""
import sqlite3
import threading
import time

from config import db_path
from db.connection import connect_sqlite

LEASE_SECONDS = 30 * 60
MAX_ATTEMPTS = 2
KEEP_DAYS = 180

_ready = set()
_lock = threading.Lock()
SCHEMA = '''
CREATE TABLE IF NOT EXISTS ai_episodes (
    ref TEXT PRIMARY KEY, link TEXT NOT NULL, channel_id INTEGER, title TEXT NOT NULL,
    show TEXT NOT NULL, seen_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_transcripts (
    ref TEXT PRIMARY KEY, text TEXT NOT NULL, source TEXT NOT NULL,
    cost_usd REAL NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_summaries (
    ref TEXT NOT NULL, lang TEXT NOT NULL, text TEXT NOT NULL,
    cost_usd REAL NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (ref, lang)
);
CREATE TABLE IF NOT EXISTS ai_requests (
    id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, ref TEXT NOT NULL, lang TEXT NOT NULL,
    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, leased_until REAL
);
CREATE INDEX IF NOT EXISTS ai_requests_status ON ai_requests(status, id);
'''


def connect(database=None):
    database = db_path if database is None else database
    c = connect_sqlite(database)
    c.row_factory = sqlite3.Row
    with _lock:
        if database not in _ready or database == ':memory:':
            c.executescript(SCHEMA)
            _ready.add(database)
    return c


def _one(database, sql, params=()):
    c = connect(database)
    try:
        row = c.execute(sql, params).fetchone()
        return dict(row) if row is not None else None
    finally:
        c.close()


def _write(database, sql, params=()):
    c = connect(database)
    try:
        with c:
            c.execute(sql, params)
    finally:
        c.close()


def remember_episode(ref, link, channel_id, title, show, database=None):
    _write(database,
           'INSERT INTO ai_episodes VALUES (?,?,?,?,?,?) ON CONFLICT(ref) DO UPDATE SET '
           'title=excluded.title, show=excluded.show, seen_at=excluded.seen_at',
           (ref, link, channel_id, str(title or '')[:500], str(show or '')[:300], time.time()))


def episode(ref, database=None):
    return _one(database, 'SELECT * FROM ai_episodes WHERE ref=?', (ref,))


def transcript(ref, database=None):
    return _one(database, 'SELECT * FROM ai_transcripts WHERE ref=?', (ref,))


def save_transcript(ref, text, source, cost_usd, database=None):
    _write(database, 'INSERT OR REPLACE INTO ai_transcripts VALUES (?,?,?,?,?)',
           (ref, text, source, float(cost_usd), time.time()))


def summary(ref, lang, database=None):
    return _one(database, 'SELECT * FROM ai_summaries WHERE ref=? AND lang=?', (ref, lang))


def save_summary(ref, lang, text, cost_usd, database=None):
    _write(database, 'INSERT OR REPLACE INTO ai_summaries VALUES (?,?,?,?,?)',
           (ref, lang, text, float(cost_usd), time.time()))


def enqueue(chat_id, ref, lang, database=None) -> tuple[int, bool]:
    """(request id, True if new). A tap on a summary already on its way is not a new one."""
    c = connect(database)
    try:
        c.isolation_level = None
        c.execute('BEGIN IMMEDIATE')
        try:
            row = c.execute("SELECT id FROM ai_requests WHERE chat_id=? AND ref=? AND lang=? "
                            "AND status IN ('pending','working')", (int(chat_id), ref, lang)).fetchone()
            if row is not None:
                c.execute('COMMIT')
                return int(row['id']), False
            cursor = c.execute("INSERT INTO ai_requests (chat_id,ref,lang,status,created_at) "
                               "VALUES (?,?,?,'pending',?)", (int(chat_id), ref, lang, time.time()))
            c.execute('COMMIT')
            return int(cursor.lastrowid), True
        except Exception:
            c.execute('ROLLBACK')
            raise
    finally:
        c.close()


def open_count(chat_id, database=None) -> int:
    """This chat's summaries on their way: they count toward its monthly quota."""
    row = _one(database, "SELECT COUNT(*) n FROM ai_requests WHERE chat_id=? "
                         "AND status IN ('pending','working')", (int(chat_id),))
    return int(row['n']) if row else 0


def claim(database=None, now=None):
    """Lease the oldest pending request (or one whose lease ran out), or None."""
    now = time.time() if now is None else now
    c = connect(database)
    try:
        c.isolation_level = None
        c.execute('BEGIN IMMEDIATE')
        try:
            row = c.execute(
                "SELECT * FROM ai_requests WHERE status='pending' "
                "OR (status='working' AND leased_until < ?) ORDER BY id LIMIT 1", (now,)).fetchone()
            if row is None:
                c.execute('COMMIT')
                return None
            c.execute("UPDATE ai_requests SET status='working', attempts=attempts+1, leased_until=? "
                      "WHERE id=?", (now + LEASE_SECONDS, row['id']))
            c.execute('COMMIT')
            claimed = dict(row)
            claimed['attempts'] += 1
            return claimed
        except Exception:
            c.execute('ROLLBACK')
            raise
    finally:
        c.close()


def finish(request_id, status, database=None):
    _write(database, 'UPDATE ai_requests SET status=?, leased_until=NULL WHERE id=?', (status, request_id))


def retry_or_fail(request, database=None) -> bool:
    """Back to pending while attempts remain; True when it failed for good."""
    failed = request['attempts'] >= MAX_ATTEMPTS
    finish(request['id'], 'failed' if failed else 'pending', database)
    return failed


def prune(database=None, now=None):
    cutoff = (time.time() if now is None else now) - KEEP_DAYS * 86400
    c = connect(database)
    try:
        with c:
            c.execute("DELETE FROM ai_requests WHERE status IN ('done','failed') AND created_at<?", (cutoff,))
            c.execute('DELETE FROM ai_summaries WHERE created_at<?', (cutoff,))
            c.execute('DELETE FROM ai_transcripts WHERE created_at<?', (cutoff,))
            c.execute('DELETE FROM ai_episodes WHERE seen_at<?', (cutoff,))
    finally:
        c.close()
