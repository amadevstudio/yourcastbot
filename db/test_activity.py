"""When a chat last used the bot, and the weekly digest of a chat that has not in 90 days: once a year.

Temporary databases only, made-up ids. Run from the repo root: python db/test_activity.py
(the send part runs where the bot's requirements are installed).
"""
import datetime
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.jobs.nosub_digest import DORMANT_DAYS, is_dormant, should_send_nosub_digest  # noqa: E402
from db import activity, usage  # noqa: E402

DAY = 86400


def _stamp(seconds_ago, now):
    return datetime.datetime.utcfromtimestamp(now - seconds_ago).strftime("%Y-%m-%d %H:%M:%S")


class Activity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'test.sqlite')
        c = activity.connect(self.db)
        with c:
            c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, created_at TEXT)")
        c.close()
        activity._touched.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, telegram_id, created_at=None):
        c = activity.connect(self.db)
        with c:
            c.execute("INSERT INTO users (telegramId, created_at) VALUES (?, ?)", (telegram_id, created_at))
        c.close()

    def test_touch_is_written_once_an_hour(self):
        now = 1_800_000_000
        activity.touch(7001, now=now, database=self.db)
        activity.touch(7001, now=now + 60, database=self.db)  # within the hour: not written
        self.assertEqual(activity.last_used(7001, self.db), now)
        activity.touch(7001, now=now + activity.TOUCH_EVERY_SECONDS, database=self.db)
        self.assertEqual(activity.last_used(7001, self.db), now + activity.TOUCH_EVERY_SECONDS)

    def test_groups_channels_and_junk_are_not_chats(self):
        for chat in (-1001234567, 0, None, 'abc'):
            activity.touch(chat, database=self.db)
        c = activity.connect(self.db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM user_activity").fetchone()[0], 0)
        c.close()

    def test_a_failed_write_is_quiet_and_tried_again(self):
        activity.touch(7002, now=100, database=os.path.join(self.tmp.name, 'no', 'such', 'dir.sqlite'))
        self.assertNotIn((os.path.join(self.tmp.name, 'no', 'such', 'dir.sqlite'), 7002), activity._touched)

    def test_last_used_is_the_latest_of_what_the_chat_did(self):
        now = time.time()
        self.assertIsNone(activity.last_used(7003, self.db))  # nothing at all: not used
        self._user(7003)  # an account from before created_at was kept
        self.assertIsNone(activity.last_used(7003, self.db))
        usage.record_deliveries([7003], 'circle', 'https://a/1.mp3', database=self.db, at=now - DAY)
        self.assertIsNone(activity.last_used(7003, self.db), "automatic files are not use")
        usage.record_deliveries([7003], 'rec', 'https://a/2.mp3', database=self.db, at=now - 5 * DAY)
        self.assertEqual(activity.last_used(7003, self.db), now - 5 * DAY)
        usage.record_ask(7003, 'ref', 0.0, database=self.db, at=now - 2 * DAY)
        self.assertEqual(activity.last_used(7003, self.db), now - 2 * DAY)
        self._user(7004, _stamp(3 * DAY, now))
        self.assertAlmostEqual(activity.last_used(7004, self.db), now - 3 * DAY, delta=1)


class DormantDigest(unittest.TestCase):
    NOW = datetime.datetime(2026, 11, 22, 12, 0, 0)

    def _user(self, sent_days_ago):
        return {"telegramId": 7101, "deleted_at": None, "nosub_digest_enabled": 1,
                "nosub_digest_sent_at": (self.NOW - datetime.timedelta(days=sent_days_ago)).strftime(
                    "%Y-%m-%d %H:%M:%S")}

    def test_dormant_is_ninety_days_or_never(self):
        now = self.NOW.replace(tzinfo=datetime.timezone.utc).timestamp()
        self.assertTrue(is_dormant(None, now=self.NOW))
        self.assertTrue(is_dormant(now - DORMANT_DAYS * DAY, now=self.NOW))
        self.assertFalse(is_dormant(now - (DORMANT_DAYS - 1) * DAY, now=self.NOW))

    def test_a_dormant_chat_gets_one_digest_a_year(self):
        self.assertTrue(should_send_nosub_digest(self._user(8), now=self.NOW))
        self.assertFalse(should_send_nosub_digest(self._user(8), now=self.NOW, dormant=True))
        self.assertFalse(should_send_nosub_digest(self._user(364), now=self.NOW, dormant=True))
        self.assertTrue(should_send_nosub_digest(self._user(365), now=self.NOW, dormant=True))
        never = dict(self._user(0), nosub_digest_sent_at=None)
        self.assertTrue(should_send_nosub_digest(never, now=self.NOW, dormant=True))
        self.assertFalse(should_send_nosub_digest(dict(self._user(400), nosub_digest_enabled=0),
                                                  now=self.NOW, dormant=True), "muted stays muted")


class DigestSend(unittest.TestCase):
    """The watcher reads the chat's use when it sends."""

    @classmethod
    def setUpClass(cls):
        try:
            from app.jobs import digest_watcher
            from db.sqliteAdapter import SQLighter
        except ImportError:
            raise unittest.SkipTest('bot requirements are not installed')
        cls.watcher, cls.SQLighter = digest_watcher, SQLighter

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'test.sqlite')
        activity._touched.clear()
        import sqlite3
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE, lang TEXT, "
                  "ref_id INTEGER, bitrate INTEGER)")
        c.commit()
        c.close()
        db = self.SQLighter(self.db)  # adds the columns the bot expects on users
        try:
            db.connection.executescript("""
                CREATE TABLE IF NOT EXISTS user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER,
                    tariff_id INTEGER, balance INTEGER, notify_count INTEGER, time_left INTEGER);
                CREATE TABLE IF NOT EXISTS user_channel_cs (id INTEGER PRIMARY KEY,
                    user_telegram_id INTEGER, channel_id INTEGER, notify INTEGER);
                INSERT INTO users (telegramId, lang, created_at) VALUES (7201, 'en', '2025-01-01 00:00:00');
            """)
            db.connection.commit()
            db.mark_nosub_digest_sent(7201, when=datetime.datetime.utcnow() - datetime.timedelta(days=8))
        finally:
            db.close()
        self.sent = []
        real = self.watcher.outer_sender
        self.watcher.outer_sender = lambda chat_id, messages, **_: self.sent.append(chat_id) or True
        self.addCleanup(setattr, self.watcher, 'outer_sender', real)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_chat_that_used_the_bot_gets_it_weekly_one_that_did_not_does_not(self):
        self.assertFalse(self.watcher.send_digest_to_user(7201, database=self.db))
        self.assertEqual(self.sent, [])
        activity.touch(7201, database=self.db)
        self.assertTrue(self.watcher.send_digest_to_user(7201, database=self.db))
        self.assertEqual(self.sent, [7201])

    def test_a_failed_read_is_the_weekly_digest(self):
        real = activity.last_used
        activity.last_used = lambda *a, **k: 1 / 0
        try:
            self.assertTrue(self.watcher.send_digest_to_user(7201, database=self.db))
        finally:
            activity.last_used = real


if __name__ == '__main__':
    unittest.main(verbosity=2)
