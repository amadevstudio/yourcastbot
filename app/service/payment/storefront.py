# -*- coding: utf-8 -*-
"""User-facing storefront: Relay (Gold / level 3) is the default sell.

Does not change tariff rows or payment apply. Live SKUs stay visible.
Relay is copy and button order — not a filter that hides Bronze/Silver
or removes change-plan.

`bs_trfs` stays on /subscription. Stars lists every SKU, Relay first.
"""

import re

from app.i18n.messages import get_message

SHOWCASE_TARIFF_LEVEL = 3
CHANGE_PLAN_CALLBACK = "bs_trfs"
# no 'v': send_invoice bills the showcase plan, so a button needs no tariff id
RELAY_INVOICE_CALLBACK = {"tp": "bs_stars_pay"}

_MEDAL = re.compile(r"^[^\w]+")


def plan_name(level, language_code) -> str:
    """The localized plan name without its medal: Bronze, Silver, Relay. '' if unknown."""
    key = "tariff_lvl%d" % int(level or 0)
    name = get_message(key, language_code)
    return "" if name == key else _MEDAL.sub("", name).strip()


def plan_ending_text(level, days, language_code) -> str:
    """D-3: the plan that ends is the user's own, not always Relay.

    Relay keeps its tuned text as it is. Other plans get a neutral one that
    names the plan as an apposition: plan names are localized words with a
    gender, they cannot replace "Relay" inside a sentence.
    """
    name = plan_name(level, language_code)
    if int(level or 0) == SHOWCASE_TARIFF_LEVEL or not name:
        return get_message("relay_trial_ending", language_code) % days
    return get_message("plan_ending_soon", language_code).format(plan=name, days=days)


def plan_off_text(level, language_code) -> str:
    """The daemon could not renew the plan: say which plan stopped."""
    name = plan_name(level, language_code)
    if int(level or 0) == SHOWCASE_TARIFF_LEVEL or not name:
        return get_message("tariff_cannot_be_prolonged_by_daemon", language_code)
    return get_message("plan_off_by_daemon", language_code).format(plan=name)


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


def showcase_tariff(tariffs):
    """The Relay row of the tariff table, or None."""
    return next((_tariff_dict(t) for t in tariffs or []
                 if int(_tariff_dict(t).get("level") or 0) == SHOWCASE_TARIFF_LEVEL), None)


def relay_nudge_markup(language_code, extra_row=None, invoice=False, source=None):
    """Stars first, then change-plan. Do not trap the user on one SKU.

    invoice=True is for a limit the user has just hit: the Relay button opens
    its Stars invoice at once (one tap to pay) instead of the page of plans.
    source: the message's key in analytics_events.SOURCES, carried by both
    buttons (`s`) so their taps say where they were (D-3, plan-off, win-back).
    """
    tag = {"s": source} if source else {}
    rows = [[{
        "text": get_message("relayEnableButton", language_code),
        "callback_data": dict(RELAY_INVOICE_CALLBACK if invoice else {"tp": "bs_stars"}, **tag),
    }], [{
        "text": get_message("tariffs", language_code),
        "callback_data": dict({"tp": CHANGE_PLAN_CALLBACK}, **tag),
    }]]
    if extra_row:
        rows.append(extra_row)
    return rows


RECURRING_CALLBACK = "bs_recur"
ONCE_CALLBACK = "bs_once"


def subscription_pay_rows(language_code):
    """Main /subscription buttons: how to pay (a subscription, one payment), then change plan.

    Change-plan is required. Every pay method stays one level down: Stars
    subscriptions and Patreon under the subscription, Stars, CryptoBot (and
    Robokassa for the creator) under the one-time payment.
    """
    return [
        [{'text': get_message("payRecurringButton", language_code),
          'callback_data': {'tp': RECURRING_CALLBACK}}],
        [{'text': get_message("payOnceButton", language_code),
          'callback_data': {'tp': ONCE_CALLBACK}}],
        [{'text': get_message("tariffs", language_code),
          'callback_data': {'tp': CHANGE_PLAN_CALLBACK}}],
    ]


def once_pay_rows(language_code, include_robokassa=False):
    """The one-time payment page: Stars first. Do not drop pay methods or hide live SKUs."""
    rows = [
        [{'text': get_message("payViaTelegramStars", language_code),
          'callback_data': {'tp': 'bs_stars'}}],
        [{'text': get_message("payViaCryptoBot", language_code),
          'callback_data': {'tp': 'bs_cryptobot'}}],
    ]
    if include_robokassa:
        rows.append([{
            'text': get_message("payViaRobokassa", language_code),
            'callback_data': {'tp': 'bs_robokassa'},
        }])
    return rows
