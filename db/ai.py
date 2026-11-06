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

A request is a summary or, `kind` TRANSCRIPT, only the transcript (the
Transcript button, sent as a file): the same queue, quota and status line,
without the model call.

Prod SQLite is 3.31: no RETURNING, claims use BEGIN IMMEDIATE.
"""
import sqlite3
import threading
import time

from config import db_path
from db.connection import connect_sqlite

SUMMARY, TRANSCRIPT = 'summary', 'transcript'  # ai_requests.kind
LEASE_SECONDS = 30 * 60
MAX_ATTEMPTS = 2
KEEP_DAYS = 180

_ready = set()
_lock = threading.Lock()
SCHEMA = '''
CREATE TABLE IF NOT EXISTS ai_episodes (
    ref TEXT PRIMARY KEY, link TEXT NOT NULL, channel_id INTEGER, title TEXT NOT NULL,
    show TEXT NOT NULL, seen_at REAL NOT NULL, seconds INTEGER NOT NULL DEFAULT 0, descr TEXT
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

CREATE TABLE IF NOT EXISTS voice_batches (
    ref TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'collecting',
    created_at REAL NOT NULL, expires_at REAL NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
    selected TEXT, message_id INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS voice_batch_open ON voice_batches(chat_id) WHERE state='collecting';
CREATE TABLE IF NOT EXISTS voice_items (
    id INTEGER PRIMARY KEY, batch TEXT NOT NULL, ref TEXT NOT NULL, message_id INTEGER NOT NULL,
    seconds INTEGER NOT NULL, bytes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'downloading',
    UNIQUE(batch, message_id)
);
CREATE INDEX IF NOT EXISTS voice_items_batch ON voice_items(batch, message_id);
CREATE TABLE IF NOT EXISTS voice_runs (
    request_id INTEGER PRIMARY KEY, batch TEXT NOT NULL, output TEXT NOT NULL, mode TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voice_run_items (
    run INTEGER NOT NULL, item INTEGER NOT NULL, request_id INTEGER NOT NULL,
    PRIMARY KEY(run, item)
);
'''


def connect(database=None):
    database = db_path if database is None else database
    c = connect_sqlite(database)
    c.row_factory = sqlite3.Row
    with _lock:
        if database not in _ready or database == ':memory:':
            c.executescript(SCHEMA)
            # descr: the feed's description, shown by "Show notes" under a brief episode
            _add_column(c, 'ai_episodes', 'descr', 'descr TEXT')
            _add_column(c, 'ai_episodes', 'owner_chat', 'owner_chat INTEGER')
            _add_column(c, 'ai_episodes', 'expires_at', 'expires_at REAL')
            columns = {row[1] for row in c.execute('PRAGMA table_info(ai_requests)')}
            # reply_to: the audio message the summary answers (its times play the episode from there);
            # auto: queued for a new episode (app/service/ai/auto.py), after every tap
            # status_message: the line "downloading... transcribing..." a tap got, edited into the summary
            # kind: SUMMARY, or TRANSCRIPT (the transcript alone, as a file)
            # paid_seconds: the audio this request had transcribed by the paid model (its hours per plan)
            for column, sql in (('reply_to', 'reply_to INTEGER'), ('auto', 'auto INTEGER NOT NULL DEFAULT 0'),
                                ('status_message', 'status_message INTEGER'),
                                ('kind', "kind TEXT NOT NULL DEFAULT '%s'" % SUMMARY),
                                ('paid_seconds', 'paid_seconds INTEGER NOT NULL DEFAULT 0')):
                if column in columns:
                    continue
                try:
                    c.execute('ALTER TABLE ai_requests ADD COLUMN ' + sql)
                except sqlite3.OperationalError as e:  # another role added it first
                    if 'duplicate column' not in str(e):
                        raise
            _ready.add(database)
    return c


def _add_column(c, table, column, sql):
    if column in {row[1] for row in c.execute('PRAGMA table_info(%s)' % table)}:
        return
    try:
        c.execute('ALTER TABLE %s ADD COLUMN %s' % (table, sql))
    except sqlite3.OperationalError as e:  # another role added it first
        if 'duplicate column' not in str(e):
            raise


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


DESCR_CHARS = 40000


def remember_episode(ref, link, channel_id, title, show, seconds=0, database=None, descr=None):
    """`seconds`: the episode's length as its feed gives it (itunes:duration), 0 if unknown;
    `descr`: its description as the feed gives it (kept unless a new one is given)."""
    _write(database,
           'INSERT INTO ai_episodes (ref, link, channel_id, title, show, seen_at, seconds, descr) '
           'VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(ref) DO UPDATE SET '
           'title=excluded.title, show=excluded.show, seen_at=excluded.seen_at, '
           'seconds=CASE WHEN excluded.seconds>0 THEN excluded.seconds ELSE ai_episodes.seconds END, '
           'descr=COALESCE(excluded.descr, ai_episodes.descr)',
           (ref, link, channel_id, str(title or '')[:500], str(show or '')[:300], time.time(),
            max(int(seconds or 0), 0), str(descr)[:DESCR_CHARS] if descr else None))


def episode(ref, database=None):
    """The episode with its channel's feed URL (`feed_url`, None when the channel is gone) and
    `channel_found` (the channel's id while it is in the database)."""
    return _one(database, 'SELECT e.*, c.rss_link feed_url, c.id channel_found FROM ai_episodes e '
                          'LEFT JOIN channels c ON c.id = e.channel_id WHERE e.ref=?', (ref,))


def accessible_episode(ref, chat_id, database=None):
    """Private media are visible only to their owner, including every callback and worker."""
    found = episode(ref, database)
    if found and found.get('owner_chat') is not None:
        if found['owner_chat'] != int(chat_id) or (found.get('expires_at') or 0) <= time.time():
            return None
    return found


def remember_voice(ref, chat_id, title, seconds, database=None):
    _write(database, 'INSERT OR IGNORE INTO ai_episodes '
           '(ref,link,title,show,seen_at,seconds,owner_chat,expires_at) VALUES (?,?,?,?,?,?,?,?)',
           (ref, '', title, '', time.time(), seconds, int(chat_id), time.time() + 7 * 86400))


def prune_voices(database=None, now=None):
    now = time.time() if now is None else now
    c = connect(database)
    try:
        with c:
            for table in ('ai_transcripts', 'ai_summaries'):
                c.execute('DELETE FROM ' + table + ' WHERE ref IN '
                          '(SELECT ref FROM ai_episodes WHERE owner_chat IS NOT NULL AND expires_at<=?)', (now,))
            c.execute('DELETE FROM ai_episodes WHERE owner_chat IS NOT NULL AND expires_at<=?', (now,))
    finally:
        c.close()


def transcript(ref, database=None):
    return _one(database, 'SELECT * FROM ai_transcripts WHERE ref=?', (ref,))


def save_transcript(ref, text, source, cost_usd, seconds=0.0, database=None):
    """`seconds`: the audio Whisper transcribed, 0 for a transcript from the feed."""
    _write(database, 'INSERT OR REPLACE INTO ai_transcripts VALUES (?,?,?,?,?,?)',
           (ref, text, source, float(cost_usd), time.time(), float(seconds or 0)))


def channel_transcripts(channel_id, database=None) -> list[dict]:
    """The transcripts of a channel's episodes someone already paid for (ref, link, title, text),
    newest first: questions about the whole show read them, nothing new is transcribed."""
    c = connect(database)
    try:
        return [dict(row) for row in c.execute(
            'SELECT e.ref, e.link, e.title, t.text FROM ai_episodes e JOIN ai_transcripts t ON t.ref = e.ref '
            'WHERE e.channel_id=? ORDER BY e.seen_at DESC', (int(channel_id),))]
    finally:
        c.close()


def summary(ref, lang, database=None):
    return _one(database, 'SELECT * FROM ai_summaries WHERE ref=? AND lang=?', (ref, lang))


def save_summary(ref, lang, text, cost_usd, database=None):
    _write(database, 'INSERT OR REPLACE INTO ai_summaries VALUES (?,?,?,?,?)',
           (ref, lang, text, float(cost_usd), time.time()))


def gist(channel_id, title, database=None, limit=200):
    """The first line of a summary someone already made of this episode (the episode's own
    language first), cut to `limit` at a word; None when there is none. For the digest:
    a summary made is free to show, nothing new is made for it."""
    row = _one(database, "SELECT s.text FROM ai_episodes e JOIN ai_summaries s ON s.ref = e.ref "
                         "WHERE e.channel_id=? AND e.title=? "
                         "ORDER BY s.lang='original' DESC, s.created_at DESC LIMIT 1",
               (int(channel_id), str(title or '')[:500]))
    lines = str(row['text']).strip().splitlines() if row else []
    first = lines[0].strip() if lines else ''
    if len(first) > limit:
        first = first[:limit].rsplit(' ', 1)[0].rstrip(',;:') + '…'
    return first or None


def enqueue(chat_id, ref, lang, seconds, database=None, reply_to=None, auto=False,
            status_message=None, kind=SUMMARY) -> tuple[int, bool]:
    """(request id, True if new), charged `seconds` of the quota. A tap on a summary
    (or a transcript) already on its way is not a new one. `reply_to`: the audio message the
    summary answers; `auto`: not asked for (a new episode), it waits for every tap;
    `status_message`: the status line the worker edits as it goes, and into the summary."""
    c = connect(database)
    try:
        c.isolation_level = None
        c.execute('BEGIN IMMEDIATE')
        try:
            row = c.execute("SELECT id FROM ai_requests WHERE chat_id=? AND ref=? AND lang=? AND kind=? "
                            "AND status IN ('pending','working')", (int(chat_id), ref, lang, kind)).fetchone()
            if row is not None:
                if not auto:  # a tap on one queued automatically: it is wanted now
                    c.execute('UPDATE ai_requests SET auto=0, reply_to=COALESCE(reply_to, ?), '
                              'status_message=COALESCE(status_message, ?) WHERE id=?',
                              (int(reply_to) if reply_to else None,
                               int(status_message) if status_message else None, row['id']))
                c.execute('COMMIT')
                return int(row['id']), False
            cursor = c.execute("INSERT INTO ai_requests (chat_id,ref,lang,status,created_at,seconds,reply_to,auto,"
                               "status_message,kind) VALUES (?,?,?,'pending',?,?,?,?,?,?)",
                               (int(chat_id), ref, lang, time.time(), int(seconds),
                                int(reply_to) if reply_to else None, int(bool(auto)),
                                int(status_message) if status_message else None, kind))
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


def paid_seconds_used(chat_id, since, database=None) -> int:
    """The audio the paid model transcribed for this chat's requests since `since`."""
    row = _one(database, "SELECT COALESCE(SUM(paid_seconds),0) s FROM ai_requests WHERE chat_id=? "
                         "AND created_at>=? AND status IN ('pending','working','done')", (int(chat_id), since))
    return int(row['s']) if row else 0


def note_paid_seconds(request_id, seconds, database=None):
    """This request had `seconds` of audio transcribed by the paid model."""
    _write(database, 'UPDATE ai_requests SET paid_seconds=? WHERE id=?', (int(seconds), request_id))


def audio_paid(chat_id, ref, database=None, exclude=None, done_only=False) -> bool:
    """Has this chat been charged this episode's audio already: a request of its own for the episode
    charged seconds, on its way or done (`done_only`: done), `exclude` (a request id) left out? Then
    its transcript is paid for, and a summary or a transcript of the same episode costs it no more hours."""
    statuses = "('done')" if done_only else "('pending','working','done')"
    row = _one(database, "SELECT 1 FROM ai_requests WHERE chat_id=? AND ref=? AND seconds>0 AND id!=? "
                         "AND status IN %s LIMIT 1" % statuses,
               (int(chat_id), ref, int(exclude or 0)))
    return row is not None


def claim(database=None, now=None):
    """Lease the oldest pending request (or one whose lease ran out), taps before
    automatic ones, or None.
    `ui_lang`: the user's interface language, for a notice (the summary's may be the episode's)."""
    now = time.time() if now is None else now
    c = connect(database)
    try:
        c.isolation_level = None
        c.execute('BEGIN IMMEDIATE')
        try:
            row = c.execute(
                "SELECT r.*, u.lang ui_lang FROM ai_requests r LEFT JOIN users u ON u.telegramId = r.chat_id "
                "WHERE r.status='pending' OR (r.status='working' AND r.leased_until < ?) "
                "ORDER BY r.auto, r.id LIMIT 1", (now,)).fetchone()
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
