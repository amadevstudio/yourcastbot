"""Usage ledger: what each chat takes from the bot, one row per event.

Written where the work is done, read by the admin economics page and by
the free weekly limit:

- 'rec': an episode a user asked for was delivered (ref: the episode)
- 'circle': an episode delivered automatically (a tariff, or a channel)
- mb: what we downloaded for that delivery (0 when Telegram fetched the URL)
- 'ai': an AI summary, cost_usd what the APIs charged for it

Revenue is not here: payment_history has it. Rows older than a year go.
"""
import hashlib
import sqlite3
import threading
import time

from config import db_path
from db.connection import connect_sqlite

KEEP_DAYS = 400
WEEK_SECONDS = 7 * 86400

_ready = set()
_lock = threading.Lock()
SCHEMA = '''
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY, at REAL NOT NULL, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
    ref TEXT, mb REAL NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS usage_events_user ON usage_events(user_id, kind, at);
CREATE INDEX IF NOT EXISTS usage_events_at ON usage_events(at);
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


def episode_ref(link) -> str:
    """A short stable id of an episode: its enclosure URL, hashed."""
    return hashlib.sha1(str(link).encode('utf-8')).hexdigest()[:16]


def record_deliveries(chat_ids, kind, link, downloaded_mb=0.0, database=None, at=None):
    """One row per chat that got the episode. A download is shared by them."""
    chat_ids = sorted({int(chat_id) for chat_id in chat_ids})
    if not chat_ids:
        return
    share = float(downloaded_mb or 0) / len(chat_ids)
    at = time.time() if at is None else at
    ref = episode_ref(link)
    c = connect(database)
    try:
        with c:
            c.executemany('INSERT INTO usage_events (at,user_id,kind,ref,mb) VALUES (?,?,?,?,?)',
                          ((at, chat_id, kind, ref, share) for chat_id in chat_ids))
    finally:
        c.close()


def record_ai(chat_id, ref, cost_usd, database=None, at=None):
    c = connect(database)
    try:
        with c:
            c.execute('INSERT INTO usage_events (at,user_id,kind,ref,cost_usd) VALUES (?,?,?,?,?)',
                      (time.time() if at is None else at, int(chat_id), 'ai', ref, float(cost_usd)))
    finally:
        c.close()


def episodes_since(chat_id, kind, since, database=None) -> set:
    """Distinct episodes of `kind` delivered to the chat since `since` (epoch)."""
    c = connect(database)
    try:
        return {r[0] for r in c.execute(
            'SELECT DISTINCT ref FROM usage_events WHERE user_id=? AND kind=? AND at>=?',
            (int(chat_id), kind, since))}
    finally:
        c.close()


def oldest_since(chat_id, kind, since, database=None):
    """When the oldest counted event of the window happened, or None."""
    c = connect(database)
    try:
        row = c.execute('SELECT MIN(at) FROM usage_events WHERE user_id=? AND kind=? AND at>=?',
                        (int(chat_id), kind, since)).fetchone()
        return row[0] if row else None
    finally:
        c.close()


def per_user(since, until=None, database=None) -> dict:
    """{chat id: {'rec', 'circle', 'ai', 'mb', 'ai_usd'}} for events in [since, until)."""
    until = time.time() if until is None else until
    c = connect(database)
    try:
        rows = c.execute(
            'SELECT user_id, SUM(kind=\'rec\') rec, SUM(kind=\'circle\') circle, '
            'SUM(kind=\'ai\') ai, SUM(mb) mb, SUM(cost_usd) ai_usd '
            'FROM usage_events WHERE at>=? AND at<? GROUP BY user_id', (since, until))
        return {r['user_id']: {'rec': r['rec'] or 0, 'circle': r['circle'] or 0, 'ai': r['ai'] or 0,
                               'mb': r['mb'] or 0.0, 'ai_usd': r['ai_usd'] or 0.0} for r in rows}
    finally:
        c.close()


def prune(database=None, now=None):
    cutoff = (time.time() if now is None else now) - KEEP_DAYS * 86400
    c = connect(database)
    try:
        with c:
            c.execute('DELETE FROM usage_events WHERE at<?', (cutoff,))
    finally:
        c.close()
