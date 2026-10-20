"""Digest episodes follow notify, expire when nothing refers to them; ACK cannot delete newer items."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import listening


class ListeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'test.sqlite')
        c = listening.connect(self.db)
        with c:
            c.executescript('CREATE TABLE user_channel_cs(user_telegram_id INTEGER,'
                           'channel_id INTEGER,notify INTEGER);'
                           'INSERT INTO user_channel_cs VALUES(101,17,1),(102,17,0);')
        c.close()

    def tearDown(self):
        self.tmp.cleanup()

    def episode(self, key='aaa', cursor='cursor'):
        return listening.remember('A &amp; B <b>episode</b>', 'Test show',
            {'tp':'rec','id':17,'dh_n':key + '_12'}, self.db, channel_id=17, cursor=cursor)

    def test_prune_keeps_what_a_channel_or_digest_still_refers_to(self):
        old = self.episode()
        listening.flag_digest([101], 17, 'cursor', self.db)
        latest = self.episode('bbb', 'newer')
        later = time.time() + 100 * 86400
        listening.prune(self.db, now=later)
        # the digest row itself is older than 90 days: gone, and its episode with it
        self.assertFalse(listening.has_digest(101, self.db))
        c = listening.connect(self.db)
        ids = [r[0] for r in c.execute('SELECT id FROM listening_episodes')]
        c.close()
        self.assertEqual(ids, [latest])
        self.assertNotIn(old, ids)

    def test_digest_rechecks_notify_and_subscription(self):
        self.episode()
        listening.flag_digest([101,102], 17, 'cursor', self.db)
        self.assertEqual(len(listening.digest(101, self.db)), 1)
        self.assertEqual(listening.digest(102, self.db), [])
        c = listening.connect(self.db)
        with c:
            c.execute('DELETE FROM user_channel_cs WHERE user_telegram_id=101')
        c.close()
        self.assertEqual(listening.digest(101, self.db), [])

    def test_hard_delete_takes_the_queued_digest(self):
        try:
            from db.sqliteAdapter import SQLighter
        except ImportError:
            self.skipTest('bot requirements are not installed')
        c = listening.connect(self.db)
        with c:
            c.executescript('CREATE TABLE users(id INTEGER PRIMARY KEY,telegramId INTEGER,'
                            "lang TEXT,deleted_at TEXT);INSERT INTO users VALUES(1,101,'en',NULL);")
        c.close()
        self.episode()
        listening.flag_digest([101], 17, 'cursor', self.db)
        db = SQLighter(self.db)
        try:
            db.delete_user_tg(101, hard=True)
        finally:
            db.close()
        self.assertFalse(listening.has_digest(101, self.db))

    def test_cursor_match_and_concurrent_ack(self):
        self.episode()
        listening.flag_digest([101], 17, 'wrong-cursor', self.db)
        self.assertEqual(listening.digest(101, self.db), [])
        listening.flag_digest([101], 17, 'cursor', self.db)
        before = listening.digest(101, self.db)
        new_id = self.episode('bbb', 'newer')
        listening.flag_digest([101], 17, 'newer', self.db)
        listening.ack_digest(101, before, self.db)
        current = listening.digest(101, self.db)
        self.assertEqual(current[0]['id'], new_id)
        listening.ack_digest(101, current, self.db)
        self.assertEqual(listening.digest(101, self.db), [])


if __name__ == '__main__':
    unittest.main()
