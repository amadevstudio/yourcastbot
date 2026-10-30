# -*- coding: utf-8 -*-
"""Days left on a plan, as the menu and the payment notices show it.

A plan's last day read "<1", a tag to Telegram: the whole menu was refused
(2026-10-27), on the day it should offer to renew.

Run from the repo root: python app/service/payment/test_days_left.py
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.payment.paymentSafeModule import days_left_text, get_tariff_info_message, money_text  # noqa: E402

# what Telegram's HTML parse mode takes; anything else after "<" is refused
_TAG = re.compile(r'</?([a-zA-Z-]+)[^>]*>')
_TELEGRAM_TAGS = {'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'a', 'code', 'pre',
                  'blockquote', 'span', 'tg-spoiler', 'tg-emoji'}


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _telegram_html(text):
    """Every "<" opens a tag Telegram knows."""
    rest = _TAG.sub(lambda m: '' if m.group(1) in _TELEGRAM_TAGS else m.group(0), text)
    return '<' not in rest


def main():
    _assert_eq(days_left_text(5), "&lt;1", "under a day")
    _assert_eq(days_left_text(23), "&lt;1", "23 hours")
    _assert_eq(days_left_text(24), "1", "a day")
    _assert_eq(days_left_text(1062), "44", "44 days")
    _assert_eq(days_left_text(0), "0", "nothing left")

    for language in ('en', 'ru'):
        for hours in (5, 1062):
            text = get_tariff_info_message('Relay', 100, 500, hours, -1, language)
            _assert_eq(_telegram_html(text), True, "tariff info, %s, %d h: Telegram HTML" % (language, hours))
    _assert_eq((money_text(0), money_text(500), money_text(450), money_text(499)), ("0", "5", "4.50", "4.99"),
               "dollars read 0, 5, 4.50, 4.99, not 0.0 and 5.0")
    text = get_tariff_info_message('Relay', 0, 500, 300, -1, 'en')
    _assert_eq("0💲</b> (not enough for renewal: 5💲)" in text, True, "the balance, a space, what renewal lacks")
    print("all days-left checks passed")


if __name__ == "__main__":
    main()
