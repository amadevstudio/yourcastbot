# -*- coding: utf-8 -*-
"""A Patreon month: credited once, and written down as a payment.

The monthly check (patreonPaymentModule.check_patreon_accounts) used to add
the pledge to the balance, move last_replenishment and write nothing else:
Patreon was not in payment_history, so revenue (the economics page), payers
(the Product page) and "ever paid" (the AI hours of a paid plan, plan_off's
paid_before) never saw a patron. Now the credit, its payment_history row and
last_replenishment are one transaction. The row's invoice id is the month
("2026-10"), so a month already written credits nothing, on top of the
module's date rule.
"""
from __future__ import annotations

import datetime

from db.connection import connect_sqlite

SERVICE = 'patreon'


def credit_month(user_id, month: str, credit_cents: int, paid_cents: int, day: str,
                 database=None) -> bool:
    """Add credit_cents to the user's balance for that month, once; True if it was credited.

    paid_cents is what the patron pays (the payment's amount); credit_cents
    can be more (special_paid_emails get the top plan's price). A pledge of
    nothing is written as 'credited', not 'paid': it is not money."""
    if database is None:
        from config import db_path as database
    connection = connect_sqlite(database)
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        written = connection.execute(
            "INSERT OR IGNORE INTO payment_history "
            "(user_id, service_type, invoice_id, invoice_hash, status, amount, datetime) "
            "VALUES (?, ?, ?, NULL, ?, ?, ?)",
            (int(user_id), SERVICE, month, 'paid' if paid_cents > 0 else 'credited',
             int(paid_cents), str(datetime.datetime.now()))).rowcount
        if not written:
            connection.execute("ROLLBACK")
            return False
        if connection.execute("SELECT 1 FROM user_tariff_cs WHERE uid = ?", (int(user_id),)).fetchone():
            connection.execute("UPDATE user_tariff_cs SET balance = balance + ? WHERE uid = ?",
                               (int(credit_cents), int(user_id)))
        else:
            connection.execute(
                "INSERT INTO user_tariff_cs (uid, tariff_id, balance, time_left, notify_count) "
                "VALUES (?, 0, ?, 0, 0)", (int(user_id), int(credit_cents)))
        connection.execute(
            "UPDATE payment_service_user_data SET last_replenishment = ? "
            "WHERE user_id = ? AND service_type = ?", (day, int(user_id), SERVICE))
        connection.execute("COMMIT")
        return True
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
