# -*- coding: utf-8 -*-
"""Stars prices that credit more than they charge: prepaid months of Relay.

The balance is credited at full price (price * months) and the hourly tick
renews month by month from it, as from any top-up. Only the charge is
discounted, so nothing else (renewal, D-3, plan change) knows about offers.
"""
from config import prepay_bundles


def bundle_discount(months) -> int | None:
    """% off for `months` of the showcase plan: 0 for one month, None if not sold."""
    months = int(months)
    if months == 1:
        return 0
    return dict(prepay_bundles).get(months)


def charged_cents(credit_cents, discount) -> int:
    """`credit_cents` with `discount` % off, rounded up to a cent."""
    return -(-int(credit_cents) * (100 - int(discount)) // 100)
