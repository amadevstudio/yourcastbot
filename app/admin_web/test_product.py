# -*- coding: utf-8 -*-
"""Admin product page: the newcomers' funnel (the welcome show is not a
subscription of their own), plans now (trial vs paid, trials ending without
the balance to renew), payments without the creator's tests (first-time
payers), AI summaries and questions, the digest, newcomers by week, the
share of newcomers who paid in their first 30 days.

Temporary file DB only. Run from the repo root:
python app/admin_web/test_product.py
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
from app.admin_web import product  # noqa: E402
from db import ai, usage  # noqa: E402

NEW_ACTIVE, NEW_IDLE, NEW_GONE, OLD_PAYER = 1001, 1002, 1003, 1004
PAID_EARLY, PAID_LATE, NEVER_PAID = 1006, 1007, 1008


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _setup(path, now):
    def stamp(days_ago):
        return datetime.datetime.fromtimestamp(now - days_ago * 86400).strftime('%Y-%m-%d %H:%M:%S.%f')
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER NOT NULL UNIQUE, deleted_at TEXT,
                            created_at TEXT, flags TEXT, nosub_digest_enabled INTEGER NOT NULL DEFAULT 1,
                            nosub_digest_sent_at TEXT);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
                                     balance INTEGER, notify_count INTEGER, time_left INTEGER);
        CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER, channel_id INTEGER);
        CREATE TABLE payment_history (user_id INTEGER, service_type TEXT, invoice_id TEXT,
                                      invoice_hash TEXT, status TEXT, amount INTEGER, datetime TEXT);
        INSERT INTO tariffs VALUES (3, 3, 500);
    """)
    creator = int(config.creatorId)
    conn.executemany(
        "INSERT INTO users (id, telegramId, deleted_at, created_at, flags, nosub_digest_enabled, "
        "nosub_digest_sent_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(1, NEW_ACTIVE, None, stamp(2)[:19], '{"auto_summary": true}', 1, None),
         (2, NEW_IDLE, None, stamp(10)[:19], '{"own_show_nudge": "control"}', 1, stamp(1)[:19]),
         (3, NEW_GONE, stamp(1)[:19], stamp(3)[:19], '{"own_show_nudge": "sent"}', 0, None),
         (4, OLD_PAYER, None, stamp(200)[:19], None, 1, stamp(20)[:19]),
         (5, creator, None, stamp(1)[:19], None, 1, None),
         # their first 30 days are over: paid on day 2, paid on day 40, never paid
         (6, PAID_EARLY, None, stamp(40)[:19], None, 1, None),
         (7, PAID_LATE, None, stamp(80)[:19], None, 1, None),
         (8, NEVER_PAID, None, stamp(50)[:19], None, 1, None)])
    conn.executemany("INSERT INTO user_tariff_cs VALUES (?, ?, ?, ?, -1, ?)",
                     [(1, 1, 3, 0, 48),     # paid (in the period): not a trial
                      (2, 2, 3, 600, 48),   # a trial ending, but its balance renews it
                      (3, 3, 3, 0, 300),    # a trial, blocked: not counted
                      (4, 4, 3, 0, 300),    # paid
                      (5, 5, 3, 0, 48)])    # the creator's tests are not payments: a trial ending
    conn.executemany("INSERT INTO user_channel_cs (user_telegram_id, channel_id) VALUES (?, ?)",
                     [(NEW_ACTIVE, product.WELCOME_CHANNEL_ID), (NEW_ACTIVE, 77),
                      (NEW_IDLE, product.WELCOME_CHANNEL_ID), (NEW_GONE, product.WELCOME_CHANNEL_ID),
                      (PAID_EARLY, 78), (NEVER_PAID, 78), (PAID_LATE, product.WELCOME_CHANNEL_ID)])
    conn.executemany("INSERT INTO payment_history VALUES (?, 'telegramStars', ?, '', ?, ?, ?)",
                     [(1, 'a', 'paid', 500, stamp(1)),         # a newcomer pays: first time
                      (4, 'b', 'paid', 500, stamp(5)),         # an old payer again
                      (4, 'old', 'paid', 500, stamp(100)),     # before the period
                      (2, 'c', 'canceled', 500, stamp(1)),     # not paid
                      (5, 'd', 'paid', 500, stamp(1)),         # the creator's own test
                      (6, 'e', 'paid', 500, stamp(38)),        # day 2 after joining
                      (7, 'f', 'paid', 500, stamp(40))])       # day 40: not in the first 30
    conn.commit()
    conn.close()
    at = now - 3600
    usage.record_deliveries([NEW_ACTIVE], 'rec', 'https://a/1.mp3', database=path, at=at)
    usage.record_deliveries([NEW_ACTIVE, OLD_PAYER], 'circle', 'https://a/2.mp3', database=path, at=at)
    usage.record_ai(NEW_ACTIVE, 'ep', 0.01, database=path, at=at)
    usage.record_ask(NEW_ACTIVE, 'ep', 0.001, database=path, at=at)
    usage.record_ask(NEW_ACTIVE, 'ep', 0.001, database=path, at=at)
    ai.enqueue(NEW_ACTIVE, 'ep', 'original', 600, database=path)
    request_id, _ = ai.enqueue(OLD_PAYER, 'ep2', 'original', 600, database=path, auto=True)
    ai.finish(request_id, 'failed', database=path)


