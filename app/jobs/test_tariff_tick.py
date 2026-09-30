# -*- coding: utf-8 -*-
"""Hourly tariff clock keeps a paying user on the tariff. Temp DB only.

A user whose balance covers the next period must never be read as "no
tariff" between two ticks: that hour the updater put them on the nosub
list, sent the "without Relay" digest and moved last_guid past the
episode. Run from the repo root: python app/jobs/test_tariff_tick.py
"""
import datetime
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs.nosub_digest import DIGEST_COOLDOWN, should_send_nosub_digest  # noqa: E402
from app.jobs.tariff_tick import run_tariff_tick  # noqa: E402
from config import tariff_period  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402

CHANNEL_ID = 7
PRICE = 500

PAYER = 101         # Relay, balance covers many periods
SHORT = 102         # Relay, balance below the price
DELETED = 103       # blocked the bot on the last hour
TOPPED_UP = 104     # expired earlier, balance credited since


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _schema(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegramId INTEGER NOT NULL UNIQUE,
            lang char(15),
            deleted_at TEXT
        );
        CREATE TABLE tariffs (
            id INTEGER PRIMARY KEY,
            level INTEGER NOT NULL,
            price INTEGER NOT NULL,
            notify_count INTEGER NOT NULL
        );
        CREATE TABLE user_tariff_cs (
            id INTEGER PRIMARY KEY,
            uid INTEGER NOT NULL,
            tariff_id INTEGER NOT NULL,
            balance INTEGER,
            notify_count INTEGER,
            time_left INTEGER
        );
        CREATE TABLE user_channel_cs (
            id INTEGER PRIMARY KEY,
            user_telegram_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            last_guid TEXT,
            last_date TEXT,
            notify INTEGER
        );
    """)
    conn.execute(
        "INSERT INTO tariffs (id, level, price, notify_count) VALUES (3, 3, ?, -1)",
        (PRICE,))
    conn.commit()


def _add_user(conn, telegram_id, balance, time_left, deleted_at=None):
    conn.execute(
        "INSERT INTO users (telegramId, lang, deleted_at) VALUES (?, 'en', ?)",
        (telegram_id, deleted_at))
    uid = conn.execute(
        "SELECT id FROM users WHERE telegramId = ?", (telegram_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO user_tariff_cs "
        "(uid, tariff_id, balance, notify_count, time_left) "
        "VALUES (?, 3, ?, -1, ?)",
        (uid, balance, time_left))
    conn.execute(
        "INSERT INTO user_channel_cs "
        "(user_telegram_id, channel_id, last_guid, notify) "
        "VALUES (?, ?, 'old-ep', 1)",
        (telegram_id, CHANNEL_ID))
    conn.commit()


def _state(path, telegram_id):
    """What the updater and digest_watcher see for this user right now."""
    db = SQLighter(path)
    try:
        row = db.connection.execute(
            "SELECT utc.time_left, utc.balance FROM user_tariff_cs utc "
            "INNER JOIN users u ON u.id = utc.uid WHERE u.telegramId = ?",
            (telegram_id,)).fetchone()
        paid = [c['user_telegram_id'] for c in db.get_uccs_by_channel(
            CHANNEL_ID, have_subscription=True, notifications_enabled=True)]
        nosub = [c['user_telegram_id'] for c in db.get_uccs_by_channel(
            CHANNEL_ID, have_subscription=False, notifications_enabled=True)]
        has_tariff = db.is_user_have_bot_subscription(telegram_id)
        digest = should_send_nosub_digest(
            db.get_user_by_tg(telegram_id),
            now=datetime.datetime.utcnow() + 2 * DIGEST_COOLDOWN,
            has_tariff=has_tariff)
    finally:
        db.close()
    return {
        'time_left': row['time_left'], 'balance': row['balance'],
        'paid': telegram_id in paid, 'nosub': telegram_id in nosub,
        'has_tariff': has_tariff, 'digest': digest,
    }


def _ids(rows):
    return [row['telegramId'] for row in rows]


def main():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        db = SQLighter(path)
        try:
            _schema(db.connection)
            _add_user(db.connection, PAYER, 31246, 2)
            _add_user(db.connection, SHORT, 100, 2)
            _add_user(db.connection, DELETED, 10000, 1, deleted_at="2026-01-01")
            _add_user(db.connection, TOPPED_UP, 1000, 0)
        finally:
            db.close()

        # 07:00 — payer has two hours left
        prolonged, not_prolonged, _ = run_tariff_tick(database=path)
        _assert_eq(_ids(prolonged), [TOPPED_UP], "expired user with balance renews")
        _assert_eq(_ids(not_prolonged), [], "nobody warned yet")
        _assert_eq(_state(path, TOPPED_UP)['time_left'], tariff_period - 1,
                   "topped-up user counts down from a full period")

        # 08:00 — payer's last hour: renewed now, not an hour later
        prolonged, not_prolonged, _ = run_tariff_tick(database=path)
        _assert_eq(_ids(prolonged), [PAYER], "payer renewed on the last hour")
        payer = _state(path, PAYER)
        _assert_eq(payer['time_left'], tariff_period, "renewal keeps the full period")
        _assert_eq(payer['balance'], 31246 - PRICE, "charged once")
        _assert(payer['paid'] and not payer['nosub'], "payer stays on the paid list")
        _assert(payer['has_tariff'], "payer still has a tariff")
        _assert(not payer['digest'], "payer gets no 'without Relay' digest")

        _assert_eq(_ids(not_prolonged), [SHORT], "short balance is warned")
        short = _state(path, SHORT)
        _assert_eq(short['time_left'], 0, "short balance expires")
        _assert(short['nosub'] and not short['paid'], "expired user is on the nosub list")
        _assert(short['digest'], "expired user may get the digest")

        deleted = _state(path, DELETED)
        _assert_eq(deleted['time_left'], 1, "deleted user's clock is frozen")
        _assert_eq(deleted['balance'], 10000, "deleted user is not charged")

        # 09:00 — nothing repeats
        prolonged, not_prolonged, _ = run_tariff_tick(database=path)
        _assert_eq(_ids(prolonged), [], "no second charge next hour")
        _assert_eq(_ids(not_prolonged), [], "expiry warning is sent once")
        _assert_eq(_state(path, PAYER)['time_left'], tariff_period - 1, "payer counts down")

        # A full period hour by hour: the payer is never read as free.
        charged_before = _state(path, PAYER)['balance']
        renewals = 0
        for _hour in range(tariff_period + 1):
            prolonged, _, _ = run_tariff_tick(database=path)
            renewals += _ids(prolonged).count(PAYER)
            payer = _state(path, PAYER)
            if payer['time_left'] <= 0 or not payer['paid'] or payer['nosub'] \
                    or payer['digest']:
                raise AssertionError("payer read as free after a tick: %r" % payer)
        _assert_eq(renewals, 1, "one renewal per period")
        _assert_eq(_state(path, PAYER)['balance'], charged_before - PRICE,
                   "one charge per period")
    finally:
        os.remove(path)

    print("all tariff tick checks passed")


if __name__ == "__main__":
    main()
