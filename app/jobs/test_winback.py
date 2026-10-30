# -*- coding: utf-8 -*-
"""Win-back: a schedule starts only when a Relay plan stops (the old expiries
are never mailed), each message goes at most once, a flood wait retries it,
a user back on a plan or gone hears nothing, and the discount is offered
until it is spent (open from the end of a trial that offered it). Each
message sent is a `winback_sent` event; its buttons carry the source `wb`.
Temp DB only.

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
from app.service import analytics_events  # noqa: E402
from app.service.payment.offers import (  # noqa: E402
    WINBACK_OFFER, WINBACK_OFFER_FLAG, mark_offer_sent, offer_open)
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
    for tg in (701, 702, 703, 704, 705, 706, 707):
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


EVENTS = []


def _run(path, telegram, at):
    def track(telegram_id, event, properties=None, database=None, **_kw):
        EVENTS.append((telegram_id, event, properties))
        return True
    with patch.object(job, '_send', telegram), patch.object(analytics_events, 'track', track):
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
    _assert_eq(_cta(telegram.sent[0][1]), {'tp': 'bs_stars_pay', 'o': WINBACK_OFFER, 's': 'wb'},
               "it carries the offer's invoice, its tap says it came from win-back")
    _assert_eq(telegram.sent[0][1]['reply_markup'][1][0]['callback_data'], {'tp': 'bs_trfs', 's': 'wb'},
               "with change-plan next to it")
    _assert_eq(EVENTS[-1], (701, 'winback_sent', {'stage': 0, 'offer': True}),
               "the message is counted, with its offer")
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
    _assert_eq(_cta(telegram.sent[0][1]), {'tp': 'bs_stars_pay', 's': 'wb'},
               "the next time Relay stops, the plain invoice without a discount")
    _assert_eq([props for chat, _e, props in EVENTS if chat == 701][-1], {'stage': 0, 'offer': False},
               "counted without an offer")


def trial_end_offer(path):
    """The end of a trial offered the discount (D-3 or plan-off): open at once, before
    any win-back message, and the first win-back message repeats it."""
    telegram = _Telegram()
    _assert_eq(offer_open(707, WINBACK_OFFER, database=path), False, "not offered: closed")
    mark_offer_sent(707, now=T0, database=path)
    _assert_eq(offer_open(707, WINBACK_OFFER, database=path), True,
               "offered at the end of the trial: open with no win-back message yet")
    job.start_winback([{'telegramId': 707, 'tlevel': RELAY}], now=T0, database=path)
    _assert_eq(offer_open(707, WINBACK_OFFER, database=path), True, "a new schedule does not close it")
    _run(path, telegram, T0 + 7 * DAY)
    _assert_eq(_cta(telegram.sent[0][1])['o'], WINBACK_OFFER, "the week's message repeats the offer")
    db = SQLighter(path)
    try:
        db.set_user_flag(707, WINBACK_OFFER_FLAG)
    finally:
        db.close()
    _assert_eq(offer_open(707, WINBACK_OFFER, database=path), False, "spent: closed, whoever offered it")


def main():
    path = _temp_db()
    try:
        schedule(path)
        at_most_once(path)
        flood(path)
        back_or_gone(path)
        spent_offer(path)
        trial_end_offer(path)
    finally:
        os.remove(path)
    print("all winback checks passed")


if __name__ == "__main__":
    main()
