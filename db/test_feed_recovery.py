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
                CREATE TABLE users(id INTEGER,telegramId INTEGER,lang TEXT,deleted_at TEXT);
                CREATE TABLE user_tariff_cs(uid INTEGER,tariff_id INTEGER,notify_count INTEGER,
                    time_left INTEGER);
                CREATE TABLE bot_runtime_kv(key TEXT PRIMARY KEY,value TEXT);
                INSERT INTO channels VALUES(17,'123456','https://old.example/feed','etag','date',
                    'channel-cursor','channel-date','Test show');
                INSERT INTO user_channel_cs VALUES(1,101,17,1,'paid-cursor','paid-date');
                INSERT INTO user_channel_cs VALUES(2,102,17,0,'muted-cursor','muted-date');
                INSERT INTO users VALUES(1,101,'ru',NULL),(2,102,'en',NULL);
                INSERT INTO user_tariff_cs VALUES(1,3,-1,100),(2,3,-1,100);
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
            lookup=lambda _: 'https://new.example/https%3A%2F%2Ffeed',
            validate=lambda url: 'new.example' in url))
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

    def test_working_stored_url_is_kept_whatever_the_catalog_says(self):
        # A tap on "Check feed" for a healthy show must not move it to the
        # catalog's URL: other guids/dates there would break every cursor.
        self.enqueue(now=100, paused=True)
        def no_catalog(_):
            self.fail('a working stored URL needs no catalog lookup')
        self.assertTrue(process_one(database=self.db, now=101,
            lookup=no_catalog, validate=lambda url: True))
        with jobs.connect(self.db) as c:
            row = c.execute('SELECT * FROM channels').fetchone()
            self.assertEqual((row['rss_link'], row['http_etag'], row['http_last_modified']),
                             ('https://old.example/feed', 'etag', 'date'))
            self.assertEqual([r[0] for r in c.execute('SELECT key FROM bot_runtime_kv')],
                             ['feed_refetch_17'])
        state = jobs.statuses([17], self.db)[17]
        self.assertEqual((state['status'], state['paused']), ('healthy', 0))

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
                INSERT INTO users VALUES(3,-100,'en',NULL),(4,104,'en','deleted'),
                    (5,105,'en',NULL),(6,106,'en',NULL);
                INSERT INTO user_tariff_cs VALUES(3,3,-1,100),(4,3,-1,100),(5,0,0,0),(6,3,-1,0);
                INSERT INTO user_channel_cs VALUES(3,-100,17,1,'x','x'),(4,104,17,1,'x','x'),
                    (5,105,17,1,'x','x'),(6,106,17,1,'x','x');
            ''')
        self.enqueue(now=100, paused=True)
        notice = jobs.next_notice(self.db, now=101)
        # 105 is free and 106's plan has run out: the digest is theirs, not a notice
        self.assertEqual(notice['user_telegram_id'], 101)
        self.assertIsNone(jobs.next_notice(self.db, now=102))
        jobs.finish_notice(notice, database=self.db, now=103)
        self.assertIsNone(jobs.next_notice(self.db, now=104))

    def test_flapping_feed_does_not_notify_again_within_a_week(self):
        self.enqueue(now=100, paused=True)
        notice = jobs.next_notice(self.db, now=101)
        jobs.finish_notice(notice, database=self.db, now=102)
        self.assertIsNone(jobs.next_notice(self.db, now=103))
        jobs.note_ok(17, self.db, now=200)
        self.enqueue(now=300, paused=True)
        self.assertIsNone(jobs.next_notice(self.db, now=301))
        jobs.note_ok(17, self.db, now=400)
        later = 102 + jobs.NOTICE_REPEAT_SECONDS
        self.enqueue(now=later, paused=True)
        self.assertEqual(jobs.next_notice(self.db, now=later + 1)['user_telegram_id'], 101)

    def test_old_notice_ack_cannot_consume_a_new_pause(self):
        self.enqueue(now=100, paused=True)
        old = jobs.next_notice(self.db, now=101)
        jobs.note_ok(17, self.db, now=102)
        # the old send never acknowledged; a pause a week on starts afresh
        later = 161 + jobs.NOTICE_REPEAT_SECONDS
        self.enqueue(now=later, paused=True)
        jobs.finish_notice(old, database=self.db, now=later + 1)
        new = jobs.next_notice(self.db, now=later + 2)
        self.assertEqual(new['sub_id'], old['sub_id'])
        self.assertNotEqual(new['token'], old['token'])


if __name__ == '__main__':
    unittest.main()
