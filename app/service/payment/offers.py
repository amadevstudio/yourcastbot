# -*- coding: utf-8 -*-
"""Stars prices that credit more than they charge: prepaid months of Relay
and the win-back offer (one month at a discount, once per user).

The balance is credited at full price (price * months) and the hourly tick
renews month by month from it, as from any top-up. Only the charge is
discounted, so nothing else (renewal, D-3, plan change) knows about offers.
"""
from config import db_path, prepay_bundles, winback_offer_discount

# the payload's "o" for the win-back offer; its single use is users.flags[WINBACK_OFFER_FLAG]
WINBACK_OFFER = "wb"
WINBACK_OFFER_FLAG = "winback_offer_used"


def bundle_discount(months) -> int | None:
    """% off for `months` of the showcase plan: 0 for one month, None if not sold."""
    months = int(months)
    if months == 1:
        return 0
    return dict(prepay_bundles).get(months)


def offer_discount(months, offer="") -> int | None:
    """% off for `months` bought under `offer` ("" or WINBACK_OFFER), None if not sold."""
    if offer == WINBACK_OFFER:
        return winback_offer_discount if int(months) == 1 else None
    if offer:
        return None
    return bundle_discount(months)


def charged_cents(credit_cents, discount) -> int:
    """`credit_cents` with `discount` % off, rounded up to a cent."""
    return -(-int(credit_cents) * (100 - int(discount)) // 100)


def offer_open(telegram_id, offer, database=None) -> bool:
    """May this user buy under `offer` now? A plain purchase always may.

    The win-back offer: the user was sent it (a callback can be forged, a
    schedule cannot) and has not spent it. Asked before Telegram takes the
    money, never after: a payment that went through is credited as sold.
    """
    if not offer:
        return True
    if offer != WINBACK_OFFER:
        return False
    from db import winback
    from db.sqliteAdapter import SQLighter
    if not winback.messages_sent(telegram_id, database=database):
        return False
    db = SQLighter(db_path if database is None else database)
    try:
        return not db.get_user_flag(telegram_id, WINBACK_OFFER_FLAG)
    finally:
        db.close()
