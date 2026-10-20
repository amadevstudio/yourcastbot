"""Episode references for the weekly digest.

No audio cache: "Listen" in a digest is the ordinary rec button and its
delivery policy. Snapshots nothing refers to expire in 90 days.
"""
import json
import sqlite3
import threading
import time
import uuid

from config import db_path
from db.connection import connect_sqlite

_ready = set()
_lock = threading.Lock()
SCHEMA = '''
CREATE TABLE IF NOT EXISTS listening_episodes (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, episode_hash TEXT NOT NULL,
    title TEXT NOT NULL, show_name TEXT NOT NULL, callback_json TEXT NOT NULL,
    seen_at REAL NOT NULL, UNIQUE(source,episode_hash)
);
CREATE TABLE IF NOT EXISTS channel_episode (
    channel_id INTEGER PRIMARY KEY, episode_id INTEGER NOT NULL, episode_cursor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS digest_episodes (
    user_telegram_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, episode_id INTEGER NOT NULL,
    revision TEXT NOT NULL, created_at REAL NOT NULL,
    PRIMARY KEY(user_telegram_id,channel_id)
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


def remember(title, show_name, callback, database=None, channel_id=None, cursor=None):
    """Callbacks contain only a podcast identifier and hash/position, never arbitrary URLs."""
    source = ('id:' + str(callback['id']) if callback.get('id') is not None
              else 'itunes:' + str(callback['iid']))
    episode_hash = callback['dh_n'].split('_')[0]
    c = connect(database)
    try:
        with c:
            c.execute('INSERT INTO listening_episodes '
                '(source,episode_hash,title,show_name,callback_json,seen_at) VALUES (?,?,?,?,?,?) '
                'ON CONFLICT(source,episode_hash) DO UPDATE SET title=excluded.title,'
                'show_name=excluded.show_name,callback_json=excluded.callback_json,seen_at=excluded.seen_at',
                (source, episode_hash, str(title)[:1000], str(show_name)[:500],
                 json.dumps(callback, separators=(',', ':')), time.time()))
            row = c.execute('SELECT id FROM listening_episodes WHERE source=? AND episode_hash=?',
                            (source, episode_hash)).fetchone()
            if channel_id is not None and cursor is not None:
                c.execute('INSERT INTO channel_episode VALUES (?,?,?) ON CONFLICT(channel_id) '
                          'DO UPDATE SET episode_id=excluded.episode_id,episode_cursor=excluded.episode_cursor',
                          (channel_id, row['id'], cursor))
            return row['id']
    finally:
        c.close()


def flag_digest(chat_ids, channel_id, cursor, database=None):
    """One latest episode per show. The cursor must match, including on a 304."""
    c = connect(database)
    try:
        with c:
            row = c.execute('SELECT episode_id FROM channel_episode WHERE channel_id=? '
                            'AND episode_cursor=?', (channel_id, cursor)).fetchone()
            if row is None:
                return
            c.executemany('INSERT INTO digest_episodes VALUES (?,?,?,?,?) '
                'ON CONFLICT(user_telegram_id,channel_id) DO UPDATE SET '
                'episode_id=excluded.episode_id,revision=excluded.revision,created_at=excluded.created_at',
                ((chat_id, channel_id, row['episode_id'], uuid.uuid4().hex, time.time()) for chat_id in chat_ids))
    finally:
        c.close()


def digest(chat_id, database=None):
    c = connect(database)
    try:
        # Re-read subscriptions/notify at send time: an opt-out must take effect.
        return [dict(r) for r in c.execute('SELECT e.*,d.channel_id,d.revision '
            'FROM digest_episodes d JOIN listening_episodes e ON e.id=d.episode_id '
            'JOIN user_channel_cs s ON s.channel_id=d.channel_id AND s.user_telegram_id=d.user_telegram_id '
            'WHERE d.user_telegram_id=? AND s.notify=1 ORDER BY d.created_at DESC,d.channel_id LIMIT 5',
            (chat_id,))]
    finally:
        c.close()


def has_digest(chat_id, database=None):
    """Distinguish migrated generic flags from episodes no longer opted into."""
    c = connect(database)
    try:
        return c.execute('SELECT 1 FROM digest_episodes WHERE user_telegram_id=? LIMIT 1',
                         (chat_id,)).fetchone() is not None
    finally:
        c.close()


def ack_digest(chat_id, entries, database=None):
    """A newly queued episode survives ACK of an older snapshot sent concurrently."""
    c = connect(database)
    try:
        with c:
            c.executemany('DELETE FROM digest_episodes WHERE user_telegram_id=? AND channel_id=? '
                          'AND revision=?', ((chat_id, e['channel_id'], e['revision']) for e in entries))
    finally:
        c.close()


def prune(database=None, now=None):
    cutoff = (time.time() if now is None else now) - 90 * 86400
    c = connect(database)
    try:
        with c:
            c.execute('DELETE FROM digest_episodes WHERE created_at<?', (cutoff,))
            c.execute('DELETE FROM listening_episodes WHERE seen_at<? '
                'AND NOT EXISTS(SELECT 1 FROM channel_episode e WHERE e.episode_id=listening_episodes.id) '
                'AND NOT EXISTS(SELECT 1 FROM digest_episodes d WHERE d.episode_id=listening_episodes.id)', (cutoff,))
    finally:
        c.close()
