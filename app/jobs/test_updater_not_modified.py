# -*- coding: utf-8 -*-
"""A 304 does not leave a paying listener behind. Temp DB, local feed.

Real send_new_records_by_channel against a local RSS server that honors
If-None-Match. Only outbox.enqueue is captured (no Telegram).

A manual refresh parses the feed for one chat and stores the new ETag for
the channel; the next circle got 304 and the other payers waited for the
feed to change again (a day for a daily show). Now a 304 with a paid
cursor behind the channel refetches without validators.

Needs the bot's requirements (like test_digest_outbox.py); the CD gate
locks the decision in app/jobs/test_feed_health.py.
Run from the repo root: python app/jobs/test_updater_not_modified.py
"""
import os
import sys
import tempfile
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402

_PROD_DB = config.db_path
config.db_path = os.path.join(tempfile.mkdtemp(prefix="yourcast_not_modified_"), "t.db")
if os.path.abspath(config.db_path) == os.path.abspath(_PROD_DB):
    raise AssertionError("refusing to use production yourcast.db")

# podcastsUpdater imports the Telethon session; a test must not log in.
_telethon = types.ModuleType("agent.bot_telethon")
_telethon.thobot_session_handler = ""
sys.modules["agent.bot_telethon"] = _telethon

from db.connection import connect_sqlite  # noqa: E402
import app.jobs.podcastsUpdater as updater  # noqa: E402
from app.jobs import digest_outbox  # noqa: E402
from db import runtime_kv  # noqa: E402
from app.service.podcast.podcast import prepare_string_from_rss  # noqa: E402
from app.service.record.helpers import get_record_uniq_id  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402
from lib.tools.time_tools.general import format_rss_last_date  # noqa: E402

CHANNEL_ID = 7
PAYER_A, PAYER_B, FREE_C = 1001, 1002, 1003
EPISODES = {
    1: ("ep-1", "Mon, 28 Sep 2026 23:00:00 +0000", "Monday"),
    2: ("ep-2", "Tue, 29 Sep 2026 23:00:00 +0000", "Tuesday"),
}
FEED = {"version": 1, "requests": [], "build_date": None, "script": False}
SENT = []


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _feed_xml(version):
    items = "".join(
        "<item><title>%s</title><guid>%s</guid><pubDate>%s</pubDate>"
        "<enclosure url='http://127.0.0.1/%s.mp3' length='1000' type='audio/mpeg'/>"
        "</item>" % (EPISODES[i][2], EPISODES[i][0], EPISODES[i][1], EPISODES[i][0])
        for i in range(version, 0, -1))
    build = ("<lastBuildDate>%s</lastBuildDate>" % FEED["build_date"]
             if FEED["build_date"] else "")
    # feeds.acast.com puts an XHTML <script> before <channel>
    script = ("<script xmlns='http://www.w3.org/1999/xhtml'>var x = 1;</script>"
              if FEED["script"] else "")
    return ("<?xml version='1.0'?><rss version='2.0'>%s<channel><title>News</title>"
            "<link>http://127.0.0.1/</link>%s%s</channel></rss>" % (script, build, items)).encode()


