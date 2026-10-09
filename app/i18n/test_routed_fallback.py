# -*- coding: utf-8 -*-
"""A routed message missing a language falls back to English, never "".

Telegram rejects an empty text ("message text is empty"): an es user who
searched a podcast's episodes and found nothing got no answer at all.

Run: python app/i18n/test_routed_fallback.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.i18n.messages import get_message_rtd, routed_messages  # noqa: E402

LANGUAGES = ("en", "ru", "pt-br", "es", "de", "he", "zh-hans", None)


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _routes(node, path):
    """Every route that ends at a {language: text} leaf."""
    if isinstance(node, dict) and isinstance(node.get("en"), str):
        yield path
        return
    if isinstance(node, dict):
        for key, child in node.items():
            yield from _routes(child, path + [key])


def _leaf(route):
    node = routed_messages
    for key in route:
        node = node[key]
    return node


def main():
    # A text not translated yet (every one is today) falls back to English
    routed_messages["_untranslated"] = {"en": "English only", "ru": "Только русский"}
    try:
        _assert(get_message_rtd(["_untranslated"], "es") == "English only",
                "a missing language gets the English text, not \"\"")
    finally:
        del routed_messages["_untranslated"]
    _assert(
        get_message_rtd(["errors", "unknown"], "ru")
        == routed_messages["errors"]["unknown"]["ru"],
        "a language that has the text still gets its own")

    # The episode list speaks of episodes, not subscriptions, in every language
    for key in ("empty", "empty_when_search"):
        texts = routed_messages["recs"]["errors"]["paging"][key]
        _assert(set(texts) == {"en", "ru", "pt-BR", "es", "de", "he"},
                "recs %s is translated to every language" % key)
    _assert(
        get_message_rtd(["recs", "errors", "paging", "empty_when_search"], "es")
        == routed_messages["recs"]["errors"]["paging"]["empty_when_search"]["es"],
        "es episode search with no results gets its own text")

    routes = list(_routes(routed_messages, []))
    _assert(len(routes) > 0, "routed messages found")
    untranslated = [".".join(route) for route in routes
                    if set(_leaf(route)) < {"en", "ru", "pt-BR", "es", "de", "he"}]
    _assert(not untranslated, "every routed text has all six languages: %r" % untranslated[:5])
    empty = [(".".join(route), lang) for route in routes for lang in LANGUAGES
             if not get_message_rtd(list(route), lang)]
    _assert(not empty, "no routed message is empty in any language: %r" % empty[:5])
    print("all routed fallback checks passed")


if __name__ == "__main__":
    main()