def main():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'test.sqlite')
        _setup(path, now)
        later = time.time()  # the AI queue stamps its rows itself
        report = product.product(days=30, database=path, now=later)

        _assert_eq(report['newcomers'], {'new': 4, 'own_sub': 1, 'got_episode': 1, 'asked_summary': 1,
                                         'paid': 1, 'blocked': 1},
                   "newcomers: the welcome show is not their own, the creator's test is not a payment")
        _assert_eq(sum(week['new'] for week in report['weeks']), 4, 'every newcomer is in a week')
        _assert_eq(report['weeks'][0]['week'] >= report['weeks'][-1]['week'], True, 'the latest week first')
        _assert_eq(report['plans'], {'paid': 2, 'trial': 2, 'trial_ending': 1},
                   'plans now: a blocked user is not counted, a trial with the balance to renew is not ending')
        _assert_eq(report['payments'], {'payments': 2, 'payers': 2, 'first_time': 1, 'revenue_usd': 10.0},
                   "payments in the period, the creator's tests left out")
        got = report['ai']
        _assert_eq((got['summary_taps'], got['summary_auto'], got['summary_failed'], got['summary_chats']),
                   (1, 1, 1, 2), 'summaries: taps and automatic ones')
        _assert_eq((got['questions'], got['question_chats'], got['auto_on']), (2, 1, 1), 'questions, auto opt-ins')
        _assert_eq(got['ai_usd'], 0.012, 'AI spend: summaries and questions')
        _assert_eq(report['activity'], {'clickers': 1, 'clicks': 1, 'automatic': 2, 'listeners': 2},
                   'who got episodes')
        _assert_eq(report['nudge'], [
            {'group': 'control', 'new': 1, 'own_sub': 0, 'got_episode': 0, 'blocked': 0, 'paid': 0},
            {'group': 'sent', 'new': 1, 'own_sub': 0, 'got_episode': 0, 'blocked': 1, 'paid': 0}],
            "the own-show nudge's A/B: newcomers by group, the unmarked ones left out")
        _assert_eq(report['digest'], {'last_week': 1, 'muted': 0}, 'digest: last week, a blocked user left out')

        _assert_eq(report['paid_first_days'], {'days': 30, 'matured': 0, 'paid': 0, 'own_sub': 0,
                                               'own_sub_paid': 0},
                   "30 days back: nobody's first 30 days are over yet")
        quarter = product.product(days=90, database=path, now=later)
        _assert_eq(quarter['paid_first_days'], {'days': 30, 'matured': 3, 'paid': 1, 'own_sub': 2,
                                                'own_sub_paid': 1},
                   'paid in the first 30 days: day 2 counts, day 40 does not; of those with a show of their own')

        from db import payments
        conn = sqlite3.connect(path)
        payments.ensure_charged_column(conn)
        conn.execute("UPDATE payment_history SET charged = 350 WHERE amount = 500 AND status = 'paid' "
                     "AND rowid = (SELECT MIN(rowid) FROM payment_history WHERE status = 'paid')")
        conn.commit()
        conn.close()
        _assert_eq(product.product(days=30, database=path, now=later)['payments']['revenue_usd'], 8.5,
                   "revenue is what a payment charged: an offer's month counts 70%")

        week = product.product(days=7, database=path, now=later)
        _assert_eq(week['newcomers']['new'], 3, 'a shorter period, fewer newcomers')

        empty = os.path.join(tmp, 'empty.sqlite')
        sqlite3.connect(empty).executescript(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, deleted_at TEXT, created_at TEXT,"
            " flags TEXT, nosub_digest_enabled INTEGER, nosub_digest_sent_at TEXT);"
            "CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER);"
            "CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,"
            " balance INTEGER, notify_count INTEGER, time_left INTEGER);"
            "CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER, channel_id INTEGER);"
            "CREATE TABLE payment_history (user_id INTEGER, service_type TEXT, invoice_id TEXT,"
            " invoice_hash TEXT, status TEXT, amount INTEGER, datetime TEXT);")
        blank = product.product(days=30, database=empty, now=now)
        _assert_eq((blank['newcomers']['new'], blank['ledger_since'], blank['weeks']), (0, None, []),
                   'a database without the ledger yet: zeros, no error')
    print("all product tests passed")


if __name__ == '__main__':
    main()
