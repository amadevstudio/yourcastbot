"""The digest names its episodes, keeps the payment and mute controls, and its copy exists in every language."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.i18n.listening import LANGUAGES, ROWS
from app.i18n.messages import get_message
from db import listening


class DigestMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from app.jobs.digest_watcher import digest_message
        except ImportError:
            raise unittest.SkipTest('bot requirements are not installed')
        cls.digest_message = staticmethod(digest_message)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'test.sqlite')
        p = patch.object(listening, 'db_path', self.db)
        p.start()
        self.addCleanup(p.stop)
        c = listening.connect(self.db)
        with c:
            c.executescript('CREATE TABLE user_channel_cs(user_telegram_id INTEGER,channel_id INTEGER,notify INTEGER);'
                            'INSERT INTO user_channel_cs VALUES(101,17,1);')
        c.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_digest_content_and_existing_payment_and_mute_controls(self):
        listening.remember('Episode <i>one</i> &amp; two', 'Show',
                           {'tp':'rec','id':17,'dh_n':'abcdef_99'}, self.db, channel_id=17, cursor='c')
        listening.flag_digest([101], 17, 'c', self.db)
        entry = listening.digest(101, self.db)[0]
        for lang in LANGUAGES:
            screen = self.digest_message([entry], lang)
            buttons = [b for row in screen['reply_markup'] for b in row]
            tps = [b['callback_data']['tp'] for b in buttons]
            self.assertEqual(tps, ['rec','bs_stars','bs_trfs','digestMute'])
            # positions move as the feed grows: "Listen" looks the hash up from the start
            self.assertEqual(buttons[0]['callback_data']['dh_n'], 'abcdef_1')
            self.assertIn('Episode one &amp; two', screen['text'])
            self.assertNotIn('<i>', screen['text'])
            self.assertLess(len(screen['text']), 4096)


class Translations(unittest.TestCase):
    def test_all_copy_has_each_language(self):
        for key, row in ROWS.items():
            self.assertEqual(len(row), len(LANGUAGES), key)
            for lang, text in zip(LANGUAGES, row):
                self.assertEqual(get_message(key, lang), text, (key,lang))


if __name__ == '__main__':
    unittest.main()
