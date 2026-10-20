# -*- coding: utf-8 -*-
"""Stars invoices: prepaid months of Relay charge the discounted price and
credit the full one, once per charge; a payload cannot pick its own discount;
top-up invoices sent before bundles existed still pass; the win-back offer
is billed only to a user it was sent to, closes at the pre-checkout once
spent, and a payment that went through is credited whatever happened since.
A payment turns on the plan it was for when no plan runs (a running one is
only topped up); prepaid months are not sold to a running Bronze or Silver,
and the longest bundle is one tap from /subscription.

Needs the bot's requirements (starsPaymentModule imports telebot).
Run from the repo root: python app/service/payment/test_stars_invoice.py
"""
import json
import os
import sqlite3
import sys
import tempfile
import types
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.payment.offers import bundle_discount, charged_cents  # noqa: E402

RATE = 1300
TARIFFS = [{'id': 1, 'level': 1, 'price': 50, 'notify_count': 30, 'compression': 0,
            'channel_control': 0},
           {'id': 3, 'level': 3, 'price': 500, 'notify_count': -1, 'compression': 0,
            'channel_control': 1}]


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


class _TariffsDB:
    subscription = None  # the payer's user_tariff_cs row

    def __init__(self, _path):
        pass

    def getTariffs(self, channel_control=None):
        return TARIFFS

    def getUserSubscriptionByTg(self, _chat_id):
        return self.subscription

    def close(self):
        pass


def _invoice(stars, chat_id, callback):
    sent = []
    data = {'chat_id': chat_id, 'language_code': 'en', 'message': None,
            'callback': types.SimpleNamespace(data=json.dumps(callback)),
            'united_data': {k: v for k, v in callback.items() if k != 'tp'}}
    with patch.object(stars, 'SQLighter', _TariffsDB), \
            patch.object(stars, 'get_invoice_stars_withdraw_rate_x1000', lambda: RATE), \
            patch.object(stars, 'notify', lambda *a, **kw: None), \
            patch.object(stars.bot, 'send_invoice', lambda *a, **kw: sent.append(a)):
        stars.send_invoice(data)
    return sent


def pricing():
    _assert_eq(bundle_discount(1), 0, "one month is a plain top-up")
    _assert_eq(bundle_discount(5), None, "months that are not sold have no price")
    _assert_eq(charged_cents(3000, 15), 2550, "6 months at 15% off")
    _assert_eq(charged_cents(1001, 10), 901, "the discounted charge rounds up to a cent")


def bundle_invoice(stars):
    sent = _invoice(stars, 601, {'tp': 'bs_stars_pay', 'v': 3, 'm': 6})
    payload = json.loads(sent[0][3])
    _assert_eq((payload['b'], payload['m'], payload['d']), (3000, 6, 15),
               "6 months credit 6 prices, with the bundle's discount")
    _assert_eq(payload['s'], stars.stars_for_balance(2550, RATE), "and charge the discounted price")
    _assert_eq(sent[0][6][0].amount, payload['s'], "the invoice asks exactly that")
    _assert(stars.validate_precheckout_payload(sent[0][3], 601, 'XTR', payload['s'])[0],
            "the bundle passes the pre-checkout")
    _assert_eq(_invoice(stars, 601, {'tp': 'bs_stars_pay', 'v': 1, 'm': 6}), [],
               "prepaid months are Relay's only")
    _assert_eq(_invoice(stars, 601, {'tp': 'bs_stars_pay', 'v': 3, 'm': 5}), [],
               "months that are not sold get no invoice")
    _assert_eq(payload['v'], 3, "the invoice names the plan it is for")
    bronze = {'tariff_id': 1, 'balance': 0, 'time_left': 100, 'notify_count': 30}
    with patch.object(_TariffsDB, 'subscription', bronze):
        _assert_eq(_invoice(stars, 601, {'tp': 'bs_stars_pay', 'v': 3, 'm': 12}), [],
                   "a running Bronze is not sold Relay's months (it would renew Bronze)")
        _assert_eq(len(_invoice(stars, 601, {'tp': 'bs_stars_pay', 'v': 3})), 1,
                   "but can top up as before")


