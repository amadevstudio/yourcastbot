# -*- coding: utf-8 -*-
"""Free weekly episodes: the 11th click is refused, the same episode is not,
waiting clicks count, a paid plan has no limit; a plan nobody paid for (the
trial) gets trial_rec_per_day a day; the limit message lists every plan with
its Stars price and keeps the page of plans, the trial's has Relay's invoice.

Run from the repo root: python app/service/record/test_free_limit.py
(the message part runs where the bot's requirements are installed).
"""
import os
import sqlite3
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.record import free_limit  # noqa: E402
from db import usage  # noqa: E402

FREE, PAID, EXPIRED, TRIAL, PAYER = 2001, 2002, 2003, 2004, 2005


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _deliver(db, chat, n, at, prefix='ep'):
    for i in range(n):
        usage.record_deliveries([chat], 'rec', 'https://cdn/%s%d.mp3' % (prefix, i), database=db, at=at)


def _check_counting(db):
    now = time.time()
    _deliver(db, FREE, 10, now - 3 * 86400)
    ok, wait = free_limit.check(FREE, 'https://cdn/new.mp3', plan=False, now=now, database=db, limit=10)
    _assert(not ok, "the 11th episode in 7 days is refused")
    _assert(abs(wait - 4 * 86400) < 5, "the next free one comes when the oldest leaves the window")
    ok, _ = free_limit.check(FREE, 'https://cdn/ep3.mp3', plan=False, now=now, database=db, limit=10)
    _assert(ok, "the same episode again is free")
    ok, _ = free_limit.check(FREE, 'https://cdn/new.mp3', plan=True, now=now, database=db, limit=10)
    _assert(ok, "a running plan has no limit")
    ok, _ = free_limit.check(FREE, 'https://cdn/new.mp3', plan=False, now=now + 5 * 86400,
                             database=db, limit=10)
    _assert(ok, "a week later the episodes are free again")

    _deliver(db, EXPIRED, 9, now - 3600, prefix='x')
    ok, _ = free_limit.check(EXPIRED, 'https://cdn/a.mp3', plan=False, now=now, database=db, limit=10)
    _assert(ok, "9 delivered: the 10th is free")
    ok, _ = free_limit.check(EXPIRED, 'https://cdn/b.mp3', open_links={'https://cdn/a.mp3'},
                             plan=False, now=now, database=db, limit=10)
    _assert(not ok, "a click still waiting in the outbox counts: fast taps do not slip past")
    ok, _ = free_limit.check(EXPIRED, 'https://cdn/a.mp3', open_links={'https://cdn/a.mp3'},
                             plan=False, now=now, database=db, limit=10)
    _assert(ok, "tapping the waiting episode again is not a new one")
    usage.record_deliveries([EXPIRED], 'circle', 'https://cdn/auto.mp3', database=db, at=now)
    ok, _ = free_limit.check(EXPIRED, 'https://cdn/a.mp3', plan=False, now=now, database=db, limit=10)
    _assert(ok, "automatic deliveries do not count")