class _Feed(BaseHTTPRequestHandler):
    def do_GET(self):
        etag = '"v%d"' % FEED["version"]
        conditional = self.headers.get("If-None-Match")
        if conditional == etag:
            FEED["requests"].append("304")
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        FEED["requests"].append("200 conditional" if conditional else "200 full")
        body = _feed_xml(FEED["version"])
        self.send_response(200)
        self.send_header("ETag", etag)
        self.send_header("Content-Type", "application/rss+xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def _pgd(number):
    guid, date, title = EPISODES[number]
    return get_record_uniq_id(guid, prepare_string_from_rss(date), title)


def _setup(feed_url):
    conn = connect_sqlite(config.db_path)
    try:
        # Rows are reset, tables kept: SQLighter adds http_etag once per process.
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY,
                telegramId INTEGER UNIQUE, lang TEXT, deleted_at TEXT, bitrate INTEGER);
            CREATE TABLE IF NOT EXISTS tariffs (id INTEGER PRIMARY KEY, level INTEGER,
                price INTEGER, notify_count INTEGER, compression INTEGER);
            CREATE TABLE IF NOT EXISTS user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER,
                tariff_id INTEGER, balance INTEGER, notify_count INTEGER, time_left INTEGER);
            CREATE TABLE IF NOT EXISTS user_channel_cs (id INTEGER PRIMARY KEY,
                user_telegram_id INTEGER, channel_id INTEGER, last_guid TEXT,
                last_date TEXT, notify INTEGER);
            CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, itunes_id INTEGER,
                name TEXT, rss_link TEXT, last_guid TEXT, last_date TEXT);
            DELETE FROM users;
            DELETE FROM tariffs;
            DELETE FROM user_tariff_cs;
            DELETE FROM user_channel_cs;
            DELETE FROM channels;
            INSERT INTO tariffs VALUES (3, 3, 500, -1, NULL);
        """)
        first_date = format_rss_last_date(EPISODES[1][1])
        conn.execute(
            "INSERT INTO channels (id, itunes_id, name, rss_link, last_guid, last_date) "
            "VALUES (?, NULL, 'News', ?, ?, ?)",
            (CHANNEL_ID, feed_url, _pgd(1), first_date))
        for uid, telegram_id, time_left in (
                (1, PAYER_A, 500), (2, PAYER_B, 500), (3, FREE_C, 0)):
            conn.execute(
                "INSERT INTO users (id, telegramId, lang) VALUES (?, ?, 'en')",
                (uid, telegram_id))
            conn.execute(
                "INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, "
                "time_left) VALUES (?, 3, 30000, -1, ?)", (uid, time_left))
            conn.execute(
                "INSERT INTO user_channel_cs (user_telegram_id, channel_id, last_guid, "
                "last_date, notify) VALUES (?, ?, ?, ?, 1)",
                (telegram_id, CHANNEL_ID, _pgd(1), first_date))
        conn.commit()
    finally:
        conn.close()


def _cursor(telegram_id):
    db = SQLighter(config.db_path)
    try:
        return db.connection.execute(
            "SELECT last_guid FROM user_channel_cs WHERE user_telegram_id = ?",
            (telegram_id,)).fetchone()[0]
    finally:
        db.close()


def _circle():
    db = SQLighter(config.db_path)
    try:
        channel = db.get_channel(CHANNEL_ID)
        paid = db.get_uccs_by_channel(
            CHANNEL_ID, have_subscription=True, notifications_enabled=True)
        free = db.get_uccs_by_channel(
            CHANNEL_ID, have_subscription=False, notifications_enabled=True)
    finally:
        db.close()
    return _run(lambda: updater.send_new_records_by_channel(
        channel, paid, nosubs_connections=free, tg_channel_connections=None))


def _manual_refresh(telegram_id):
    db = SQLighter(config.db_path)
    try:
        channel = db.get_channel(CHANNEL_ID)
        mine = [c for c in db.get_uccs_by_channel(CHANNEL_ID)
                if c['user_telegram_id'] == telegram_id]
    finally:
        db.close()
    return _run(lambda: updater.send_new_records_by_channel(
        channel, mine, manual=True))


def _run(call):
    SENT.clear()
    FEED["requests"].clear()
    call()
    return list(SENT), list(FEED["requests"])


def main():
    server = HTTPServer(("127.0.0.1", 0), _Feed)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    feed_url = "http://127.0.0.1:%d/feed.xml" % server.server_port
    updater.outbox.enqueue = lambda job, **_kwargs: SENT.append((
        job['func_params']['podcastInfo']['title'],
        sorted(job['func_params']['chat_ids'])))
    try:
        FEED["version"] = 1
        _setup(feed_url)
        sent, requests = _circle()
        _assert_eq(requests, ["200 full"], "first circle has no ETag yet")
        _assert_eq(sent, [], "everyone already has Monday")

        # Everyone current: the 304 is trusted, no full download.
        sent, requests = _circle()
        _assert_eq(requests, ["304"], "current payers: one conditional GET")
        _assert_eq(sent, [], "nothing to send")

        # Tuesday is out; A taps refresh before the circle.
        FEED["version"] = 2
        sent, requests = _manual_refresh(PAYER_A)
        _assert_eq(sent, [("Tuesday", [PAYER_A])], "refresh sends Tuesday to A")
        _assert_eq(_cursor(PAYER_B), _pgd(1), "B has not got Tuesday yet")

        sent, requests = _circle()
        _assert_eq(requests, ["304", "200 full"], "304 with B behind refetches in full")
        _assert_eq(sent, [("Tuesday", [PAYER_B])], "B gets Tuesday in this circle")
        _assert_eq(_cursor(PAYER_B), _pgd(2), "B's cursor at Tuesday")

        sent, requests = _circle()
        _assert_eq(requests, ["304"], "all current again: no second full download")
        _assert_eq(sent, [], "nothing sent twice")

        # A free listener behind does not force a full download; the 304
        # branch still reminds them.
        FEED["version"] = 1
        _setup(feed_url)
        _circle()
        conn = connect_sqlite(config.db_path)
        conn.execute("UPDATE user_channel_cs SET last_guid = 'older', last_date = 'older' "
                     "WHERE user_telegram_id = ?", (FREE_C,))
        conn.commit()
        conn.close()
        sent, requests = _circle()
        _assert_eq(requests, ["304"], "free listener behind: no refetch")
        _assert_eq(
            digest_outbox.get_row(FREE_C, database=config.db_path) is not None,
            True, "free listener behind is still flagged for the digest")

        # Loop guard. The episode list rewrote channels.last_* in its own
        # format; a full parse of the same version finds every payer current
        # (lastBuildDate) and returns early, so they stay "behind". One full
        # refetch per feed version, then the 304 is trusted.
        FEED["version"] = 1
        FEED["build_date"] = EPISODES[1][1]
        _setup(feed_url)
        runtime_kv.delete_kv("feed_refetch_%s" % CHANNEL_ID, database=config.db_path)
        _circle()
        conn = connect_sqlite(config.db_path)
        conn.execute("UPDATE channels SET last_guid = 'list-view-format', "
                     "last_date = 'list-view-date' WHERE id = ?", (CHANNEL_ID,))
        conn.commit()
        conn.close()
        sent, requests = _circle()
        _assert_eq(requests, ["304", "200 full"], "drifted channel: one full refetch")
        _assert_eq(sent, [], "the parse finds everyone current")
        sent, requests = _circle()
        _assert_eq(requests, ["304"], "same version again: no second download")
        _assert_eq(sent, [], "still nothing to send")

        # Acast: a <script> before <channel> used to parse to no items at all.
        FEED["version"] = 2
        FEED["build_date"] = None
        FEED["script"] = True
        _setup(feed_url)
        runtime_kv.delete_kv("feed_refetch_%s" % CHANNEL_ID, database=config.db_path)
        sent, requests = _circle()
        _assert_eq(sent, [("Tuesday", [PAYER_A, PAYER_B])],
                   "script before <channel>: the episode is parsed and sent")
        _assert_eq(_cursor(PAYER_B), _pgd(2), "cursor at the real episode, not '__'")
        FEED["script"] = False
    finally:
        server.shutdown()
    print("all updater 304 checks passed")


if __name__ == "__main__":
    main()
