# -*- coding: utf-8 -*-
"""A webhook's payment, credited once per invoice.

CryptoBot sends a webhook "at least one time" and retries one that failed
(Crypto Pay API docs, Webhooks). A Robokassa ResultURL is signed with
OutSum:InvId:Password#2:Shp_*, the same for every delivery of that invoice:
whoever has the URL (a log line) can send it again. The invoice is looked up
and written in the transaction that credits it (applyPaymentReplenishmentOnce,
as for Stars): a second delivery finds it and credits nothing.
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


def notify(bot, coroutine, what: str) -> bool:
    """Run one Telegram notice of a payment already credited; a failure is logged, never raised.

    The payer or the inviter may have blocked the bot (Telethon raises
    UserIsBlockedError): what comes after the notice (the inviter's bonus, the
    payment event, the creator's note) must still run.
    """
    try:
        bot.loop.run_until_complete(coroutine)
        return True
    except Exception as e:
        line = "%s %s: payment notice to the %s failed\n" % (type(e).__name__, e, what)
        if config.server:
            with open(f"{config.BASE_DIR}/log/payment.log", 'a+') as log:
                log.write(line)
        else:
            print(line, flush=True)
        return False
