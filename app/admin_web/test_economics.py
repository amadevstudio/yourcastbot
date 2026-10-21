# -*- coding: utf-8 -*-
"""Admin economics: segments, revenue without the creator's tests, the server
bill spread by load, a channel's deliveries counted for its owner.

Temporary file DB only. Run from the repo root:
python app/admin_web/test_economics.py
"""
import datetime
import os
import sqlite3
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402
from app.admin_web import economics  # noqa: E402
from db import usage  # noqa: E402

PAYER, TRIAL, FREE, CHANNEL = 1001, 1002, 1003, -100500


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _assert_close(got, expected, label):
    if abs(got - expected) > 1e-3:  # the report rounds to 4 places
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, round(got, 6)))


def _setup(path, now):
    stamp = datetime.datetime.fromtimestamp(now - 86400).strftime('%Y-%m-%d %H:%M:%S.%f')
    old = datetime.datetime.fromtimestamp(now - 90 * 86400).strftime('%Y-%m-%d %H:%M:%S.%f')
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER NOT NULL UNIQUE);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
                                     balance INTEGER, notify_count INTEGER, time_left INTEGER);
        CREATE TABLE payment_history (user_id INTEGER, service_type TEXT, invoice_id TEXT,
                                      invoice_hash TEXT, status TEXT, amount INTEGER, datetime TEXT);
        CREATE TABLE tg_channels (id INTEGER PRIMARY KEY, user_id INTEGER, tg_id INTEGER, active INTEGER);
        INSERT INTO tariffs VALUES (1, 1, 50), (3, 3, 500);
    """)
    creator = int(config.creatorId)
    conn.executemany("INSERT INTO users VALUES (?, ?)",
                     [(1, PAYER), (2, TRIAL), (3, FREE), (4, creator)])
    conn.executemany("INSERT INTO user_tariff_cs VALUES (?, ?, ?, 0, -1, ?)",
                     [(1, 1, 3, 100), (2, 2, 3, 100), (3, 3, 0, 0), (4, 4, 3, 100)])
    conn.executemany("INSERT INTO payment_history VALUES (?, 'telegramStars', ?, '', ?, ?, ?)",
                     [(1, 'a', 'paid', 500, stamp),
                      (1, 'old', 'paid', 500, old),        # outside the period
                      (2, 'b', 'canceled', 500, stamp),    # not paid: still a trial
                      (4, 'c', 'paid', 500, stamp)])       # the creator's own test
    conn.execute("INSERT INTO tg_channels VALUES (1, ?, ?, 1)", (PAYER, CHANNEL))
    # a channel added by its link is kept by @name (10 of 47 on prod): int() of it broke the page
    conn.execute("INSERT INTO tg_channels VALUES (2, ?, '@named_show', 1)", (PAYER,))
    conn.commit()
    conn.close()
    at = now - 3600
    for i in range(6):
        usage.record_deliveries([FREE], 'rec', 'https://a/%d.mp3' % i, database=path, at=at)
    usage.record_deliveries([FREE], 'rec', 'https://a/big.mp3', downloaded_mb=100, database=path, at=at)
    usage.record_deliveries([CHANNEL], 'circle', 'https://a/c.mp3', database=path, at=at)
    usage.record_ai(TRIAL, 'ep', 0.25, database=path, at=at)


def main():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'test.sqlite')
        _setup(path, now)
        report = economics.economics(days=30, database=path, now=now, server_usd_month=10)

        users = {row['tg']: row for row in report['users']}
        _assert_eq(users[PAYER]['segment'], 'paid', 'a running plan someone paid for')
        _assert_eq(users[TRIAL]['segment'], 'trial', 'a running plan nobody paid for')
        _assert_eq(users[FREE]['segment'], 'free', 'no running plan')
        _assert_eq(CHANNEL in users, False, 'a channel is not its own row')
        _assert_eq(users[PAYER]['circle'], 1, "the channel's delivery counts for its owner")
        _assert_close(users[PAYER]['revenue_usd'], 5.0, 'revenue: paid, in the period')
        _assert_eq(int(config.creatorId) in users, False, "the creator's test payment is not revenue")

        # load: FREE 7 deliveries + 100/50 MB = 9, PAYER 1, TRIAL 0 (AI only)
        _assert_close(users[FREE]['fixed_usd'], 10 * 9 / 10, 'the server bill follows the load')
        _assert_close(users[FREE]['margin_usd'], -9.0, 'a heavy free user is in the minus')
        _assert_close(users[PAYER]['margin_usd'], 5.0 - 1.0, 'a payer pays for their share')
        _assert_close(users[TRIAL]['margin_usd'], -0.25, 'AI spend is a direct cost')
        _assert_eq(report['users'][0]['tg'], FREE, 'the worst margin comes first')

        totals = report['totals']
        _assert_close(totals['fixed_usd'], 10.0, 'the whole month of server')
        _assert_close(totals['margin_usd'], 5.0 - 0.25 - 10.0, 'total: revenue - AI - server')
        segments = {row['segment']: row for row in report['segments']}
        _assert_eq(segments['free']['users'], 1, 'segment counts')
        _assert_close(segments['paid']['revenue_usd'], 5.0, 'segment revenue')

        usage.record_deliveries(['@named_show'], 'circle', 'https://a/n.mp3', database=path, at=now - 60)
        named = {row['tg']: row for row in economics.economics(
            days=30, database=path, now=now, server_usd_month=10)['users']}
        _assert_eq(named[PAYER]['circle'], 2, "a channel kept by @name counts for its owner too")

        usage.record_deliveries([int(config.creatorId)], 'rec', 'https://a/me.mp3', database=path, at=now - 60)
        mine = {row['tg']: row for row in economics.economics(
            days=30, database=path, now=now, server_usd_month=10)['users']}
        _assert_eq(mine[int(config.creatorId)]['segment'], 'trial', "the creator's own tests do not make a payer")

        quiet = economics.economics(days=7, database=path, now=now + 30 * 86400, server_usd_month=10)
        _assert_eq(quiet['users'], [], 'a period without events lists nobody')
        _assert_close(quiet['totals']['margin_usd'], -10 * 7 / 30, 'the bill is paid anyway')
    print("all economics tests passed")


if __name__ == '__main__':
    main()
