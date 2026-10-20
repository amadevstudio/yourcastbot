"""Saved lists are personal and bounded; digest ACK cannot delete newer items."""
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

    def test_saved_idempotent_personal_and_survives_pruning(self):
        episode = self.episode()
        self.assertEqual(listening.add_saved(101, episode, self.db), 'savedLater')
        self.assertEqual(listening.add_saved(101, episode, self.db), 'savedLater')
        self.assertEqual(len(listening.saved(101, self.db)), 1)
        self.assertEqual(listening.saved(102, self.db), [])
        listening.remove_saved(102, episode, self.db)
        self.episode('bbb', 'newer')
        listening.prune(self.db, now=time.time() + 100 * 86400)
        self.assertEqual(listening.saved(101, self.db)[0]['id'], episode)
        listening.remove_saved(101, episode, self.db)
        self.assertEqual(listening.saved(101, self.db), [])
        self.assertEqual(listening.add_saved(101, 999, self.db), 'screenOutdated')

    def test_bounded_saved_list(self):
        for index in range(listening.MAX_SAVED):
            episode = self.episode(str(index))
            self.assertEqual(listening.add_saved(101, episode, self.db), 'savedLater')
        self.assertEqual(listening.add_saved(101, self.episode('extra'), self.db), 'savedLimit')

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
