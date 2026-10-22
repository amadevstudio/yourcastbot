# -*- coding: utf-8 -*-
"""Referral rewards: an unlimited plan (-1) stays unlimited, a payment awards
the inviter once whatever the pay method or retries, an invitee gets the
longer welcome plan, and a link naming nobody creates nobody.

Run from the repo root: python app/service/payment/test_referral_award.py
"""
import os
import sys
import tempfile
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.payment import paymentSafeModule  # noqa: E402
from app.service.payment.paymentSafeModule import (  # noqa: E402
    giveAward, notify_count_after_referral)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


class FakeDB:
    subscription = {}
    saved = []

    def __init__(self, _path):
        pass

    def get_user_by_tg(self, _tg_id):
        return {'id': 1, 'lang': 'en'}

    def getUserSubscriptionByTg(self, _tg_id):
        return dict(FakeDB.subscription)

    def getTariffById(self, tariff_id):
        return {'id': tariff_id, 'level': 3, 'price': 500,
                'notify_count': -1, 'compression': 0}

    def subscribeUserToTariffByTg(self, tg_id, tariff_id, balance, time_left, notify_count):
        FakeDB.saved.append((tariff_id, balance, time_left, notify_count))

    def close(self):
        pass


def _award_with(notify_count):
    FakeDB.subscription = {
        'tariff_id': 3, 'balance': 100, 'time_left': 50, 'notify_count': notify_count}
    FakeDB.saved = []
    original = paymentSafeModule.SQLighter
    paymentSafeModule.SQLighter = FakeDB
    try:
        giveAward(1001, 1002, 'reged')
    finally:
        paymentSafeModule.SQLighter = original
    return FakeDB.saved[0]


def _temp_db():
    from db.sqliteAdapter import SQLighter
    import sqlite3
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE, "
                 "lang TEXT, ref_id INTEGER, bitrate INTEGER)")
    conn.commit()
    conn.close()
    db = SQLighter(path)  # adds the columns the bot expects on users
    db.connection.executescript("""
        CREATE TABLE IF NOT EXISTS tariffs (id INTEGER PRIMARY KEY, level INTEGER,
            price INTEGER, notify_count INTEGER, compression INTEGER, channel_control INTEGER);
        CREATE TABLE IF NOT EXISTS user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER,
            tariff_id INTEGER, balance INTEGER, notify_count INTEGER, time_left INTEGER);
        CREATE TABLE IF NOT EXISTS user_channel_cs (id INTEGER PRIMARY KEY,
            user_telegram_id INTEGER, channel_id INTEGER, notify INTEGER);
        CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO tariffs VALUES (1, 1, 50, 30, 0, 0), (3, 3, 500, -1, 0, 1);
    """)
    db.connection.commit()
    db.close()
    return path


def _plan(path, telegram_id):
    from db.sqliteAdapter import SQLighter
    db = SQLighter(path)
    try:
        row = db.getUserSubscriptionByTg(telegram_id)
        return None if row is None else (row['tariff_id'], row['time_left'])
    finally:
        db.close()


def _payment_awards_once():
    from db.sqliteAdapter import SQLighter
    path = _temp_db()
    try:
        db = SQLighter(path)
        db.register_new_user(1001, 'en')
        db.register_new_user(1002, 'en', 1001)
        db.register_new_user(1003, 'en', 1003)
        db.subscribeUserToTariffByTg(1001, 3, 0, 10, -1)
        db.close()
        with patch.object(paymentSafeModule, 'db_path', path):
            first = paymentSafeModule.award_referrer_for_payment(1002)
            second = paymentSafeModule.award_referrer_for_payment(1002)
            itself = paymentSafeModule.award_referrer_for_payment(1003)
        _assert_eq(first[0], 1001, "an invitee's first payment awards the inviter")
        _assert_eq(_plan(path, 1001), (3, 10 + paymentSafeModule.tariff_ref_sub_period),
                   "the inviter's plan grows by the payment bonus")
        _assert_eq(second, (None, None), "a second payment or a webhook retry awards nothing")
        _assert_eq(_plan(path, 1001), (3, 10 + paymentSafeModule.tariff_ref_sub_period),
                   "and the plan is not extended twice")
        _assert_eq(itself, (None, None), "nobody is their own referral")
    finally:
        os.remove(path)


