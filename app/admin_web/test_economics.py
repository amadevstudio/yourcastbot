# -*- coding: utf-8 -*-
"""Admin economics: segments, revenue without the creator's tests (what a payment
charged, not the full price a bundle or an offer credits), the server bill
spread by load, a channel's deliveries counted for its owner; AI by plan: the
rates read from what was made, the worst month of each plan, what its chats used.

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
from db import ai, usage  # noqa: E402

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


def _ai_plans(path, now):
    empty = economics.economics(days=30, database=path, now=now, server_usd_month=10)['ai']
    _assert_eq(empty['rates']['whisper'], {'usd': None, 'n': 0}, 'no transcript made: no rate')
    _assert_eq([p['key'] for p in empty['plans']], ['1', '3', 'trial'], 'a row per plan level, then trials')
    _assert_eq(empty['plans'][0]['worst_whisper_usd'], None, 'no rate, no worst month')

    # an hour of Whisper for $0.015 and its summary ($0.017 with it: the model call $0.002);
    # 2 h of the paid model for $0.20; a summary of a transcript made long before ($0.004); a question
    ai.save_transcript('w', 'text', 'whisper', 0.015, 3600, database=path)
    ai.save_summary('w', 'en', 'sum', 0.017, database=path)
    ai.save_transcript('g', 'text', 'speakers', 0.20, 7200, database=path)
    ai.save_transcript('feed', 'text', 'feed', 0.0, 0, database=path)
    ai.save_summary('feed', 'en', 'sum', 0.004, database=path)
    usage.record_ask(PAYER, 'w', 0.001, database=path, at=now - 60)
    conn = ai.connect(path)
    conn.execute("UPDATE ai_transcripts SET created_at = created_at - 30")
    conn.execute("INSERT INTO ai_requests (chat_id, ref, lang, status, created_at, seconds) VALUES "
                 "(?, 'w', 'en', 'done', ?, 5400), (?, 'g', 'en', 'failed', ?, 7200), (?, 'x', 'en', 'done', ?, 1800)",
                 (PAYER, now - 60, PAYER, now - 60, TRIAL, now - 60))
    conn.commit()
    conn.close()

    original = config.ai_paid_transcribe_model
    try:
        config.ai_paid_transcribe_model = 'some/stt'
        report = economics.economics(days=30, database=path, now=now, server_usd_month=10)['ai']
        config.ai_paid_transcribe_model = ''
        off = economics.economics(days=30, database=path, now=now, server_usd_month=10)['ai']
    finally:
        config.ai_paid_transcribe_model = original
    rates = report['rates']
    _assert_close(rates['whisper']['usd'], 0.015, 'Whisper: what it charged per hour')
    _assert_close(rates['speakers']['usd'], 0.10, 'the paid model per hour')
    _assert_close(rates['summary']['usd'], 0.003, "a summary is the model call: its transcript's cost taken off")
    _assert_eq(rates['summary']['n'], 2, 'a summary of a free transcript counts as it is')
    _assert_close(rates['question']['usd'], 0.001, 'a question')

    plans = {p['key']: p for p in report['plans']}
    relay = plans['3']
    hours = config.ai_summary_hours_per_month[3]
    month_of_questions = config.ai_questions_per_month[3] * 0.001
    paid_hours = config.ai_paid_transcribe_hours_per_month[3]
    _assert_close(relay['price_usd'], 5.0, "the plan's price")
    _assert_close(relay['worst_whisper_usd'], min(hours * (0.015 + 0.003) + month_of_questions, relay['cap_usd']),
                  'worst month: every hour new audio, a summary per hour, every question of the 30 days')
    _assert_close(relay['worst_paid_usd'], min(paid_hours * 0.10 + (hours - paid_hours) * 0.015 + hours * 0.003
                                               + month_of_questions, relay['cap_usd']),
                  'the paid model for its hours, Whisper for the rest, never above the budget')
    _assert_close(relay['cap_usd'], 5.0 * config.ai_budget_share, "the budget: a share of the plan's price")
    _assert_eq(all(p['cap_usd'] <= p['net_usd'] for p in report['plans'] if p['cap_usd'] is not None), True,
               'no plan may cost more in AI than it brings')
    # the AI quota's "paid for": the creator's own payment counts there (it is not revenue above)
    _assert_eq(relay['chats'], 2 if int(config.creatorId) else 1, 'chats with the plan running that paid for it')
    _assert_close(relay['hours_used'], 1.5, 'hours charged by requests done, not failed ones')
    _assert_close(relay['max_hours'], 1.5, 'the most one chat used')
    trial = plans['trial']
    _assert_eq(trial['worst_paid_usd'], None, 'a trial never gets the paid model')
    _assert_close(trial['worst_whisper_usd'], config.ai_summary_trial_hours * 0.018
                  + config.ai_trial_questions_per_month * 0.001, "a trial's hours and its 30 days' questions")
    _assert_close(trial['hours_used'], 0.5, "a trial's hours")
    _assert_close(trial['ai_usd'], 0.25, "a trial's AI spend in the period")
    _assert_eq({p['key']: p['worst_paid_usd'] for p in off['plans']}['3'], None,
               'no paid model configured: no worst month with it')


def _payout_share(path, now):
    """What reaches us: a Stars payment at its share, other methods whole; a plan's price too."""
    original = config.payout_share
    try:
        config.payout_share = {'telegramStars': 0.9}
        report = economics.economics(days=30, database=path, now=now, server_usd_month=10)
    finally:
        config.payout_share = original
    users = {row['tg']: row for row in report['users']}
    _assert_close(users[PAYER]['revenue_usd'], (5.0 + 3.5) * 0.9, 'Stars revenue at the share that reaches us')
    _assert_close({p['key']: p for p in report['ai']['plans']}['3']['net_usd'], 4.5, "a plan's price at the Stars share")
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO payment_history VALUES (1, 'cryptoBot', 'cb', '', 'paid', 100, ?, NULL)",
                 (datetime.datetime.fromtimestamp(now - 60).strftime('%Y-%m-%d %H:%M:%S.%f'),))
    conn.commit()
    conn.close()
    try:
        config.payout_share = {'telegramStars': 0.9}
        users = {row['tg']: row for row in economics.economics(
            days=30, database=path, now=now, server_usd_month=10)['users']}
    finally:
        config.payout_share = original
    _assert_close(users[PAYER]['revenue_usd'], (5.0 + 3.5) * 0.9 + 1.0, 'another method counts whole')


def main():
    config.payout_share = {}  # the figures below are what was charged
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

        # an offer credited a month ($5) and charged 70% of it: revenue is the charge
        from db import payments
        conn = sqlite3.connect(path)
        payments.ensure_charged_column(conn)
        conn.execute("INSERT INTO payment_history VALUES (1, 'telegramStars', 'wb', '', 'paid', 500, ?, 350)",
                     (datetime.datetime.fromtimestamp(now - 60).strftime('%Y-%m-%d %H:%M:%S.%f'),))
        conn.commit()
        conn.close()
        charged = {row['tg']: row for row in economics.economics(
            days=30, database=path, now=now, server_usd_month=10)['users']}
        _assert_close(charged[PAYER]['revenue_usd'], 5.0 + 3.5,
                      "an offer's revenue is what it charged; rows before the column are their amount")

        _ai_plans(path, now)
        _payout_share(path, now)

        quiet = economics.economics(days=7, database=path, now=now + 30 * 86400, server_usd_month=10)
        _assert_eq(quiet['users'], [], 'a period without events lists nobody')
        _assert_close(quiet['totals']['margin_usd'], -10 * 7 / 30, 'the bill is paid anyway')
    print("all economics tests passed")


if __name__ == '__main__':
    main()