def precheckout(stars):
    forged = stars.create_payload(602, 3000, stars.stars_to_charge(3000, RATE, 60), RATE, 6, 60)
    _assert_eq(stars.validate_precheckout_payload(forged, 602, 'XTR', json.loads(forged)['s']),
               (False, "Invalid payment offer"), "a payload cannot choose its own discount")
    legacy = json.dumps({'t': 602, 'b': 500, 's': stars.stars_for_balance(500, RATE),
                         'r': RATE, 'p': 'old'})
    _assert(stars.validate_precheckout_payload(legacy, 602, 'XTR', json.loads(legacy)['s'])[0],
            "an invoice sent before bundles still passes")
    _assert_eq('m' in json.loads(stars.create_payload(602, 500, 385, RATE)), False,
               "a plain top-up keeps the old payload")
    sold = stars.create_payload(602, 3000, stars.stars_to_charge(3000, RATE, 15), RATE, 6, 15)
    with patch.object(stars, 'offer_discount', lambda *_: 20):
        _assert_eq(stars.validate_precheckout_payload(sold, 602, 'XTR', json.loads(sold)['s'])[0],
                   False, "after a discount change an old invoice is refused before payment")
        _assert_eq(stars.validate_payment_payload(sold, 602, 'XTR', json.loads(sold)['s']),
                   (True, None), "but one already paid is credited as it was sold")


