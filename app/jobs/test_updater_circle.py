# -*- coding: utf-8 -*-
"""The real updater loop: one circle, paced per host, then the rest. Temp DB, no Telegram.

podcastsUpdater.main() runs against a temp database with three polled
channels (two on one host, one on another). The channel fetch is a stub that
answers "fetched", the clock and the sleeps are fake, and the loop is stopped
at the rest after the first circle. Needs the bot's requirements (like
test_updater_not_modified.py); the CD gate locks the shape in
test_circle_pace.py. Run from the repo root: python app/jobs/test_updater_circle.py
"""
import os
import sys
import tempfile
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402

_PROD_DB = config.db_path
config.db_path = os.path.join(tempfile.mkdtemp(prefix="yourcast_circle_"), "t.db")
if os.path.abspath(config.db_path) == os.path.abspath(_PROD_DB):
    raise AssertionError("refusing to use production yourcast.db")

_telethon = types.ModuleType("agent.bot_telethon")
_telethon.thobot_session_handler = ""
sys.modules["agent.bot_telethon"] = _telethon

from db.connection import connect_sqlite  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402
import app.jobs.podcastsUpdater as updater  # noqa: E402
from app.jobs import circle_pace  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


class _Stop(BaseException):
    """Ends the endless loop from inside the rest."""


class _Client:
    def __init__(self, *args, **kwargs):
        pass

    def start(self, **kwargs):
        return self

    def disconnect(self):
        pass


class _World:
    def __init__(self):
        self.now = 5000.0
        self.slept = []
        self.visited = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 3))
        self.now += seconds


class _Db(SQLighter):
    """The real poll query and listener lists; no Telegram-channel subscriptions in this fixture."""

    def getTgChannelSubConnectionsByPodcast(self, *args, **kwargs):
        return []


def _setup_db():
    conn = connect_sqlite(config.db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE,
                lang TEXT, deleted_at TEXT, bitrate INTEGER);
            CREATE TABLE IF NOT EXISTS tariffs (id INTEGER PRIMARY KEY, level INTEGER,
                price INTEGER, notify_count INTEGER, compression INTEGER, channel_control INTEGER);
            CREATE TABLE IF NOT EXISTS user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER,
                tariff_id INTEGER, balance INTEGER, notify_count INTEGER, time_left INTEGER);
            CREATE TABLE IF NOT EXISTS user_channel_cs (id INTEGER PRIMARY KEY,
                user_telegram_id INTEGER, channel_id INTEGER, last_guid TEXT,
                last_date TEXT, notify INTEGER);
            CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, itunes_id INTEGER,
                name TEXT, rss_link TEXT, last_guid TEXT, last_date TEXT);
            CREATE TABLE IF NOT EXISTS tg_channels (id INTEGER PRIMARY KEY, user_id INTEGER,
                tg_id INTEGER, active INTEGER);
            CREATE TABLE IF NOT EXISTS subscription_to_tg_channel_cs (id INTEGER PRIMARY KEY,
                user_channel_cs_id INTEGER, tg_channel_id INTEGER);
            DELETE FROM users; DELETE FROM user_tariff_cs; DELETE FROM user_channel_cs;
            DELETE FROM channels;
            INSERT INTO users (id, telegramId, lang) VALUES (1, 9001, 'en');
            INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left)
                VALUES (1, 0, 0, 0, 0);
        """)
        for channel_id, link in ((1, "http://a.example/one.xml"), (2, "http://a.example/two.xml"),
                                 (3, "http://b.example/three.xml")):
            conn.execute("INSERT INTO channels (id, name, rss_link) VALUES (?, ?, ?)",
                         (channel_id, "Show %d" % channel_id, link))
            conn.execute("INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) "
                         "VALUES (9001, ?, 1)", (channel_id,))
        conn.commit()
    finally:
        conn.close()


def _run(world, fetch_outcomes, circle_seconds=None):
    """main() until the first rest after a circle; returns the rest in seconds."""
    updater.TelegramClient = _Client
    updater.SQLighter = _Db
    updater.server = True
    updater.send_message_to_creator = lambda *a, **k: None
    updater.pending_count = lambda: 0
    updater.time = types.SimpleNamespace(sleep=world.sleep, time=lambda: world.now, ctime=lambda: "now")
    updater.HostPacer = lambda: circle_pace.HostPacer(clock=world.clock, sleep=world.sleep)

    def fake_send(channel, connections, **kwargs):
        world.visited.append(channel['id'])
        world.now += 0.2  # the fetch itself
        return updater.ChannelUpdateResult(False, fetch_outcomes.get(channel['id'], 'fetched'))

    updater.send_new_records_by_channel = fake_send
    if circle_seconds is not None:
        real = updater.mark_circle_finished
        updater.mark_circle_finished = lambda *a, **k: {**real(*a, **k), 'duration_sec': circle_seconds}

    rests = []

    def rest(seconds):
        rests.append(seconds)
        raise _Stop()

    # the rest after the circle is the only sleep that ends the test
    original_sleep = world.sleep

    def sleep(seconds):
        if world.in_rest:
            rest(seconds)
        if len(world.slept) > 100:
            raise AssertionError("the updater never rested after a circle (endless circles)")
        original_sleep(seconds)

    world.in_rest = False
    log = updater.logger.log

    def logged(*args, **kwargs):
        if args and args[0] == "Circle rest, sec:":
            world.in_rest = True
        return log(*args, **kwargs)

    updater.logger.log = logged
    updater.time.sleep = sleep
    try:
        updater.main(10)
    except _Stop:
        pass
    finally:
        updater.logger.log = log
    return rests[0]


def main():
    _setup_db()

    world = _World()
    _run(world, {})
    _assert_eq(world.visited, [1, 2, 3], "the circle visits every polled channel in order")
    # channel 1: no wait; channel 2 (the same host) waits 6 s after the end of the
    # fetch of 1; channel 3 (another host) only the 1 s between two fetches
    _assert_eq(world.slept[:2], [6.0, 1.0], "the same host waits 6 s, another host only the 1 s gap")
    _assert_eq(world.slept.count(6.0), 1, "the 6 s is paid once, by the host that was fetched twice")

    # A circle that took 10 minutes rests until the hour; a long one rests the old 10 minutes.
    for seconds, expected, label in ((600, 3000, "a 10 min circle rests until the hour"),
                                     (3500, 600, "a circle as long as before rests the old 10 min")):
        _setup_db()
        world = _World()
        _assert_eq(_run(world, {}, circle_seconds=seconds), expected, label)

    # 304s and skipped channels are never paced
    _setup_db()
    world = _World()
    _run(world, {1: 'not_modified', 2: 'not_modified', 3: 'skipped'})
    _assert_eq(world.visited, [1, 2, 3], "304 and skipped channels are visited too")
    _assert_eq(world.slept, [], "and cost no sleep at all")

    print("all updater circle checks passed")


if __name__ == "__main__":
    main()
