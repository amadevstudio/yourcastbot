"""Personal screens, safe feed text, and buttons that survive lost screen state."""
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from app.controller.builders.test_open_recs import import_builder
from app.i18n.listening import LANGUAGES, ROWS
from app.i18n.messages import get_message
from db import feed_recovery, listening


class ListeningScreens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if import_builder('listeningModule') is None:
            raise unittest.SkipTest('bot requirements are not installed')
        from app.controller.builders import listeningModule
        cls.ui = listeningModule

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'test.sqlite')
        for module in (listening, feed_recovery):
            p = patch.object(module, 'db_path', self.db)
            p.start()
            self.addCleanup(p.stop)
        c = feed_recovery.connect(self.db)
        with c:
            c.executescript('CREATE TABLE channels(id INTEGER PRIMARY KEY,name TEXT);'
                           'CREATE TABLE user_channel_cs(user_telegram_id INTEGER,channel_id INTEGER,notify INTEGER);'
                           "INSERT INTO channels VALUES(17,'Show &amp; &lt;b&gt;'),(18,'Other');"
                           'INSERT INTO user_channel_cs VALUES(101,17,1),(102,18,1);')
        c.close()

    def tearDown(self):
        self.tmp.cleanup()

    def data(self, callback):
        return {'chat_id':101, 'language_code':'en', 'callback':types.SimpleNamespace(data=json.dumps(callback)),
                'message':None, 'united_data':{}, 'is_command':False}

    def episode(self):
        return listening.remember('Episode <i>one</i> &amp; two', 'Show',
            {'tp':'rec','id':17,'dh_n':'abcdef_99'}, self.db)

    def test_status_and_check_are_personal_and_stateless(self):
        screen = self.ui.construct_feed_status(101, 'en', database=self.db)[0]
        self.assertIn('Show &amp; &lt;b&gt;', screen['text'])
        self.assertNotIn('Other', screen['text'])
        with patch.object(self.ui, 'notify'), patch.object(self.ui, 'notify_outdated_screen') as outdated:
            self.ui.check_feed(self.data({'id':18}))
            self.ui.check_feed(self.data({'id':[]}))
            self.assertEqual(outdated.call_count, 2)
            self.assertEqual(feed_recovery.statuses([18], self.db), {})
            self.ui.check_feed(self.data({'id':17}))
            self.assertEqual(feed_recovery.statuses([17], self.db)[17]['status'], 'pending')

    def test_saved_actions_cannot_play_or_remove_another_users_item(self):
        episode = self.episode()
        listening.add_saved(102, episode, self.db)
        with patch.object(self.ui, 'notify_outdated_screen') as outdated:
            self.ui.play_later(self.data({'e':episode}))
            outdated.assert_called_once()
        with patch.object(self.ui, 'render_messages'), patch.object(self.ui, 'notify'):
            self.ui.remove_later(self.data({'e':episode}))
            self.ui.save_later(self.data({'e':episode}))
        self.assertEqual(len(listening.saved(102, self.db)), 1)
        from app.controller.builders import recsModule
        with patch.object(self.ui, 'notify'), patch.object(recsModule, 'send_record_direct') as send, \
                patch.object(feed_recovery, 'channel', return_value={'id':17}):
            self.ui.play_later(self.data({'e':episode}))
            self.assertEqual(send.call_args.args, ({'id':17},101,'en','abcdef',0))
        screen = self.ui.construct_saved(101, 'en', database=self.db)[0]
        self.assertIn('Episode one &amp; two', screen['text'])
        self.assertNotIn('<i>', screen['text'])

    def test_digest_content_and_existing_payment_and_mute_controls(self):
        from app.jobs.digest_watcher import digest_message
        episode = self.episode()
        listening.add_saved(101, episode, self.db)
        entry = listening.saved(101, self.db)[0]
        for lang in LANGUAGES:
            screen = digest_message([entry], lang)
            buttons = [b for row in screen['reply_markup'] for b in row]
            tps = [b['callback_data']['tp'] for b in buttons]
            self.assertEqual(tps, ['rec','saveLater','bs_stars','bs_trfs','digestMute'])
            self.assertEqual(buttons[0]['callback_data']['dh_n'], 'abcdef_1')
            self.assertIn('Episode one &amp; two', screen['text'])
            self.assertLess(len(screen['text']), 4096)


class Translations(unittest.TestCase):
    def test_all_copy_has_each_language(self):
        for key, row in ROWS.items():
            self.assertEqual(len(row), len(LANGUAGES), key)
            for lang, text in zip(LANGUAGES, row):
                self.assertEqual(get_message(key, lang), text, (key,lang))


if __name__ == '__main__':
    unittest.main()
