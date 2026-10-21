"""Usage ledger: one row per delivered chat, a download shared, counts per episode, old rows go."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import usage


class UsageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'test.sqlite')

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_download_is_shared_by_the_chats_that_got_it(self):
        usage.record_deliveries([101, 102, 102], 'circle', 'https://cdn.example/ep1.mp3',
                                downloaded_mb=30, database=self.db)
        rows = usage.per_user(0, database=self.db)
        self.assertEqual(set(rows), {101, 102})
        self.assertAlmostEqual(rows[101]['mb'], 15)
        self.assertEqual(rows[101]['circle'], 1)
        self.assertEqual(rows[101]['rec'], 0)

    def test_episodes_are_counted_once_per_window(self):
        now = time.time()
        for link in ('https://a/1.mp3', 'https://a/2.mp3', 'https://a/1.mp3'):
            usage.record_deliveries([101], 'rec', link, database=self.db, at=now)
        usage.record_deliveries([101], 'rec', 'https://a/old.mp3', database=self.db,
                                at=now - usage.WEEK_SECONDS - 60)
        usage.record_deliveries([101], 'circle', 'https://a/3.mp3', database=self.db, at=now)
        week = usage.episodes_since(101, 'rec', now - usage.WEEK_SECONDS, database=self.db)
        self.assertEqual(week, {usage.episode_ref('https://a/1.mp3'), usage.episode_ref('https://a/2.mp3')})
        self.assertEqual(usage.oldest_since(101, 'rec', now - usage.WEEK_SECONDS, database=self.db), now)
        self.assertIsNone(usage.oldest_since(102, 'rec', 0, database=self.db))

    def test_ai_cost_and_prune(self):
        now = time.time()
        usage.record_ai(101, 'ep', 0.031, database=self.db, at=now)
        usage.record_ai(101, 'ep', 0.5, database=self.db, at=now - (usage.KEEP_DAYS + 1) * 86400)
        usage.prune(self.db, now=now)
        rows = usage.per_user(0, database=self.db)
        self.assertEqual(rows[101]['ai'], 1)
        self.assertAlmostEqual(rows[101]['ai_usd'], 0.031)

    def test_no_chats_writes_nothing(self):
        usage.record_deliveries([], 'rec', 'https://a/1.mp3', downloaded_mb=10, database=self.db)
        self.assertEqual(usage.per_user(0, database=self.db), {})


if __name__ == '__main__':
    unittest.main()
