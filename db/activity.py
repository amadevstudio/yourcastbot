"""When a chat last used the bot: a message, a tap or an inline query of its own.

Written by the incoming path (`touch`, from default_middleware.get_user), at most once an hour per
chat per process: a write per tap would be a write per tap. What the bot sends (episodes, the digest,
reminders) is not use.

`last_used` is the latest of that, the chat's registration (`users.created_at`) and what the usage
ledger has from the chat's own asking (clicks, summaries, transcripts, questions; never `circle`,
the automatic files). The ledger began on 2026-10-21 and this table on 2026-11-22: use before both
is not known, and a chat with nothing since reads as not used.

The weekly digest reads it (app/jobs/nosub_digest.py): a chat that has not used the bot in
`DORMANT_DAYS` gets it at most once a year. Never fails the caller.
Lock: python db/test_activity.py
"""
import datetime
import sqlite3
import threading
import time

from config import db_path
from db.connection import connect_sqlite
from lib.tools.logger import logger

TOUCH_EVERY_SECONDS = 3600
ASKED_KINDS = ('rec', 'ai', 'transcript', 'ask')  # the ledger's rows a chat asked for

_ready = set()
_lock = threading.Lock()
_touched = {}  # (database, telegram id) -> when this process last wrote it
SCHEMA = '''
CREATE TABLE IF NOT EXISTS user_activity (
    user_telegram_id INTEGER PRIMARY KEY, at REAL NOT NULL
);
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


def touch(telegram_id, now=None, database=None) -> None:
    """The chat used the bot now. Private chats only (a positive id); never raises."""
    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        return
    if telegram_id <= 0:
        return
    now = time.time() if now is None else now
    key = (database, telegram_id)
    with _lock:
        if now - _touched.get(key, 0) < TOUCH_EVERY_SECONDS:
            return
        _touched[key] = now
    try:
        c = connect(database)
        try:
            with c:
                c.execute('INSERT INTO user_activity (user_telegram_id, at) VALUES (?, ?) '
                          'ON CONFLICT(user_telegram_id) DO UPDATE SET at = MAX(at, excluded.at)',
                          (telegram_id, now))
        finally:
            c.close()
    except Exception as e:
        with _lock:
            _touched.pop(key, None)
        logger.warn("activity touch:", type(e).__name__, e)


def _created_at(value):
    if not value:
        return None
    try:
        return datetime.datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return None


def last_used(telegram_id, database=None):
    """Epoch seconds the chat last used the bot, or None when nothing says it ever did."""
    c = connect(database)
    try:
        times = []
        row = c.execute('SELECT at FROM user_activity WHERE user_telegram_id = ?', (int(telegram_id),)).fetchone()
        if row is not None:
            times.append(row['at'])
        row = c.execute('SELECT created_at FROM users WHERE telegramId = ? ORDER BY id DESC LIMIT 1',
                        (int(telegram_id),)).fetchone()
        if row is not None and _created_at(row['created_at']) is not None:
            times.append(_created_at(row['created_at']))
        if c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'usage_events'").fetchone():
            row = c.execute('SELECT MAX(at) at FROM usage_events WHERE user_id = ? AND kind IN (%s)'
                            % ','.join('?' * len(ASKED_KINDS)), (int(telegram_id),) + ASKED_KINDS).fetchone()
            if row is not None and row['at'] is not None:
                times.append(row['at'])
        return max(times) if times else None
    finally:
        c.close()
