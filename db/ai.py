"""AI summaries: the episodes a summary can be asked for, cached transcripts
and summaries, and the queue the jobs process drains.

An episode is known by its ref (db.usage.episode_ref of the enclosure URL):
the sender remembers it when it delivers the file, the button carries only
the ref. A transcript is made once per episode; a summary once per episode
and language, and then it is free for everyone who asks.

Quotas are hours of audio: a request carries the seconds it is charged
(the feed's length when asked, what Whisper measured once transcribed, 0 when
someone else's summary served it), and a chat's use is the sum of its
requests that are on their way or done.

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
    show TEXT NOT NULL, seen_at REAL NOT NULL, seconds INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ai_transcripts (
    ref TEXT PRIMARY KEY, text TEXT NOT NULL, source TEXT NOT NULL,
    cost_usd REAL NOT NULL, created_at REAL NOT NULL, seconds REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ai_summaries (
    ref TEXT NOT NULL, lang TEXT NOT NULL, text TEXT NOT NULL,
    cost_usd REAL NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (ref, lang)
);
CREATE TABLE IF NOT EXISTS ai_requests (
    id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, ref TEXT NOT NULL, lang TEXT NOT NULL,
    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, leased_until REAL, seconds INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ai_requests_chat ON ai_requests(chat_id, created_at);
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


def remember_episode(ref, link, channel_id, title, show, seconds=0, database=None):
    """`seconds`: the episode's length as its feed gives it (itunes:duration), 0 if unknown."""
    _write(database,
           'INSERT INTO ai_episodes VALUES (?,?,?,?,?,?,?) ON CONFLICT(ref) DO UPDATE SET '
           'title=excluded.title, show=excluded.show, seen_at=excluded.seen_at, '
           'seconds=CASE WHEN excluded.seconds>0 THEN excluded.seconds ELSE ai_episodes.seconds END',
           (ref, link, channel_id, str(title or '')[:500], str(show or '')[:300], time.time(),
            max(int(seconds or 0), 0)))


def episode(ref, database=None):
    """The episode with its channel's feed URL (`feed_url`, None when the channel is gone)."""
    return _one(database, 'SELECT e.*, c.rss_link feed_url FROM ai_episodes e '
                          'LEFT JOIN channels c ON c.id = e.channel_id WHERE e.ref=?', (ref,))


def transcript(ref, database=None):
    return _one(database, 'SELECT * FROM ai_transcripts WHERE ref=?', (ref,))


def save_transcript(ref, text, source, cost_usd, seconds=0.0, database=None):
    """`seconds`: the audio Whisper transcribed, 0 for a transcript from the feed."""
    _write(database, 'INSERT OR REPLACE INTO ai_transcripts VALUES (?,?,?,?,?,?)',
           (ref, text, source, float(cost_usd), time.time(), float(seconds or 0)))


def summary(ref, lang, database=None):
    return _one(database, 'SELECT * FROM ai_summaries WHERE ref=? AND lang=?', (ref, lang))


def save_summary(ref, lang, text, cost_usd, database=None):
    _write(database, 'INSERT OR REPLACE INTO ai_summaries VALUES (?,?,?,?,?)',
           (ref, lang, text, float(cost_usd), time.time()))


def enqueue(chat_id, ref, lang, seconds, database=None) -> tuple[int, bool]:
    """(request id, True if new), charged `seconds` of the quota. A tap on a summary
    already on its way is not a new one."""
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
            cursor = c.execute("INSERT INTO ai_requests (chat_id,ref,lang,status,created_at,seconds) "
                               "VALUES (?,?,?,'pending',?,?)",
                               (int(chat_id), ref, lang, time.time(), int(seconds)))
            c.execute('COMMIT')
            return int(cursor.lastrowid), True
        except Exception:
            c.execute('ROLLBACK')
            raise
    finally:
        c.close()


def seconds_used(chat_id, since, database=None) -> int:
    """The audio this chat's requests since `since` are charged: done and on their way, not failed."""
    row = _one(database, "SELECT COALESCE(SUM(seconds),0) s FROM ai_requests WHERE chat_id=? "
                         "AND created_at>=? AND status IN ('pending','working','done')",
               (int(chat_id), since))
    return int(row['s']) if row else 0


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


def finish(request_id, status, seconds=None, database=None):
    """`seconds`: what the request is charged in the end, when it differs from the estimate."""
    _write(database, 'UPDATE ai_requests SET status=?, leased_until=NULL, seconds=COALESCE(?,seconds) '
                     'WHERE id=?', (status, None if seconds is None else int(seconds), request_id))


def retry_or_fail(request, database=None) -> bool:
    """Back to pending while attempts remain; True when it failed for good."""
    failed = request['attempts'] >= MAX_ATTEMPTS
    finish(request['id'], 'failed' if failed else 'pending', database=database)
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
