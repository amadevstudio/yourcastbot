# -*- coding: utf-8 -*-
"""A Stars payment taken back (db/stars_refund.py, app/service/payment/stars_refund.py).

- Money still on the balance pays the refund; money already turned into days
  gives back the hours it bought at the plan's price; what the hours do not
  cover stays as a debt the next payment pays first.
- Once per payment, whichever way it is seen (the service message, the daily
  look at the bot's transactions); an unknown charge changes nothing.
- The payment stops counting as paid; the chat hears what changed.

Run from the repo root: python app/service/payment/test_stars_refund.py
"""
import datetime
import os
import sys
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.i18n.messages import get_message  # noqa: E402
from app.service.payment import stars_refund  # noqa: E402
from app.service.payment.test_referral_award import _temp_db  # noqa: E402
from db import stars_refund as db_refund  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402
from db.tariff_rows import ever_paid  # noqa: E402

STARS = db_refund.STARS_SERVICE_TYPE
RELAY, PERIOD = 3, 720  # the fixture's Relay costs 500


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _db():
    path = _temp_db()
    db = SQLighter(path)
    db.connection.execute(
        "CREATE TABLE IF NOT EXISTS payment_history (user_id integer NOT NULL, service_type text NOT NULL, "
        "invoice_id text, invoice_hash text, status text, amount integer, datetime text, "
        "PRIMARY KEY (user_id, service_type, invoice_id))")
    db.connection.commit()
    db.close()
    return path


def _user(path, telegram_id, tariff_id=0, time_left=0, balance=0):
    db = SQLighter(path)
    try:
        db.register_new_user(telegram_id, 'en')
        uid = db.connection.execute("SELECT id FROM users WHERE telegramId = ?", (telegram_id,)).fetchone()[0]
        db.connection.execute("DELETE FROM user_tariff_cs WHERE uid = ?", (uid,))
        db.connection.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) "
                              "VALUES (?, ?, ?, -1, ?)", (uid, tariff_id, balance, time_left))
        db.connection.commit()
        return uid
    finally:
        db.close()


def _pay(path, telegram_id, charge, cents=500, plan=None):
    db = SQLighter(path)
    try:
        return db.applyPaymentReplenishmentOnce(
            db.get_user_by_tg(telegram_id), STARS, charge, datetime.datetime.now(), cents, PERIOD,
            status='paid', planId=plan, planPrice=cents if plan else None)
    finally:
        db.close()


def _plan(path, uid):
    db = SQLighter(path)
    try:
        return tuple(db.connection.execute(
            "SELECT tariff_id, balance, time_left FROM user_tariff_cs WHERE uid = ?", (uid,)).fetchone())
    finally:
        db.close()


def _set_plan(path, uid, balance, time_left):
    db = SQLighter(path)
    try:
        db.connection.execute("UPDATE user_tariff_cs SET balance = ?, time_left = ? WHERE uid = ?",
                              (balance, time_left, uid))
        db.connection.commit()
    finally:
        db.close()


def _status(path, charge):
    db = SQLighter(path)
    try:
        return db.connection.execute("SELECT status FROM payment_history WHERE invoice_id = ?",
                                     (charge,)).fetchone()[0]
    finally:
        db.close()


