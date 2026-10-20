# -*- coding: utf-8 -*-
"""Win-back: a schedule starts only when a Relay plan stops (the old expiries
are never mailed), each message goes at most once, a flood wait retries it,
a user back on a plan or gone hears nothing, and the discount is offered
until it is spent. Temp DB only.

Run from the repo root: python app/jobs/test_winback.py
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.sender.outbox import OutboxRetryableError  # noqa: E402
from app.jobs import winback as job  # noqa: E402
from app.service.payment.offers import WINBACK_OFFER, WINBACK_OFFER_FLAG, offer_open  # noqa: E402
from db import winback  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402

DAY = 24 * 60 * 60
T0 = 1_800_000_000
RELAY, BRONZE = 3, 1


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE,
            lang TEXT, ref_id INTEGER, bitrate INTEGER);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER,
            notify_count INTEGER, compression INTEGER, channel_control INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
            balance INTEGER, notify_count INTEGER, time_left INTEGER);
        INSERT INTO tariffs VALUES (1, 1, 50, 30, 0, 0), (3, 3, 500, -1, 0, 1);
    """)
    conn.commit()
    conn.close()
    db = SQLighter(path)
    for tg in (701, 702, 703, 704, 705, 706):
        db.register_new_user(tg, 'en')
        db.subscribeUserToTariffByTg(tg, 3, 0, 0, -1)  # Relay has just stopped
    db.close()
    return path


class _Telegram:
    def __init__(self):
        self.sent = []
        self.flood = False

    def __call__(self, chat_id, messages):
        if self.flood:
            raise OutboxRetryableError("FLOOD_WAIT_30")
        self.sent.append((chat_id, messages[0]))
        return [{}]


def _run(path, telegram, at):
    with patch.object(job, '_send', telegram):
        return job.send_winback_messages(now=at, database=path)


def _cta(message):
    return message['reply_markup'][0][0]['callback_data']


def schedule(path):
    telegram = _Telegram()
    job.start_winback([{'telegramId': 701, 'tlevel': RELAY},
                       {'telegramId': 702, 'tlevel': BRONZE}], now=T0, database=path)
    _assert_eq(winback.messages_sent(702, database=path), None,
               "a Bronze plan that stops gets no Relay win-back")
    _assert_eq(_run(path, telegram, T0 + 6 * DAY), 0, "nothing before a week")
    _assert_eq(offer_open(701, WINBACK_OFFER, database=path), False,
               "the offer is not open before it is sent")
    _assert_eq(_run(path, telegram, T0 + 7 * DAY), 1, "the first message after a week")
    _assert_eq(_cta(telegram.sent[0][1]), {'tp': 'bs_stars_pay', 'o': WINBACK_OFFER},
               "it carries the offer's invoice")
    _assert_eq(telegram.sent[0][1]['reply_markup'][1][0]['callback_data']['tp'], 'bs_trfs',
               "with change-plan next to it")
    _assert_eq(_run(path, telegram, T0 + 8 * DAY), 0, "and is never sent twice")
    _assert_eq(offer_open(701, WINBACK_OFFER, database=path), True, "the offer is open once sent")
    _assert_eq(_run(path, telegram, T0 + 30 * DAY), 1, "the last message after a month")
    _assert_eq(_run(path, telegram, T0 + 90 * DAY), 0, "and nothing after it")
    _assert_eq(offer_open(701, WINBACK_OFFER, database=path), True,
               "a finished schedule keeps the offer open")
    _assert_eq([chat for chat, _ in telegram.sent], [701, 701], "one user, two messages")


def at_most_once(path):
    winback.start(703, now=T0, database=path)
    _assert_eq(winback.claim(703, 0, database=path), True, "one worker takes a message")
    _assert_eq(winback.claim(703, 0, database=path), False, "a second cannot take it again")


def flood(path):
    telegram = _Telegram()
    winback.start(704, now=T0, database=path)
    telegram.flood = True
    _assert_eq(_run(path, telegram, T0 + 7 * DAY), 0, "a flood wait sends nothing")
    _assert_eq(winback.messages_sent(704, database=path), 0, "and gives the message back")
    telegram.flood = False
    _assert_eq(_run(path, telegram, T0 + 7 * DAY + 3600), 1, "the next hour sends it")


def back_or_gone(path):
    telegram = _Telegram()
    winback.start(705, now=T0, database=path)
    winback.start(706, now=T0, database=path)
    db = SQLighter(path)
    try:
        db.subscribeUserToTariffByTg(705, 3, 0, 700, -1)  # paid in between
        db.mark_user_deleted_tg(706)                       # blocked the bot
    finally:
        db.close()
    _assert_eq(_run(path, telegram, T0 + 7 * DAY), 0, "back on a plan or gone: nothing sent")
    _assert_eq(winback.messages_sent(705, database=path), None, "the schedule ends")


def spent_offer(path):
    telegram = _Telegram()
    db = SQLighter(path)
    try:
        db.set_user_flag(701, WINBACK_OFFER_FLAG)
    finally:
        db.close()
    _assert_eq(offer_open(701, WINBACK_OFFER, database=path), False, "a spent offer is closed")
    job.start_winback([{'telegramId': 701, 'tlevel': RELAY}], now=T0 + 100 * DAY, database=path)
    _run(path, telegram, T0 + 107 * DAY)
    _assert_eq(_cta(telegram.sent[0][1]), {'tp': 'bs_stars_pay'},
               "the next time Relay stops, the plain invoice without a discount")


def main():
    path = _temp_db()
    try:
        schedule(path)
        at_most_once(path)
        flood(path)
        back_or_gone(path)
        spent_offer(path)
    finally:
        os.remove(path)
    print("all winback checks passed")


if __name__ == "__main__":
    main()
