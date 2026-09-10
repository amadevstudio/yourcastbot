# -*- coding: utf-8 -*-
"""Relay storefront: Stars first, then change plan.

Run from the repo root: python app/service/payment/test_storefront.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.i18n.messages import get_message  # noqa: E402
from app.service.payment.storefront import (  # noqa: E402
    subscription_pay_rows, tariffs_for_change_plan, tariffs_for_storefront)


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    rows = [
        {"id": 1, "level": 1, "price": 50},
        {"id": 2, "level": 2, "price": 200},
        {"id": 3, "level": 3, "price": 500},
    ]
    _assert_eq(
        [t["id"] for t in tariffs_for_storefront(rows)],
        [3],
        "Stars invoice is Relay only")
    _assert_eq(
        [t["id"] for t in tariffs_for_storefront(rows, 2)],
        [2, 3],
        "legacy Silver still sees their plan on Stars")
    _assert_eq(
        [t["id"] for t in tariffs_for_storefront(rows, 0)],
        [3],
        "no current tariff still hides bronze/silver on Stars")
    _assert_eq(
        [t["id"] for t in tariffs_for_storefront(
            [{"id": 1, "level": 1, "price": 50}])],
        [1],
        "fallback if Gold is missing")
    _assert_eq(
        [t["id"] for t in tariffs_for_change_plan(rows)],
        [1, 2, 3],
        "change-plan page lists Bronze, Silver, Relay")

    page_types = [
        row[0]["callback_data"]["tp"]
        for row in subscription_pay_rows("en")
    ]
    _assert_eq(page_types[0], "bs_stars", "Stars is the first button")
    _assert_eq(page_types[1], "bs_trfs", "change plan is second")
    _assert_eq(page_types[2], "bs_cryptobot", "Crypto is third")
    _assert_eq(page_types[3], "bs_patr", "Patreon is fourth")
    _assert_eq(
        [row[0]["callback_data"]["tp"] for row in subscription_pay_rows("en", True)][-1],
        "bs_robokassa",
        "creator still gets Robokassa last")

    body = get_message("relay_sub_page_body", "en")
    _assert("file" in body.lower() or "deliver" in body.lower(),
            "main copy sells delivery")
    footnote = get_message("relay_sub_page_footnote", "en")
    _assert("donation" in footnote.lower(), "donation footnote stays")
    change = get_message("bot_sub_trfs_page", "en")
    _assert("Bronze" in change and "Silver" in change,
            "change-plan copy mentions older SKUs")
    _assert("Relay" in change, "change-plan copy still recommends Relay")

    ru_stars = get_message("payViaTelegramStars", "ru")
    _assert(len(ru_stars) <= 64, "Stars button fits Telegram")
    ru_plan = get_message("tariffs", "ru")
    _assert(len(ru_plan) <= 64, "change-plan button fits Telegram")
    _assert("план" in ru_plan.lower() or "тариф" in ru_plan.lower(),
            "RU change-plan button is readable")
    print("all storefront checks passed")


if __name__ == "__main__":
    main()
