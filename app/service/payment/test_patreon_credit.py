# -*- coding: utf-8 -*-
"""Patreon: one membership pays one account. An email another account has is
not saved; accounts that already share one (saved before) are credited once a
month between them; the creator's debug address credits the creator's account
only, never whoever types it. Every credit is a payment_history row of its
month (db/patreon.py), written with the balance: revenue and "paid" see it.

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
    db.connection.execute(
        "CREATE TABLE IF NOT EXISTS payment_history (user_id integer NOT NULL, service_type text NOT NULL, "
        "invoice_id text, invoice_hash text, status text, amount integer, datetime text, "
        "PRIMARY KEY (user_id, service_type, invoice_id))")
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


def _history(path):
    from db.sqliteAdapter import SQLighter
    db = SQLighter(path)
    try:
        return sorted((row['telegramId'], row['invoice_id'], row['status'], row['amount'])
                      for row in db.connection.execute(
                          "SELECT u.telegramId, p.* FROM payment_history p JOIN users u ON u.id = p.user_id "
                          "WHERE p.service_type = 'patreon'").fetchall())
    finally:
        db.close()


def test_credit_month():
    from db import patreon as ledger
    from db.tariff_rows import paid_for_days, ever_paid
    path, db = _db_with_users(2001, 2002)
    uid = {tg: db.connection.execute("SELECT id FROM users WHERE telegramId = ?", (tg,)).fetchone()[0]
           for tg in (2001, 2002)}
    for tg in (2001, 2002):
        db.connection.execute(
            "INSERT INTO payment_service_user_data (user_id, service_type, email, active) VALUES (?, 'patreon', ?, 1)",
            (uid[tg], "%d@example.com" % tg))
    db.connection.execute("DELETE FROM user_tariff_cs WHERE uid = ?", (uid[2002],))
    db.connection.commit()
    db.close()
    try:
        _assert(ledger.credit_month(uid[2001], "2026-10", 500, 500, "2026-10-13", database=path) is True,
                "a month is credited")
        _assert(ledger.credit_month(uid[2001], "2026-10", 500, 500, "2026-10-14", database=path) is False,
                "and not twice")
        _assert(_balances(path, (2001,))[2001] == 500, "the balance got it once")
        _assert(ledger.credit_month(uid[2002], "2026-10", 500, 0, "2026-10-13", database=path) is True
                and _balances(path, (2002,))[2002] == 500, "a user with no tariff row gets one with the balance")
        _assert(_history(path) == [(2001, "2026-10", "paid", 500), (2002, "2026-10", "credited", 0)],
                "each credit is a payment row of its month; a pledge of nothing is not 'paid'")
        _assert(ever_paid(2001, path) and paid_for_days(2001, path), "a patron has paid")
        _assert(not ever_paid(2002, path) and paid_for_days(2002, path),
                "a credited special address is not revenue, but its days are paid for")
        from db.sqliteAdapter import SQLighter
        db = SQLighter(path)
        try:
            day = db.connection.execute("SELECT last_replenishment FROM payment_service_user_data "
                                        "WHERE user_id = ?", (uid[2001],)).fetchone()[0]
        finally:
            db.close()
        _assert(day == "2026-10-13", "last_replenishment is the credited day, not the refused one")
    finally:
        os.remove(path)


def _patreon_module():
    from app.controller.builders.test_open_recs import import_builder
    if import_builder("welcomeModule") is None:  # the bot's requirements
        return None
    from app.service.payment import patreonPaymentModule
    return patreonPaymentModule


def _balances(path, ids=(2001, 2002, 2003, CREATOR)):
    from db.sqliteAdapter import SQLighter
    db = SQLighter(path)
    try:
        return {tg: db.getUserSubscriptionByTg(tg)['balance'] for tg in ids}
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
            rows = _history(path)
    finally:
        os.remove(path)
    _assert(first[2001] + first[2002] == 500, "one membership shared by two accounts is credited once")
    _assert(second == first, "and not again in the same month")
    _assert(first[2003] == 0, "the creator's debug address credits nobody else")
    _assert(first[CREATOR] == 100, "the creator's own account still gets it")
    _assert(len(rows) == 2 and {row[0] for row in rows} & {2001, 2002} and CREATOR in {row[0] for row in rows},
            "the credits are payment rows: the shared membership once, the creator's debug one")


def main():
    test_email_taken_once()
    test_credit_month()
    patreon = _patreon_module()
    if patreon is not None:
        test_credit_once_per_email(patreon)
    print("all patreon credit checks passed")


if __name__ == "__main__":
    main()
