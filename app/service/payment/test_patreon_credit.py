# -*- coding: utf-8 -*-
"""Patreon: one membership pays one account. An email another account has is
not saved; accounts that already share one (saved before) are credited once a
month between them; the creator's debug address credits the creator's account
only, never whoever types it.

Run from the repo root: python app/service/payment/test_patreon_credit.py
"""
import os
import sys
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.payment.test_referral_award import _temp_db  # noqa: E402

CREATOR = 4000


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _db_with_users(*telegram_ids):
    from db.sqliteAdapter import SQLighter
    path = _temp_db()
    db = SQLighter(path)
    db.connection.execute(
        "CREATE TABLE payment_service_user_data (user_id integer NOT NULL, service_type text NOT NULL, "
        "email text NOT NULL, last_replenishment text, active integer NOT NULL, "
        "PRIMARY KEY (user_id, service_type))")
    for tg in telegram_ids:
        db.connection.execute("INSERT INTO users (telegramId, lang) VALUES (?, 'en')", (tg,))
        uid = db.connection.execute("SELECT id FROM users WHERE telegramId = ?", (tg,)).fetchone()[0]
        db.connection.execute(
            "INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) VALUES (?, 1, 0, 30, 100)",
            (uid,))
    db.connection.commit()
    return path, db


def test_email_taken_once():
    path, db = _db_with_users(2001, 2002)
    try:
        _assert(db.savePaymentServiceEmail(2001, "Fan@Example.com", "patreon") is True, "the first account saves it")
        _assert(db.savePaymentServiceEmail(2002, " fan@example.COM ", "patreon") is False
                and db.getPaymentServiceEmail(2002, "patreon") is None,
                "another account cannot take it (case and spaces do not matter)")
        _assert(db.savePaymentServiceEmail(2001, "fan@example.com", "patreon") is True,
                "the owner may save it again")
        _assert(db.savePaymentServiceEmail(2002, "other@example.com", "patreon") is True,
                "another address is free")
        rows = db.getPaymentDataByService("patreon")
        _assert(sorted(row['telegramId'] for row in rows) == [2001, 2002], "rows carry their telegramId")
        _assert(db.getPaymentDataByService("other") == [], "and only the asked service")
    finally:
        db.close()
        os.remove(path)


def _patreon_module():
    from app.controller.builders.test_open_recs import import_builder
    if import_builder("welcomeModule") is None:  # the bot's requirements
        return None
    from app.service.payment import patreonPaymentModule
    return patreonPaymentModule


def _balances(path):
    from db.sqliteAdapter import SQLighter
    db = SQLighter(path)
    try:
        return {tg: db.getUserSubscriptionByTg(tg)['balance'] for tg in (2001, 2002, 2003, CREATOR)}
    finally:
        db.close()


def test_credit_once_per_email(patreon):
    path, db = _db_with_users(2001, 2002, 2003, CREATOR)
    # legacy rows: two accounts saved one membership before it could be taken once
    for tg, email in ((2001, "fan@example.com"), (2002, "fan@example.com"),
                      (2003, "owner@example.com"), (CREATOR, "owner@example.com")):
        uid = db.connection.execute("SELECT id FROM users WHERE telegramId = ?", (tg,)).fetchone()[0]
        db.connection.execute(
            "INSERT INTO payment_service_user_data (user_id, service_type, email, active) VALUES (?, 'patreon', ?, 1)",
            (uid, email))
    db.connection.commit()
    db.close()
    try:
        with patch.object(patreon, 'db_path', path), \
                patch.object(patreon, 'creatorId', CREATOR), \
                patch.object(patreon, 'creator_email', 'owner@example.com'), \
                patch.object(patreon, 'special_paid_emails', []), \
                patch.object(patreon, 'load_patrons', return_value={'fan@example.com': {'cents': 500}}), \
                patch.object(patreon, 'outer_sender'):
            patreon.check_patreon_accounts()
            first = _balances(path)
            patreon.check_patreon_accounts()
            second = _balances(path)
    finally:
        os.remove(path)
    _assert(first[2001] + first[2002] == 500, "one membership shared by two accounts is credited once")
    _assert(second == first, "and not again in the same month")
    _assert(first[2003] == 0, "the creator's debug address credits nobody else")
    _assert(first[CREATOR] == 100, "the creator's own account still gets it")


def main():
    test_email_taken_once()
    patreon = _patreon_module()
    if patreon is not None:
        test_credit_once_per_email(patreon)
    print("all patreon credit checks passed")


if __name__ == "__main__":
    main()
