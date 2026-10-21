"""The digest names its episodes, keeps the payment and mute controls, and its copy exists in every language."""
import json
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
        from db import ai
        p = patch.object(ai, 'db_path', self.db)
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
            tps = [_data(b)['tp'] for b in buttons]
            self.assertEqual(tps, ['rec','bs_stars','bs_trfs','digestMute'])
            # positions move as the feed grows: "Listen" looks the hash up from the start
            self.assertEqual(_data(buttons[0])['dh_n'], 'abcdef_1')
            # a tap from the digest is told apart in Amplitude, within Telegram's 64 bytes
            self.assertEqual(_data(buttons[0])['s'], 'd')
            self.assertLessEqual(len(buttons[0]['callback_data'].encode()), 64)
            self.assertIn('Episode one &amp; two', screen['text'])
            self.assertNotIn('<i>', screen['text'])
            self.assertLess(len(screen['text']), 4096)

    def test_a_made_summary_shows_its_gist(self):
        from db import ai
        listening.remember('Episode one', 'Show', {'tp': 'rec', 'id': 17, 'dh_n': 'abcdef_9'},
                           self.db, channel_id=17, cursor='c')
        listening.flag_digest([101], 17, 'c', self.db)
        entry = listening.digest(101, self.db)[0]
        self.assertNotIn('📝', self.digest_message([entry], 'en')['text'], "no summary made: nothing new")
        ai.remember_episode('ref1', 'https://cdn.example/1.mp3', 17, 'Episode one', 'Show', database=self.db)
        ai.save_summary('ref1', 'de', 'Auf Deutsch.\n• x', 0.0, database=self.db)
        ai.save_summary('ref1', 'original', 'They <explain> why ' + 'very ' * 60 + 'much.\n• point', 0.0,
                        database=self.db)
        text = self.digest_message([entry], 'en')['text']
        self.assertIn('📝 <i>They &lt;explain&gt; why very', text, "the gist, the episode's own language first")
        self.assertIn('…</i>', text, "cut at a word")
        self.assertNotIn('• point', text, "the first line only")
        with patch.object(ai, 'gist', side_effect=RuntimeError('locked')):
            self.assertNotIn('📝', self.digest_message([entry], 'en')['text'], "a failing lookup never fails the digest")

    def test_listen_buttons_share_rows(self):
        listening.remember('Episode', 'Show', {'tp': 'rec', 'id': 17, 'dh_n': 'abcdef_9'},
                           self.db, channel_id=17, cursor='c')
        listening.flag_digest([101], 17, 'c', self.db)
        entry = dict(listening.digest(101, self.db)[0])
        entries = [dict(entry, show_name='Show %d' % i) for i in range(5)]
        rows = self.digest_message(entries, 'en')['reply_markup']
        listen_rows = [row for row in rows if _data(row[0])['tp'] == 'rec']
        self.assertEqual([len(row) for row in listen_rows], [3, 2], "five episodes in two rows")
        self.assertEqual([b['text'][0] for row in listen_rows for b in row], list('12345'), "in order")


def _data(button):
    data = button['callback_data']
    return json.loads(data) if isinstance(data, str) else data


class Translations(unittest.TestCase):
    def test_all_copy_has_each_language(self):
        for key, row in ROWS.items():
            self.assertEqual(len(row), len(LANGUAGES), key)
            for lang, text in zip(LANGUAGES, row):
                self.assertEqual(get_message(key, lang), text, (key,lang))


if __name__ == '__main__':
    unittest.main()
