# -*- coding: utf-8 -*-
"""Free weekly episodes: the 11th click is refused, the same episode is not,
waiting clicks count, a running plan has no limit; the limit message lists
every plan with its Stars price and keeps the page of plans.

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

FREE, PAID, EXPIRED = 2001, 2002, 2003


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
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
                                     balance INTEGER, notify_count INTEGER, time_left INTEGER);
    """)
    c.executemany("INSERT INTO users VALUES (?, ?)", [(1, FREE), (2, PAID), (3, EXPIRED)])
    c.executemany("INSERT INTO user_tariff_cs VALUES (?, ?, ?, 0, ?, ?)",
                  [(1, 1, 0, 0, 0), (2, 2, 1, 0, 200), (3, 3, 3, -1, 0)])
    c.commit()
    c.close()
    _assert(not free_limit.has_running_plan(FREE, db), "no plan: limited")
    _assert(free_limit.has_running_plan(PAID, db), "Bronze with its notifies spent still has a plan")
    _assert(not free_limit.has_running_plan(EXPIRED, db), "a plan with no time left is no plan")


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
    _check_message()
    print("all free limit checks passed")


if __name__ == "__main__":
    main()
