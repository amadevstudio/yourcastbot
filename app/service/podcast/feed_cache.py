# -*- coding: utf-8 -*-
"""The last copy of a feed a person opened: the podcast page, the episode list and
a click on an episode read the same feed one after another.

Each of them used to download the whole feed: 12 s for a 66 MB feed of 10k
episodes, 1.8 s for a slow host, every tap. Now (rss.get_rss_root_with_status,
cached=True; interactive paths only, never the updater or feed recovery):

- a copy checked less than FRESH_SECONDS ago is read from disk, no network;
- an older one is asked for with its ETag / Last-Modified: a 304 reads it from
  disk, anything else is the usual fetch, whose result replaces the copy;
- any other full fetch of the feed (the updater found a new version, a manual
  refresh, feed recovery) drops the copy: a new episode is never hidden
  behind it, so the digest's "Listen" finds it.

Copies live in work_dir/feed_cache, at most TOTAL_BYTES (the least recently
used go first), and only while the disk keeps MIN_FREE_BYTES plus room for
episode downloads (lib/system/disk_budget.py): the cache never competes with
SQLite or an episode for space. A copy that does not parse is dropped.
"""
import hashlib
import os
import shutil
import sqlite3
import threading
import time
from typing import NamedTuple

from config import db_path, work_dir
from db.connection import connect_sqlite
from lib.system.disk_budget import MB, MIN_FREE_BYTES

FRESH_SECONDS = 5 * 60  # page -> episode list -> episode
TOTAL_BYTES = 300 * MB
DOWNLOAD_ROOM_BYTES = 512 * MB  # left for episode downloads, on top of MIN_FREE_BYTES
DIRECTORY = os.path.join(work_dir, 'feed_cache')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS feed_cache (
    url TEXT PRIMARY KEY, file TEXT NOT NULL, size INTEGER NOT NULL,
    etag TEXT, last_modified TEXT, checked_at REAL NOT NULL, used_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS feed_cache_used ON feed_cache(used_at);
'''

_ready = set()
_lock = threading.Lock()


class Entry(NamedTuple):
    content: bytes
    etag: str | None
    last_modified: str | None
    fresh: bool


def _connect(database=None):
    database = db_path if database is None else database
    c = connect_sqlite(database)
    c.row_factory = sqlite3.Row
    with _lock:
        if database not in _ready:
            c.executescript(SCHEMA)
            _ready.add(database)
    return c


def _file_name(url) -> str:
    return hashlib.sha1(str(url).encode('utf-8')).hexdigest() + '.xml'


def get(url, now=None, database=None, directory=DIRECTORY) -> Entry | None:
    now = time.time() if now is None else now
    c = _connect(database)
    try:
        row = c.execute('SELECT * FROM feed_cache WHERE url=?', (url,)).fetchone()
        if row is None:
            return None
        try:
            with open(os.path.join(directory, row['file']), 'rb') as f:
                content = f.read()
        except OSError:
            with c:
                c.execute('DELETE FROM feed_cache WHERE url=?', (url,))
            return None
        with c:
            c.execute('UPDATE feed_cache SET used_at=? WHERE url=?', (now, url))
        return Entry(content, row['etag'], row['last_modified'], now - row['checked_at'] < FRESH_SECONDS)
    finally:
        c.close()


def touch(url, now=None, database=None):
    """The host answered 304: the copy is the feed as of now."""
    c = _connect(database)
    try:
        with c:
            c.execute('UPDATE feed_cache SET checked_at=? WHERE url=?', (time.time() if now is None else now, url))
    finally:
        c.close()


def put(url, content, etag=None, last_modified=None, now=None, database=None,
        directory=DIRECTORY, disk_free=None) -> bool:
    """Keep this copy (False when the disk has no room for it: the old copy goes too)."""
    now = time.time() if now is None else now
    size = len(content)
    os.makedirs(directory, exist_ok=True)
    free = (disk_free or (lambda: shutil.disk_usage(directory).free))()
    if size > TOTAL_BYTES or free - size < MIN_FREE_BYTES + DOWNLOAD_ROOM_BYTES:
        forget(url, database=database, directory=directory)
        return False
    name = _file_name(url)
    temporary = os.path.join(directory, name + '.tmp%d' % threading.get_ident())
    with open(temporary, 'wb') as f:
        f.write(content)
    os.replace(temporary, os.path.join(directory, name))
    c = _connect(database)
    try:
        with c:
            c.execute('INSERT OR REPLACE INTO feed_cache VALUES (?,?,?,?,?,?,?)',
                      (url, name, size, etag, last_modified, now, now))
            _evict(c, directory)
    finally:
        c.close()
    return True


def forget(url, database=None, directory=DIRECTORY):
    c = _connect(database)
    try:
        row = c.execute('SELECT file FROM feed_cache WHERE url=?', (url,)).fetchone()
        if row is not None:
            with c:
                c.execute('DELETE FROM feed_cache WHERE url=?', (url,))
    finally:
        c.close()
    if row is not None:
        _remove(os.path.join(directory, row['file']))


def _evict(c, directory):
    total = c.execute('SELECT COALESCE(SUM(size), 0) FROM feed_cache').fetchone()[0]
    for row in c.execute('SELECT url, file, size FROM feed_cache ORDER BY used_at').fetchall():
        if total <= TOTAL_BYTES:
            break
        c.execute('DELETE FROM feed_cache WHERE url=?', (row['url'],))
        _remove(os.path.join(directory, row['file']))
        total -= row['size']


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
