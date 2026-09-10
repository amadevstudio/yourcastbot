# -*- coding: utf-8 -*-
"""Relay conversion copy. No network.

Run from the repo root: python app/i18n/test_relay_copy.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.i18n.messages import get_message  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def main():
    langs = ("ru", "en", "pt", "es", "de", "he")
    keys = (
        "relay_sub_page_body",
        "relay_sub_page_footnote",
        "relayEnableButton",
        "relay_trial_ending",
        "youHaveNewEpisodes",
        "withoutTariffSubscriptionsLimited",
        "award_welcome",
        "tariff_cannot_be_prolonged_by_daemon",
        "payViaTelegramStars",
        "telegram_stars_invoice_title",
        "tariff_lvl3",
        "bot_sub_page_header",
        "bot_sub_trfs_page",
        "tariffs",
    )
    for key in keys:
        for lang in langs:
            text = get_message(key, lang)
            _assert(text and text != key, "%s/%s has copy" % (key, lang))
            if key != "relay_trial_ending":
                _assert("%s" not in text, "%s/%s leftover placeholder" % (key, lang))

    en_digest = get_message("youHaveNewEpisodes", "en")
    _assert("/subscribe" not in en_digest, "EN digest does not use missing /subscribe")
    _assert("Relay" in en_digest, "digest sells Relay")

    ru_limit = get_message("withoutTariffSubscriptionsLimited", "ru")
    _assert("/subscription" in ru_limit, "16th-sub paywall still points to /subscription")
    _assert("тариф" not in ru_limit.lower(), "paywall does not say тариф")

    _assert(get_message("tariff_lvl3", "en").endswith("Relay")
            or "Relay" in get_message("tariff_lvl3", "en"),
            "Gold is named Relay")

    ending = get_message("relay_trial_ending", "en") % 3
    _assert("3" in ending, "D-3 interpolates days")
    _assert("%s" not in ending, "D-3 consumed the placeholder")

    change = get_message("bot_sub_trfs_page", "en")
    _assert("Bronze" in change and "Silver" in change,
            "change-plan page still lists older SKUs")

    for lang in langs:
        for key in ("relayEnableButton", "payViaTelegramStars",
                    "nosubDigestMuteButton", "tariffs"):
            text = get_message(key, lang)
            _assert(len(text) <= 64, "%s/%s is %s chars" % (key, lang, len(text)))

    print("all relay copy checks passed")


if __name__ == "__main__":
    main()
