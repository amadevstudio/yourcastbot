# -*- coding: utf-8 -*-
"""payment_history.charged: what the payer was charged, beside `amount`, the
balance the payment credited.

A Stars bundle of prepaid months or an offer credits the full price and charges
less (app/service/payment/offers.py): revenue is the charge, the balance is
what the tick renews from. NULL is "the same as amount": rows from before the
column, CryptoBot, Robokassa, Patreon. Payments are rare, so the column is made
when a payment is written (deploy does not run db/migrations), and readers ask
whether it is there.
Lock: python app/service/payment/test_stars_invoice.py, python app/admin_web/test_economics.py.
"""
import sqlite3


def has_charged(connection) -> bool:
    return any(row[1] == 'charged' for row in connection.execute("PRAGMA table_info(payment_history)"))


def ensure_charged_column(connection) -> None:
    """Outside a transaction: the ALTER commits."""
    if has_charged(connection):
        return
    try:
        connection.execute("ALTER TABLE payment_history ADD COLUMN charged INTEGER")
        connection.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise


def revenue_sql(connection, alias='p') -> str:
    """The cents a payment row brought in, for a query over payment_history `alias`."""
    if has_charged(connection):
        return "COALESCE(%s.charged, %s.amount)" % (alias, alias)
    return "%s.amount" % alias
