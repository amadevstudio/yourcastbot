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
from app.service.payment.storefront import (  # noqa: E402
    plan_ending_text, plan_name, plan_off_text)


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
        "plan_ending_soon",
        "plan_off_by_daemon",
        "youHaveNewEpisodes",
        "withoutTariffSubscriptionsLimited",
        "award_welcome",
        "tariff_cannot_be_prolonged_by_daemon",
        "payViaTelegramStars",
        "telegram_stars_invoice_title",
        "telegram_stars_invoice_description",
        "bot_sub_stars_page_body",
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

    # The plan that ends is the user's own. Relay keeps its text as it is;
    # Bronze and Silver are named, as an apposition (plan names have a gender).
    for lang in langs:
        _assert(plan_name(1, lang) and plan_name(1, lang) != plan_name(3, lang),
                "%s: Bronze has its own name" % lang)
        _assert(plan_name(3, lang) == "Relay" and "🥇" not in plan_name(3, lang),
                "%s: the name has no medal" % lang)
        _assert(plan_ending_text(3, 3, lang) == get_message("relay_trial_ending", lang) % 3,
                "%s: the Relay D-3 text is unchanged" % lang)
        _assert(plan_off_text(3, lang) == get_message("tariff_cannot_be_prolonged_by_daemon", lang),
                "%s: the Relay 'plan is off' text is unchanged" % lang)
        for level in (1, 2):
            name = plan_name(level, lang)
            ending = plan_ending_text(level, 3, lang)
            off = plan_off_text(level, lang)
            _assert(name in ending and "3" in ending and "{" not in ending and "🥉" not in ending
                    and "🥈" not in ending, "%s/level %d: D-3 names the plan and the days" % (lang, level))
            _assert(name in off and "{" not in off, "%s/level %d: 'plan is off' names the plan" % (lang, level))
            _assert("Relay" in ending and "Relay" in off,
                    "%s/level %d: both still offer Relay" % (lang, level))
        _assert(plan_ending_text(0, 3, lang) == plan_ending_text(3, 3, lang)
                and plan_off_text(9, lang) == plan_off_text(3, lang),
                "%s: an unknown level keeps the Relay text (as before)" % lang)

    watcher = open(os.path.join(_ROOT, "app", "jobs", "balance_watcher.py"), encoding="utf-8").read()
    _assert("plan_off_text" in watcher and '"tariff_cannot_be_prolonged_by_daemon"' not in watcher,
            "the daemon's 'not prolonged' notice names the user's own plan")

    print("all relay copy checks passed")


if __name__ == "__main__":
    main()
