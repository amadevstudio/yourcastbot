# -*- coding: utf-8 -*-
"""User-facing storefront: Relay (Gold / level 3) is the default sell.

Does not change tariff rows or payment apply. Bronze/Silver stay in SQLite.
Stars invoices hide them; the change-plan page lists every SKU.

Relay-only is a Stars/SKU filter, not permission to drop plan management.
`bs_trfs` stays on /subscription. A previous shop cleanup removed it and
encoded that as a test; do not do that again.
"""

from app.i18n.messages import get_message

SHOWCASE_TARIFF_LEVEL = 3
CHANGE_PLAN_CALLBACK = "bs_trfs"


def tariffs_for_storefront(tariffs, current_tariff_id=0):
    """Gold/Relay plus the caller's current plan if it is a hidden SKU."""
    rows = list(tariffs or [])
    current_id = int(current_tariff_id or 0)
    visible = []
    seen = set()
    for tariff in rows:
        tariff_id = int(tariff["id"])
        level = int(tariff.get("level") or 0)
        if level != SHOWCASE_TARIFF_LEVEL and tariff_id != current_id:
            continue
        if tariff_id <= 0 or tariff_id in seen:
            continue
        visible.append(tariff)
        seen.add(tariff_id)
    if visible:
        return visible
    priced = [row for row in rows if int(row.get("price") or 0) > 0]
    return priced or rows


def tariffs_for_change_plan(tariffs):
    """Every live SKU on the change-plan page, including Bronze/Silver."""
    visible = []
    seen = set()
    for tariff in list(tariffs or []):
        tariff_id = int(tariff["id"])
        if tariff_id <= 0 or tariff_id in seen:
            continue
        visible.append(tariff)
        seen.add(tariff_id)
    return visible


def subscription_pay_rows(language_code, include_robokassa=False):
    """Main /subscription pay buttons. Stars first, then change plan.

    Change-plan is required. Hide Bronze/Silver only in
    tariffs_for_storefront (Stars invoices), never by dropping this row.
    """
    rows = [
        [{'text': get_message("payViaTelegramStars", language_code),
          'callback_data': {'tp': 'bs_stars'}}],
        [{'text': get_message("tariffs", language_code),
          'callback_data': {'tp': CHANGE_PLAN_CALLBACK}}],
        [{'text': get_message("payViaCryptoBot", language_code),
          'callback_data': {'tp': 'bs_cryptobot'}}],
        [{'text': get_message("payViaPatreon", language_code),
          'callback_data': {'tp': 'bs_patr'}}],
    ]
    if include_robokassa:
        rows.append([{
            'text': get_message("payViaRobokassa", language_code),
            'callback_data': {'tp': 'bs_robokassa'},
        }])
    return rows
