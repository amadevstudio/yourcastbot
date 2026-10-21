# -*- coding: utf-8 -*-
"""Amplitude events that are not taps: tracked under users.id from any role,
never for a chat the bot does not know (no row created), never failing the
caller; a digest's Listen tap carries its source.

Run from the repo root: python app/service/test_analytics_events.py
"""
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service import analytics_events  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class FakeAnalytics:
    def __init__(self):
        self.queued, self.sent = [], []
        self.queue = self

    def put(self, item):
        self.queued.append(item[1])

    def event(self, args):
        self.sent.append(args)


def test_track(db):
    fake = FakeAnalytics()
    _assert(analytics_events.track(1001, 'digest_sent', {'episodes': 3}, db, analytics=fake), "tracked")
    event = fake.queued[0]
    _assert(event['user_id'] == 7 and event['command'] == 'digest_sent' and event['event_properties'] == {'episodes': 3}
            and event['user_properties'] == {'lang': 'ru', 'telegram_id': 1001},
            "under users.id, as taps are, with the user's language")
    _assert(not analytics_events.track(5555, 'digest_sent', None, db, analytics=fake), "an unknown chat is not tracked")
    count = sqlite3.connect(db).execute("SELECT count(*) FROM users").fetchone()[0]
    _assert(count == 1, "and no user row is created for it")
    analytics_events.track(1001, 'payment', {'method': 'cryptoBot'}, db, analytics=fake, sync=True)
    _assert(fake.sent and fake.sent[0]['command'] == 'payment', "sync: sent at once (a script exits next)")

    class Broken(FakeAnalytics):
        def put(self, item):
            raise RuntimeError('amplitude is down')
    _assert(analytics_events.track(1001, 'digest_sent', None, db, analytics=Broken()) is False,
            "a failing tracker never fails the caller")
    _assert(analytics_events.track(1001, 'x', None, os.path.join(os.path.dirname(db), 'missing', 'x.db'),
                                   analytics=fake) is False, "nor does a database error")


def test_plan_off(db):
    fake = FakeAnalytics()
    saved = analytics_events._analytics
    analytics_events._analytics = lambda: fake
    try:
        analytics_events.plan_off(1001, 3, db)
        _assert(fake.queued[-1]['event_properties'] == {'level': 3, 'paid_before': False},
                "a plan nobody paid for that ended: a trial that did not convert")
        sqlite3.connect(db).executescript(
            "INSERT INTO payment_history(user_id, status) VALUES (7, 'paid');")
        analytics_events.plan_off(1001, 3, db)
        _assert(fake.queued[-1]['event_properties']['paid_before'] is True, "a paid plan that ended")
    finally:
        analytics_events._analytics = saved


def test_tap_source():
    _assert(analytics_events.tap_properties({'tp': 'rec', 's': 'd'}) == {'source': 'digest'},
            "a digest's Listen tap carries its source")
    _assert(analytics_events.tap_properties({'tp': 'rec'}) == {} and analytics_events.tap_properties(None) == {},
            "other taps carry nothing new")


def test_tap_event():
    try:
        from lib.analytics.analytics import Analytics
    except Exception as e:  # CI has no bot requirements
        print("skip tap event (%s)" % e.__class__.__name__)
        return
    queued = []
    tracker = Analytics.__new__(Analytics)
    tracker.queue = type('Q', (), {'put': lambda self, item: queued.append(item[1])})()
    tracker.smart_event_telegram_processing({
        'tgData': {'callback': object(), 'route_name': 'recs', 'language_code': 'en', 'chat_id': 1001},
        'userSystemId': 7, 'actionName': 'recs', 'language_code': 'en', 'specialEventData': None,
        'eventProperties': {'source': 'digest'}})
    _assert(queued[0]['command'] == 'recs' and queued[0]['event_properties']['source'] == 'digest'
            and queued[0]['event_properties']['request_type'] == 'call', "the tap's Amplitude event has the source")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'test.sqlite')
        sqlite3.connect(db).executescript(
            "CREATE TABLE users(id INTEGER PRIMARY KEY, telegramId INTEGER, lang TEXT);"
            "INSERT INTO users VALUES (7, 1001, 'ru');"
            "CREATE TABLE payment_history(user_id INTEGER, status TEXT);")
        test_track(db)
        test_plan_off(db)
    test_tap_source()
    test_tap_event()
    print("all analytics event checks passed")


if __name__ == "__main__":
    main()
