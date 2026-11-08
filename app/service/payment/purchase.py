# -*- coding: utf-8 -*-
"""What a purchase sells, whatever pays for it: a plan, its prepaid months, a discount, an offer.

The rules are offers.py's (which months are sold, at what discount, to whom); this is the
one place a pay method meets them. Each pay method is an adapter: it carries the terms in
its own way (a Stars invoice's payload, a CryptoBot invoice's payload), asks `refusal`
at its last moment before the credit and credits with `credit_args`:

- Stars asks at the pre-checkout, before Telegram takes the money, and can still refuse.
  What it took is credited as sold.
- CryptoBot has no pre-checkout: it asks when its webhook credits (`at_credit`). Terms that
  no longer hold then (the user switched to Bronze after a Relay bundle's invoice, an offer
  already spent) are a top-up of what was paid: the money stays, the discount does not.

A new pay method is one more adapter; nothing here knows about any of them.
"""
from dataclasses import dataclass

from app.service.payment.offers import (
    WINBACK_OFFER, WINBACK_OFFER_FLAG, charged_cents, offer_discount, offer_open, plan_terms_open)
import config
from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL


@dataclass(frozen=True)
class Terms:
    credit: int  # cents to the balance: the plan's price times the months when sold
    plan_id: int = 0  # the plan turned on when none runs; 0: a top-up
    months: int = 1
    discount: int = 0  # % off the charge
    offer: str = ""  # "" or offers.WINBACK_OFFER

    @property
    def charge(self) -> int:
        """What the payer pays: the credit with the discount, rounded up to a cent."""
        return charged_cents(self.credit, self.discount)

    @property
    def plain(self) -> bool:
        """No terms beyond the plan: one month at full price, sold to anyone."""
        return self.months == 1 and not self.discount and not self.offer


def sell(plan, months=1, offer="") -> Terms | None:
    """The terms of `months` of `plan` under `offer` at today's price, None if not sold."""
    try:
        months = int(months)
        discount = offer_discount(months, str(offer or ""))
    except (TypeError, ValueError):
        return None
    if plan is None or int(plan['price'] or 0) <= 0 or discount is None:
        return None
    if offer and int(plan['level']) != SHOWCASE_TARIFF_LEVEL:  # the offer is Relay's
        return None
    return Terms(int(plan['price']) * months, int(plan['id']), months, discount, str(offer or ""))


def plan_by_id(plan_id, database=None):
    """The tariffs row of `plan_id`, None for no such plan."""
    from db.sqliteAdapter import SQLighter
    try:
        plan_id = int(plan_id)
    except (TypeError, ValueError):
        return None
    db = SQLighter(config.db_path if database is None else database)
    try:
        return db.getTariffById(plan_id)
    finally:
        db.close()


def refusal(telegram_id, terms: Terms, database=None) -> str | None:
    """Why `terms` cannot be paid for by this user now, None when they can: 'terms' (not sold
    so: the config changed, or a forged button), 'offer' (not open to this user), 'plan'
    (another plan runs).
    The plan running is read now: a user who switched to Bronze after a Relay bundle's
    invoice would have Relay's discounted months renew Bronze."""
    if terms.discount != offer_discount(terms.months, terms.offer):
        return 'terms'
    if not offer_open(telegram_id, terms.offer, database=database):
        return 'offer'
    if (terms.months != 1 or terms.discount) and not plan_terms_open(telegram_id, terms.plan_id, database=database):
        return 'plan'
    return None


def at_credit(telegram_id, terms: Terms, database=None) -> Terms:
    """The terms a payment already taken is credited with, for a pay method that cannot
    refuse before it (CryptoBot). Terms that no longer hold are a top-up of what was paid.
    A plan is turned on only for at least its price now a month: an invoice for less was
    made from a forged button (a CryptoBot invoice for $0.01 named Relay, before 2026-11-08);
    one made before a price rise and paid after it is a top-up too (rare; the money stays)."""
    if not terms.plain and refusal(telegram_id, terms, database) is not None:
        return Terms(terms.charge)
    if terms.plan_id:
        plan = plan_by_id(terms.plan_id, database)
        if plan is None or int(plan['price'] or 0) <= 0 or terms.credit // terms.months < int(plan['price']):
            return Terms(terms.charge)
    return terms


def credit_args(terms: Terms) -> dict:
    """applyPaymentReplenishmentOnce's keywords for `terms` (the amount is `terms.credit`)."""
    return {
        'planId': terms.plan_id or None,
        # the price one period was sold for: a later price rise does not undo the invoice
        'planPrice': terms.credit // terms.months if terms.plan_id else None,
        # what the payer was charged, for revenue: a bundle or an offer credits more
        'chargedCents': terms.charge,
        'userFlag': WINBACK_OFFER_FLAG if terms.offer == WINBACK_OFFER else None,
    }


def to_payload(terms: Terms) -> dict:
    """The terms in an invoice's payload, only what differs from a plain top-up: `v` the plan,
    `m` months, `d` % off, `o` the offer (the Stars payload's letters)."""
    payload = {}
    if terms.plan_id:
        payload['v'] = terms.plan_id
    if terms.months != 1 or terms.discount:
        payload.update(m=terms.months, d=terms.discount)
    if terms.offer:
        payload['o'] = terms.offer
    return payload


def from_payload(payload: dict, credit) -> Terms:
    """The terms an invoice's payload carries (to_payload), `credit` the cents it credits."""
    return Terms(int(credit), int(payload.get('v') or 0), int(payload.get('m', 1)),
                 int(payload.get('d', 0)), str(payload.get('o', '') or ''))