def _temp_db():
    from db.sqliteAdapter import SQLighter
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
        CREATE TABLE payment_history (id INTEGER PRIMARY KEY, user_id INTEGER,
            service_type TEXT, invoice_id TEXT, invoice_hash TEXT, status TEXT,
            amount INTEGER, datetime TEXT);
        INSERT INTO tariffs VALUES (1, 1, 50, 30, 0, 0), (3, 3, 500, -1, 0, 1);
    """)
    conn.commit()
    conn.close()
    db = SQLighter(path)
    db.register_new_user(603, 'en')
    db.subscribeUserToTariffByTg(603, 3, 0, 0, -1)  # the Relay trial has ended
    db.close()
    return path


def _pay(stars, path, chat_id, payload, charge):
    with patch.object(stars.config, 'db_path', path), \
            patch.object(stars, 'outer_sender', lambda *a, **kw: True), \
            patch.object(stars, 'award_referrer_for_payment', lambda _tg: (None, None)):
        return stars.process_successful_payment(
            chat_id, 'XTR', json.loads(payload)['s'], payload, charge)


def plan_turns_on(stars):
    from db.sqliteAdapter import SQLighter
    path = _temp_db()
    db = SQLighter(path)
    try:
        for tg in (611, 612, 613, 614):
            db.register_new_user(tg, 'en')
        db.subscribeUserToTariffByTg(612, 1, 0, 0, 0)      # Bronze has ended
        db.subscribeUserToTariffByTg(613, 1, 0, 100, 30)   # Bronze runs
    finally:
        db.close()
    relay = stars.stars_for_balance(500, RATE)
    try:
        _pay(stars, path, 611, stars.create_payload(611, 500, relay, RATE, plan_id=3), 'c-611')
        _pay(stars, path, 612, stars.create_payload(612, 500, relay, RATE, plan_id=3), 'c-612')
        _pay(stars, path, 613, stars.create_payload(613, 500, relay, RATE, plan_id=3), 'c-613')
        legacy = json.dumps({'t': 614, 'b': 500, 's': relay, 'r': RATE, 'p': 'old'})
        _pay(stars, path, 614, legacy, 'c-614')
        db = SQLighter(path)
        try:
            plans = {tg: db.getUserSubscriptionByTg(tg) for tg in (611, 612, 613, 614)}
        finally:
            db.close()
        state = {tg: (p['tariff_id'], p['time_left'], p['balance']) for tg, p in plans.items()}
        period = stars.config.tariff_period
        _assert_eq(state[611], (3, period, 0), "a free user who paid for Relay has Relay on")
        _assert_eq(state[612], (3, period, 0), "an ended Bronze paid for Relay switches to Relay")
        _assert_eq(state[613], (1, 100, 500), "a running Bronze is only topped up")
        _assert_eq(state[614], (0, 0, 500), "an invoice from before keeps the old top-up")
    finally:
        os.remove(path)


def credit_once(stars):
    from db.sqliteAdapter import SQLighter
    path = _temp_db()
    try:
        s = stars.stars_to_charge(3000, RATE, 15)
        payload = stars.create_payload(603, 3000, s, RATE, 6, 15)
        with patch.object(stars.config, 'db_path', path), \
                patch.object(stars, 'outer_sender', lambda *a, **kw: True), \
                patch.object(stars, 'award_referrer_for_payment', lambda _tg: (None, None)):
            first = stars.process_successful_payment(603, 'XTR', s, payload, 'charge-1')
            again = stars.process_successful_payment(603, 'XTR', s, payload, 'charge-1')
        db = SQLighter(path)
        try:
            plan = db.getUserSubscriptionByTg(603)
        finally:
            db.close()
        _assert_eq((first, again), (True, False), "a charge is applied once, a redelivery is not")
        _assert_eq((plan['tariff_id'], plan['time_left'], plan['balance']),
                   (3, stars.config.tariff_period, 2500),
                   "Relay renews at once and 5 more months stay on the balance")
    finally:
        os.remove(path)


def winback_offer(stars):
    from db import winback
    from db.sqliteAdapter import SQLighter
    from app.service.payment import offers
    path = _temp_db()
    try:
        with patch.object(offers, 'db_path', path), patch.object(winback, 'db_path', path):
            _assert_eq(_invoice(stars, 603, {'tp': 'bs_stars_pay', 'o': 'wb'}), [],
                       "no offer invoice for a user who was not sent the offer")
            winback.start(603, now=0)
            winback.claim(603, 0)  # the first win-back message went out
            sent = _invoice(stars, 603, {'tp': 'bs_stars_pay', 'o': 'wb'})
            payload = json.loads(sent[0][3])
            _assert_eq((payload['b'], payload['m'], payload['d'], payload['o']), (500, 1, 30, 'wb'),
                       "the offer credits one month of Relay at 30% off")
            _assert_eq(payload['s'], stars.stars_for_balance(350, RATE), "and charges 70%")
            _assert(stars.validate_precheckout_payload(sent[0][3], 603, 'XTR', payload['s'])[0],
                    "an open offer passes the pre-checkout")
            with patch.object(stars.config, 'db_path', path), \
                    patch.object(stars, 'outer_sender', lambda *a, **kw: True), \
                    patch.object(stars, 'award_referrer_for_payment', lambda _tg: (None, None)):
                _assert_eq(stars.process_successful_payment(
                    603, 'XTR', payload['s'], sent[0][3], 'charge-wb-1'), True, "the offer is paid")
                _assert_eq(stars.validate_precheckout_payload(
                    sent[0][3], 603, 'XTR', payload['s']),
                    (False, "Offer is no longer available"), "a spent offer closes at the pre-checkout")
                _assert_eq(stars.process_successful_payment(
                    603, 'XTR', payload['s'], sent[0][3], 'charge-wb-2'), True,
                    "a second payment that got through anyway is still credited")
            db = SQLighter(path)
            try:
                _assert_eq(db.get_user_flag(603, offers.WINBACK_OFFER_FLAG), 1,
                           "the offer is spent with the payment that used it")
                _assert_eq(db.getUserSubscriptionByTg(603)['balance'], 500,
                           "both payments credited: Relay renewed and a month on the balance")
            finally:
                db.close()
    finally:
        os.remove(path)


def page_rows(stars):
    from app.service.payment import paymentModule

    def months(tariff_id, level, time_left):
        markup = stars.get_sub_message('en', tariff_id, level, 0, 0, time_left, 0, RATE)['markup']
        return [row[0]['callback_data'].get('m') for row in markup
                if row[0]['callback_data'].get('m')]

    def main_page(level, time_left):
        markup = paymentModule.get_sub_message(1, 'en', level, 0, 0, time_left, 0)['markup']
        return [row[0]['callback_data'] for row in markup
                if row[0]['callback_data'].get('m')]
    with patch.object(stars, 'SQLighter', _TariffsDB):
        _assert_eq(months(3, 3, 100), [3, 6, 12], "a Relay plan sees the prepaid months")
        _assert_eq(months(0, 0, 0), [3, 6, 12], "so does a user with no plan running")
        _assert_eq(months(1, 1, 0), [3, 6, 12], "and one whose Bronze has ended")
        _assert_eq(months(1, 1, 100), [], "a running Bronze does not")
    _assert_eq(main_page(0, 0), [{'tp': 'bs_stars_pay', 'm': 12}],
               "/subscription bills the longest bundle in one tap")
    _assert_eq(main_page(1, 100), [], "but not to a running Bronze")


def main():
    pricing()
    from app.controller.builders.test_open_recs import import_builder
    if import_builder("podcastModule") is None:
        return
    from app.service.payment import starsPaymentModule as stars
    bundle_invoice(stars)
    precheckout(stars)
    credit_once(stars)
    plan_turns_on(stars)
    winback_offer(stars)
    page_rows(stars)
    print("all Stars invoice checks passed")


if __name__ == "__main__":
    main()
