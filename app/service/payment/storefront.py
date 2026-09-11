# -*- coding: utf-8 -*-
"""User-facing storefront: Relay (Gold / level 3) is the default sell.

Does not change tariff rows or payment apply. Live SKUs stay visible.
Relay is copy and button order — not a filter that hides Bronze/Silver
or removes change-plan.

`bs_trfs` stays on /subscription. Stars lists every SKU, Relay first.
"""

from app.i18n.messages import get_message

SHOWCASE_TARIFF_LEVEL = 3
CHANGE_PLAN_CALLBACK = "bs_trfs"


def _tariff_dict(tariff):
    """sqlite3.Row has no .get(); dicts from tests do."""
    if isinstance(tariff, dict):
        return tariff
    try:
        return {key: tariff[key] for key in tariff.keys()}
    except Exception:
        return dict(tariff)


def tariffs_for_change_plan(tariffs):
    """Every live SKU, including Bronze/Silver."""
    visible = []
    seen = set()
    for tariff in list(tariffs or []):
        row = _tariff_dict(tariff)
        tariff_id = int(row["id"])
        if tariff_id <= 0 or tariff_id in seen:
            continue
        visible.append(row)
        seen.add(tariff_id)
    return visible


def tariffs_for_storefront(tariffs, current_tariff_id=0):
    """Every live SKU. Showcase (Relay) first, then the current plan."""
    rows = tariffs_for_change_plan(tariffs)
    if not rows:
        return []
    current_id = int(current_tariff_id or 0)
    showcase = []
    current = []
    rest = []
    for tariff in rows:
        tariff_id = int(tariff["id"])
        level = int(tariff.get("level") or 0)
        if level == SHOWCASE_TARIFF_LEVEL:
            showcase.append(tariff)
        elif tariff_id == current_id:
            current.append(tariff)
        else:
            rest.append(tariff)
    ordered = showcase + current + rest
    if ordered:
        return ordered
    priced = [row for row in rows if int(row.get("price") or 0) > 0]
    return priced or rows


def subscription_pay_rows(language_code, include_robokassa=False):
    """Main /subscription pay buttons. Stars first, then change plan.

    Change-plan is required. Do not drop pay methods or hide live SKUs.
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
