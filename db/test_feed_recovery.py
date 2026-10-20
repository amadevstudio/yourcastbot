"""Repair jobs preserve listening preferences/cursors and fence obsolete workers."""
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import feed_recovery as jobs
from app.jobs.feed_recovery import process_one, lookup_url


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, 'test.sqlite')
        with jobs.connect(self.db) as c:
            c.executescript('''
                CREATE TABLE channels(id INTEGER PRIMARY KEY,itunes_id TEXT,rss_link TEXT,
                    http_etag TEXT,http_last_modified TEXT,last_guid TEXT,last_date TEXT,name TEXT);
                CREATE TABLE user_channel_cs(id INTEGER PRIMARY KEY,user_telegram_id INTEGER,
                    channel_id INTEGER,notify INTEGER,last_guid TEXT,last_date TEXT);
                CREATE TABLE users(telegramId INTEGER,lang TEXT,deleted_at TEXT);
                CREATE TABLE bot_runtime_kv(key TEXT PRIMARY KEY,value TEXT);
                INSERT INTO channels VALUES(17,'123456','https://old.example/feed','etag','date',
                    'channel-cursor','channel-date','Test show');
                INSERT INTO user_channel_cs VALUES(1,101,17,1,'paid-cursor','paid-date');
                INSERT INTO user_channel_cs VALUES(2,102,17,0,'muted-cursor','muted-date');
                INSERT INTO users VALUES(101,'ru',NULL),(102,'en',NULL);
                INSERT INTO bot_runtime_kv VALUES('feed_refetch_17','old');
                INSERT INTO bot_runtime_kv VALUES('channel_feed_dead_until_17','9999');
            ''')

    def tearDown(self):
        self.tmp.cleanup()

    def enqueue(self, **kw):
        return jobs.enqueue(17, 'gone', database=self.db, **kw)

    def test_replace_only_url_and_validators(self):
        self.enqueue(now=100, paused=True)
        self.assertTrue(process_one(database=self.db, now=101,
            lookup=lambda _: 'https://new.example/https%3A%2F%2Ffeed', validate=lambda _: True))
        with jobs.connect(self.db) as c:
            row = c.execute('SELECT * FROM channels').fetchone()
            self.assertEqual(row['rss_link'], 'https://new.example/https%3A%2F%2Ffeed')
            self.assertIsNone(row['http_etag'])
            self.assertIsNone(row['http_last_modified'])
            self.assertEqual(row['last_guid'], 'channel-cursor')
            self.assertEqual([tuple(r) for r in c.execute(
                'SELECT notify,last_guid,last_date FROM user_channel_cs ORDER BY id')],
                [(1,'paid-cursor','paid-date'), (0,'muted-cursor','muted-date')])
            self.assertEqual(c.execute('SELECT count(*) FROM bot_runtime_kv').fetchone()[0], 0)
        self.assertEqual(jobs.statuses([17], self.db)[17]['paused'], 0)

    def test_duplicate_failure_does_not_extend_lease_or_create_jobs(self):
        self.enqueue(now=100)
        old = jobs.claim(self.db, now=100)
        self.enqueue(now=101, paused=True)
        self.assertIsNone(jobs.claim(self.db, now=102))
        new = jobs.claim(self.db, now=401)
        self.assertNotEqual(old['lease_token'], new['lease_token'])
        channel = jobs.channel(17, self.db)
        self.assertFalse(jobs.finish(old, channel, new_url='https://stale.example',
                                     database=self.db, now=402))
        self.assertTrue(jobs.finish(new, channel, new_url='https://good.example',
                                    database=self.db, now=403))

    def test_concurrent_claim_has_only_one_owner(self):
        self.enqueue(now=100)
        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda _: jobs.claim(self.db, now=101), range(8)))
        self.assertEqual(sum(c is not None for c in claims), 1)

    def test_catalog_matches_identity_and_keeps_encoded_tracker_url(self):
        response = Mock()
        response.json.return_value = {'results':[
            {'collectionId':999,'feedUrl':'https://wrong.example'},
            {'collectionId':123456,'feedUrl':'https://feed.example/https%3A%2F%2Fsource'},
        ]}
        with patch('app.jobs.feed_recovery.requester.get', return_value=response) as get:
            self.assertEqual(lookup_url('123456'), 'https://feed.example/https%3A%2F%2Fsource')
            self.assertTrue(get.call_args.kwargs['verify'])
            response.raise_for_status.assert_called_once()

    def test_retry_daily_and_manual_throttling(self):
        self.enqueue(now=100, paused=True)
        process_one(self.db, lookup=lambda _: None, validate=lambda _: False, now=101)
        self.enqueue(now=102)
        self.assertIsNone(jobs.claim(self.db, now=102))
        self.enqueue(now=103, manual=True)
        self.assertIsNone(jobs.claim(self.db, now=400))
        self.assertIsNotNone(jobs.claim(self.db, now=401))

    def test_catalog_failure_and_invalid_candidate_keep_stored_fallback(self):
        self.enqueue(now=100)
        def validate(url):
            if 'catalog' in url:
                raise ValueError('bad XML')
            return True
        process_one(self.db, lookup=lambda _: 'https://catalog.example', validate=validate, now=101)
        self.assertEqual(jobs.statuses([17], self.db)[17]['status'], 'healthy')

    def test_rss_only_rechecks_without_catalog_and_failed_repair_keeps_old_url(self):
        with jobs.connect(self.db) as c:
            c.execute('UPDATE channels SET itunes_id=NULL')
        self.enqueue(now=100, paused=True)
        def no_catalog(_):
            self.fail('RSS-only feed must not be looked up in iTunes')
        process_one(self.db, lookup=no_catalog, validate=lambda _: False, now=101)
        state = jobs.statuses([17], self.db)[17]
        self.assertEqual(state['available_at'], 101 + jobs.RECHECK_SECONDS)
        self.assertEqual(state['paused'], 1)
        self.assertEqual(jobs.channel(17, self.db)['rss_link'], 'https://old.example/feed')
        process_one(self.db, lookup=no_catalog, validate=lambda _: True, now=state['available_at'])
        self.assertEqual(jobs.statuses([17], self.db)[17]['status'], 'healthy')

    def test_catalog_exception_still_checks_stored_url(self):
        self.enqueue(now=100)
        def offline(_):
            raise TimeoutError()
        process_one(self.db, lookup=offline, validate=lambda _: True, now=101)
        self.assertEqual(jobs.statuses([17], self.db)[17]['status'], 'healthy')

    def test_concurrent_edit_and_successful_regular_fetch_cancel_old_work(self):
        self.enqueue(now=100)
        job = jobs.claim(self.db, now=101)
        channel = jobs.channel(17, self.db)
        with jobs.connect(self.db) as c:
            c.execute("UPDATE channels SET rss_link='https://edited.example'")
        self.assertFalse(jobs.finish(job, channel, new_url='https://other.example',
                                    database=self.db, now=102))
        jobs.note_ok(17, self.db, now=103)
        self.assertEqual(jobs.statuses([17], self.db)[17]['status'], 'healthy')
        self.assertIsNone(jobs.claim(self.db, now=100000))

    def test_legacy_does_not_unmute_or_send_old_notices(self):
        jobs.seed_legacy(self.db, now=100)
        jobs.seed_legacy(self.db, now=101)
        self.assertIsNone(jobs.next_notice(self.db, now=102))
        with jobs.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT notify FROM user_channel_cs WHERE id=2').fetchone()[0], 0)

    def test_notice_only_active_private_opted_in_listeners_and_once(self):
        with jobs.connect(self.db) as c:
            c.executescript('''
                INSERT INTO users VALUES(-100,'en',NULL),(104,'en','deleted');
                INSERT INTO user_channel_cs VALUES(3,-100,17,1,'x','x'),(4,104,17,1,'x','x');
            ''')
        self.enqueue(now=100, paused=True)
        notice = jobs.next_notice(self.db, now=101)
        self.assertEqual(notice['user_telegram_id'], 101)
        self.assertIsNone(jobs.next_notice(self.db, now=102))
        jobs.finish_notice(notice, database=self.db, now=103)
        self.assertIsNone(jobs.next_notice(self.db, now=104))

    def test_old_notice_ack_cannot_consume_a_new_pause(self):
        self.enqueue(now=100, paused=True)
        old = jobs.next_notice(self.db, now=101)
        jobs.note_ok(17, self.db, now=102)
        self.enqueue(now=103, paused=True)
        jobs.finish_notice(old, database=self.db, now=104)
        new = jobs.next_notice(self.db, now=105)
        self.assertEqual(new['sub_id'], old['sub_id'])
        self.assertNotEqual(new['token'], old['token'])


if __name__ == '__main__':
    unittest.main()
