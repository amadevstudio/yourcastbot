# -*- coding: utf-8 -*-
"""Stars prices that credit more than they charge: prepaid months of Relay
and the win-back offer (one month at a discount, once per user).

The balance is credited at full price (price * months) and the hourly tick
renews month by month from it, as from any top-up. Only the charge is
discounted, so nothing else (renewal, D-3, plan change) knows about offers;
payment_history keeps what was charged beside it (`charged`), for revenue.

The win-back offer opens when it is first sent: the end of a trial (D-3 or
the plan-off notice, users.flags[OFFER_SENT_FLAG]) or the first win-back
message. Both are Relay's terms: never billed while Bronze or Silver runs
(the balance would renew that plan instead), checked again at the pre-checkout.
"""
from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL
from config import db_path, prepay_bundles, winback_offer_discount

# the payload's "o" for the win-back offer; its single use is users.flags[WINBACK_OFFER_FLAG]
WINBACK_OFFER = "wb"
WINBACK_OFFER_FLAG = "winback_offer_used"
# when the end of a trial offered it (app/service/payment/plan_end.py)
OFFER_SENT_FLAG = "winback_offer_sent"


def bundle_discount(months) -> int | None:
    """% off for `months` of the showcase plan: 0 for one month, None if not sold."""
    months = int(months)
    if months == 1:
        return 0
    return dict(prepay_bundles).get(months)


def longest_bundle():
    """(months, % off) of the longest prepaid bundle, the one the /subscription page shows."""
    return max(prepay_bundles)


def prepaid_months_sold(current_level, plan_running) -> bool:
    """Relay's prepaid months go to a Relay plan or to a user with no plan
    running (the payment turns Relay on). A running Bronze or Silver would
    renew itself from that balance: its owner changes plan first."""
    return int(current_level or 0) == SHOWCASE_TARIFF_LEVEL or not plan_running


def relay_terms_open(telegram_id, database=None) -> bool:
    """May this user pay for prepaid months or an offer now? The plan is read now,
    not when the invoice was sent: a user who switched to Bronze in between would
    get Relay's discounted month credited to Bronze."""
    from db.tariff_rows import running_plan_level
    level = running_plan_level(telegram_id, db_path if database is None else database)
    return prepaid_months_sold(level, level > 0)


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

    The win-back offer: the user was sent it (a callback can be forged, the
    flag and the schedule cannot) and has not spent it. Asked before Telegram
    takes the money, never after: a payment that went through is credited as sold.
    """
    if not offer:
        return True
    if offer != WINBACK_OFFER:
        return False
    from db import winback
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path if database is None else database)
    try:
        if db.get_user_flag(telegram_id, WINBACK_OFFER_FLAG):
            return False
        if db.get_user_flag(telegram_id, OFFER_SENT_FLAG):
            return True
    finally:
        db.close()
    return bool(winback.messages_sent(telegram_id, database=database))


def mark_offer_sent(telegram_id, now=None, database=None):
    """The end of a trial offers the first month: open it before the message goes
    (a message that failed opens an offer nobody saw, which costs nothing)."""
    import time
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path if database is None else database)
    try:
        db.set_user_flag(telegram_id, OFFER_SENT_FLAG, int(time.time() if now is None else now))
    finally:
        db.close()