def _check_plan(db):
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
                                     balance INTEGER, notify_count INTEGER, time_left INTEGER);
        INSERT INTO tariffs VALUES (1, 1), (3, 3);
    """)
    c.executemany("INSERT INTO users VALUES (?, ?)", [(1, FREE), (2, PAID), (3, EXPIRED)])
    c.executemany("INSERT INTO user_tariff_cs VALUES (?, ?, ?, 0, ?, ?)",
                  [(1, 1, 0, 0, 0), (2, 2, 1, 0, 200), (3, 3, 3, -1, 0)])
    c.commit()
    c.close()
    _assert(not free_limit.has_running_plan(FREE, db), "no plan: limited")
    _assert(free_limit.has_running_plan(PAID, db), "Bronze with its notifies spent still has a plan")
    _assert(not free_limit.has_running_plan(EXPIRED, db), "a plan with no time left is no plan")


def _check_trial(db):
    """A plan nobody paid for: trial_rec_per_day by click a day; a payer: no limit."""
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE payment_history (id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT, amount INTEGER);
        INSERT INTO users VALUES (4, %d), (5, %d);
        INSERT INTO user_tariff_cs VALUES (4, 4, 3, 0, -1, 300), (5, 5, 3, 0, -1, 300);
        INSERT INTO payment_history (user_id, status, amount) VALUES (5, 'paid', 500);
    """ % (TRIAL, PAYER))
    c.commit()
    c.close()
    now = time.time()
    _deliver(db, TRIAL, 3, now - 20 * 3600, prefix='t')
    ok, wait = free_limit.trial_check(TRIAL, 'https://cdn/t9.mp3', now=now, database=db, limit=3)
    _assert(not ok and abs(wait - 4 * 3600) < 5, "the trial's 4th episode in a day waits for the oldest to leave")
    ok, _ = free_limit.trial_check(TRIAL, 'https://cdn/t1.mp3', now=now, database=db, limit=3)
    _assert(ok, "the same episode again is not a new one")
    ok, _ = free_limit.trial_check(TRIAL, 'https://cdn/t9.mp3', now=now + 5 * 3600, database=db, limit=3)
    _assert(ok, "a day later the trial's episodes are there again")
    ok, _ = free_limit.trial_check(TRIAL, 'https://cdn/t8.mp3', open_links={'https://cdn/t7.mp3'},
                                   now=now, database=db, limit=4)
    _assert(not ok, "a trial's click still waiting counts")

    from config import trial_rec_per_day
    _deliver(db, TRIAL, trial_rec_per_day, now - 3600, prefix='many')
    _deliver(db, PAYER, trial_rec_per_day, now - 3600, prefix='many')
    _deliver(db, PAID, trial_rec_per_day, now - 3600, prefix='many')
    message = free_limit.click_limit(TRIAL, 'https://cdn/next.mp3', (), 'en', now=now, database=db)
    _assert(message is not None and ('up to %d episodes a day' % trial_rec_per_day) in message['text'],
            "a trial past its day gets the trial's message")
    rows = [row[0]['callback_data'] for row in message['reply_markup']]
    _assert(rows[0]['tp'] == 'bs_stars_pay' and rows[1]['tp'] == 'bs_trfs',
            "Relay's invoice (paying lifts the limit at once), change-plan next to it")
    _assert(free_limit.click_limit(PAYER, 'https://cdn/next.mp3', (), 'en', now=now, database=db) is None,
            "a plan someone paid for has no limit")
    _assert(free_limit.click_limit(PAID, 'https://cdn/next.mp3', (), 'en', now=now, database=db) is not None,
            "nor does a running Bronze nobody paid for escape it")
    _assert(free_limit.click_limit(TRIAL, 'https://cdn/many1.mp3', (), 'en', now=now, database=db) is None,
            "an episode the trial already had today goes again")
    bronze = free_limit.trial_limit_message('en', 3600, 1)
    _assert(bronze['reply_markup'][0][0]['callback_data'] == {'tp': 'bs_stars'},
            "a Bronze trial gets the Stars page, not an invoice that would only top Bronze up")


def _check_message():
    try:
        from app.service.payment import starsPaymentModule
        from db import sqliteAdapter
    except Exception as e:  # CI has no bot requirements
        print("skip limit message (%s)" % e.__class__.__name__)
        return
    tariffs = [{'id': 1, 'level': 1, 'price': 100, 'notify_count': 60, 'compression': 0, 'channel_control': 0},
               {'id': 2, 'level': 2, 'price': 200, 'notify_count': 400, 'compression': 1, 'channel_control': 0},
               {'id': 3, 'level': 3, 'price': 500, 'notify_count': -1, 'compression': 1, 'channel_control': 1}]

    class FakeDB:
        def __init__(self, *_):
            pass

        def getTariffs(self):
            return tariffs

        def close(self):
            pass

    saved = (sqliteAdapter.SQLighter, starsPaymentModule.get_stars_withdraw_rate_x1000)
    sqliteAdapter.SQLighter = FakeDB
    starsPaymentModule.get_stars_withdraw_rate_x1000 = lambda *a, **k: 1300
    try:
        message = free_limit.limit_message('en', 30 * 3600, limit=10)
    finally:
        sqliteAdapter.SQLighter, starsPaymentModule.get_stars_withdraw_rate_x1000 = saved
    buttons = [row[0]['callback_data'] for row in message['reply_markup']]
    _assert([b.get('v') for b in buttons[:3]] == [3, 1, 2], "every plan is offered, Relay first")
    _assert(all(b['tp'] == 'bs_stars_pay' for b in buttons[:3]), "each plan opens its Stars invoice")
    _assert(buttons[3] == {'tp': 'bs_trfs'}, "the page of plans (other ways to pay) stays")
    _assert('385 ⭐' in message['reply_markup'][0][0]['text'], "Relay shows its Stars price")
    _assert('10 of 10' in message['text'] and '30 h' in message['text'], "the limit and the wait are named")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'test.sqlite')
        _check_counting(db)
        _check_plan(db)
        _check_trial(db)
    _check_message()
    print("all free limit checks passed")


if __name__ == "__main__":
    main()
