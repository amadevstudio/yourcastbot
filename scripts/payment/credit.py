# -*- coding: utf-8 -*-
"""A webhook's payment, credited once per invoice.

CryptoBot and Robokassa retry a webhook they did not see answered (a slow
Telegram connection, a restart), and nothing stops a second delivery while
the first one runs. The invoice is looked up and written in the transaction
that credits it (applyPaymentReplenishmentOnce, as for Stars): a retry finds
it and credits nothing.
"""
import datetime

import config
from db.sqliteAdapter import SQLighter


def credit_once(tg_id, service: str, invoice_id, cents: int, invoice_hash=None):
    """(user, result): result['already_processed'] for an invoice credited before,
    else result_mode, current_tariff and current_subscription for the message."""
    db = SQLighter(config.db_path)
    try:
        user = db.get_user_by_tg(tg_id)
        result = db.applyPaymentReplenishmentOnce(
            user, service, invoice_id, datetime.datetime.now(), int(cents), config.tariff_period,
            invoiceHash=invoice_hash, status="paid")
        return user, result
    finally:
        db.close()