def _invitee_gets_longer_welcome():
    from db.sqliteAdapter import SQLighter
    path = _temp_db()
    try:
        db = SQLighter(path)
        db.register_new_user(2001, 'en')
        db.register_new_user(2002, 'ru')
        db.close()
        with patch.object(paymentSafeModule, 'db_path', path):
            plain = giveAward(2001, 0, 'new')
            invited = giveAward(2002, 0, 'new', invited=True)
        welcome = paymentSafeModule.tariff_new_user_period
        _assert_eq(_plan(path, 2001), (3, welcome), "a plain sign-up gets the usual welcome plan")
        _assert_eq(_plan(path, 2002), (3, welcome + paymentSafeModule.tariff_ref_invitee_period),
                   "a friend's link adds the invitee bonus")
        _assert("+7" in invited and "+7" not in plain, "the invitee is told why the plan is longer")
    finally:
        os.remove(path)


def _newcomer_who_subscribed_first():
    """A first command other than /start (/search from the bot's menu) creates the
    user with no plan; subscribing before /start must not make them "returning"."""
    from db.sqliteAdapter import SQLighter
    path = _temp_db()
    try:
        db = SQLighter(path)
        db.get_user_by_tg(4001)  # /search: the dispatcher creates the row
        db.register_new_user(4002, 'en')
        db.connection.execute("UPDATE users SET created_at = NULL WHERE telegramId = 4002")  # before the column
        db.register_new_user(4003, 'en')
        db.connection.execute("UPDATE users SET created_at = datetime('now', '-3 days') WHERE telegramId = 4003")
        db.connection.executemany(
            "INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) VALUES (?, ?, 1)",
            [(4001, 1), (4001, 2), (4002, 1), (4003, 1)])
        db.connection.commit()
        db.close()
        with patch.object(paymentSafeModule, 'db_path', path):
            for telegram_id in (4001, 4002, 4003):
                giveAward(telegram_id, 0, 'new')
        _assert_eq(_plan(path, 4001), (3, paymentSafeModule.tariff_new_user_period),
                   "a newcomer who subscribed before /start gets the welcome plan")
        _assert_eq(_plan(path, 4002), (3, paymentSafeModule.tariff_secret_start_cmd_period),
                   "an old user with podcasts and no plan gets the short one, as before")
        _assert_eq(_plan(path, 4003), (3, paymentSafeModule.tariff_secret_start_cmd_period),
                   "so does a user who joined days ago")
    finally:
        os.remove(path)


def _link_naming_nobody_creates_nobody():
    from app.controller.builders.test_open_recs import import_builder
    welcomeModule = import_builder("welcomeModule")
    if welcomeModule is None:
        return
    from db.sqliteAdapter import SQLighter
    path = _temp_db()
    try:
        data = {'chat_id': 3001, 'language_code': 'en'}
        with patch.object(welcomeModule.config, 'db_path', path), \
                patch.object(paymentSafeModule, 'db_path', path), \
                patch.object(welcomeModule, 'render_messages'), \
                patch.object(welcomeModule, 'add_sub', return_value=(None, None)):
            welcomeModule.referral_processing(data, 999999999)
        db = SQLighter(path)
        try:
            _assert_eq(db.user_exists_tg(999999999), False, "an unknown inviter is not created")
            _assert_eq(db.get_user_by_tg(3001)['ref_id'], None, "nor stored as the referrer")
        finally:
            db.close()
        _assert_eq(_plan(path, 3001), (3, paymentSafeModule.tariff_new_user_period),
                   "and the sign-up gets no invitee bonus")
    finally:
        os.remove(path)


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def main():
    _assert_eq(notify_count_after_referral(-1, 20), -1, "unlimited stays unlimited")
    _assert_eq(notify_count_after_referral(0, 20), 20, "spent plan gets the bonus")
    _assert_eq(notify_count_after_referral(5, 20), 25, "counted plan gets the bonus")
    _assert_eq(_award_with(-1)[3], -1, "giveAward keeps an unlimited plan unlimited")
    _assert_eq(_award_with(5)[3], 25, "giveAward adds the bonus to a counted plan")
    _payment_awards_once()
    _invitee_gets_longer_welcome()
    _newcomer_who_subscribed_first()
    _link_naming_nobody_creates_nobody()
    print("all referral award checks passed")


if __name__ == "__main__":
    main()