def test_balance_and_hours():
    path = _db()
    try:
        uid = _user(path, 9101, RELAY, time_left=100)
        _pay(path, 9101, 'c-top')
        _assert(_plan(path, uid) == (RELAY, 500, 100), "a running plan is topped up")
        refund = db_refund.apply_refund('c-top', path, PERIOD)
        _assert(_plan(path, uid) == (RELAY, 0, 100) and refund['hours'] == 0,
                "money still on the balance pays the refund: the plan keeps its hours")
        _assert(_status(path, 'c-top') == 'refunded' and not ever_paid(9101, path),
                "the payment stops counting as paid")
        _assert(db_refund.apply_refund('c-top', path, PERIOD) is None and _plan(path, uid) == (RELAY, 0, 100),
                "a second refund of the same payment takes nothing")
        _assert(db_refund.apply_refund('c-unknown', path, PERIOD) is None, "an unknown charge changes nothing")

        uid2 = _user(path, 9102)
        _pay(path, 9102, 'c-on', plan=RELAY)
        _assert(_plan(path, uid2) == (RELAY, 0, PERIOD), "with no plan the payment turned Relay on")
        refund = db_refund.apply_refund('c-on', path, PERIOD)
        _assert(_plan(path, uid2) == (RELAY, 0, 0) and refund['hours'] == PERIOD,
                "the days it bought go back: the plan is off at once, no debt")

        uid3 = _user(path, 9103)
        _pay(path, 9103, 'c-half', plan=RELAY)
        _set_plan(path, uid3, 0, PERIOD // 2)  # half of the month used
        refund = db_refund.apply_refund('c-half', path, PERIOD)
        _assert(_plan(path, uid3) == (RELAY, -250, 0) and refund['balance'] == -250,
                "the hours left cover half: the rest stays as a debt")
        _pay(path, 9103, 'c-next', plan=RELAY)
        _assert(_plan(path, uid3) == (RELAY, 250, 0), "the next payment pays the debt first: Relay stays off")

        uid4 = _user(path, 9104, RELAY, time_left=PERIOD, balance=0)
        _pay(path, 9104, 'c-part')
        _set_plan(path, uid4, 200, PERIOD)  # the tick spent 300 of it on the period
        refund = db_refund.apply_refund('c-part', path, PERIOD)
        _assert(refund['hours'] == 432 and _plan(path, uid4) == (RELAY, 0, PERIOD - 432),
                "the balance pays what it can, hours at the plan's price the rest")
    finally:
        os.remove(path)


def test_notice_and_once():
    path = _db()
    try:
        uid = _user(path, 9201)
        _pay(path, 9201, 'c-1', plan=RELAY)
        _set_plan(path, uid, 0, PERIOD // 2)
        sent, told, tracked = [], [], []
        with patch.object(stars_refund.analytics_events, 'track', lambda *a, **k: tracked.append(a[1])):
            refund = stars_refund.process_refund('c-1', 'message', path, send=lambda c, m: sent.append((c, m)) or [1],
                                                 notify_creator=told.append)
            again = stars_refund.process_refund('c-1', 'transactions', path, send=lambda c, m: sent.append((c, m)),
                                                notify_creator=told.append)
        _assert(refund is not None and again is None and len(sent) == 1 and len(told) == 1,
                "the message and the daily check see one refund: one notice")
        text = sent[0][1][0]['text']
        _assert(sent[0][0] == 9201 and get_message('starsRefundPlanOff', 'en') in text and '−$2.50' in text,
                "the chat hears the plan ended and the debt")
        _assert(tracked == ['payment_refunded'] and 'user %d' % uid in told[0], "tracked, the creator told")

        uid2 = _user(path, 9202, RELAY, time_left=PERIOD, balance=200)
        _pay(path, 9202, 'c-2')
        _set_plan(path, uid2, 200, PERIOD)
        with patch.object(stars_refund.analytics_events, 'track', lambda *a, **k: None):
            stars_refund.process_refund('c-2', 'message', path, send=lambda c, m: sent.append((c, m)) or [1],
                                        notify_creator=told.append)
        text = sent[-1][1][0]['text']
        _assert('Days left: 12' in text and '−$' not in text, "a shorter plan: the days left, no debt")
    finally:
        os.remove(path)


def test_transactions():
    path = _db()
    try:
        _user(path, 9301, RELAY, time_left=100)
        _pay(path, 9301, 'c-refunded')
        _pay(path, 9301, 'c-kept')
        page = [{'id': 'other-%d' % i, 'amount': 1, 'date': 1, 'source': {'type': 'user'}} for i in range(100)]
        rest = [
            {'id': 'c-kept', 'amount': 250, 'date': 2, 'source': {'type': 'user'}},
            {'id': 'c-refunded', 'amount': 250, 'date': 3, 'source': {'type': 'user'}},
            {'id': 'c-refunded', 'amount': 250, 'date': 4, 'receiver': {'type': 'user'}},
            {'id': 'w-1', 'amount': 1000, 'date': 5, 'receiver': {'type': 'fragment'}},
        ]
        offsets = []

        def request(offset):
            offsets.append(offset)
            return {'transactions': page if offset == 0 else rest}
        with patch.object(stars_refund.analytics_events, 'track', lambda *a, **k: None):
            found = stars_refund.check_transactions(request, path, send=lambda c, m: [1], notify_creator=lambda t: None)
            again = stars_refund.check_transactions(request, path, send=lambda c, m: [1], notify_creator=lambda t: None)
        _assert(offsets[:2] == [0, 100], "every page of the transactions is read")
        _assert(found == 1 and again == 0, "an outgoing transaction with a payment's id is its refund, once")
        _assert(_status(path, 'c-refunded') == 'refunded' and _status(path, 'c-kept') == 'paid',
                "an incoming one or a withdrawal is no refund")
    finally:
        os.remove(path)


if __name__ == '__main__':
    test_balance_and_hours()
    test_notice_and_once()
    test_transactions()
    print("all stars refund checks passed")
