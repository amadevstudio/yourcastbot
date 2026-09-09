# -*- coding: utf-8 -*-
"""Unavailable copy includes links. No network.

Run: python app/i18n/test_unavailable_copy.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.i18n.messages import (  # noqa: E402
    format_record_unavailable, format_feed_notice)


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def main():
    rec = format_record_unavailable(
        "ru", "https://site.example/show", "https://cdn.example/ep.mp3")
    _assert("официальном сайте" in rec, "site link in ru rec")
    _assert("https://site.example/show" in rec, "site href")
    _assert("прямой ссылке" in rec, "file link in ru rec")
    _assert("https://cdn.example/ep.mp3" in rec, "file href")

    bare = format_record_unavailable("en", None, "https://cdn.example/ep.mp3")
    _assert("unavailable" in bare.lower() or "Unfortunately" in bare,
            "bare sentence without site")
    _assert("https://cdn.example/ep.mp3" in bare, "file link without site")
    _assert("%s" not in bare, "no leftover placeholder")

    feed = format_feed_notice(
        "ru", "feedTemporarilyUnavailable", "http://dead.example/rss.xml")
    _assert("Уведомления остались включёнными" in feed, "temp body")
    _assert("http://dead.example/rss.xml" in feed, "rss href on temp notice")
    _assert("открыть RSS" in feed, "rss link label")

    off = format_feed_notice(
        "en", "notificationsFCDisabled", "http://dead.example/rss.xml")
    _assert("disabled" in off.lower(), "disabled body")
    _assert("http://dead.example/rss.xml" in off, "rss href on disable notice")

    no_url = format_feed_notice("ru", "feedTemporarilyUnavailable", "")
    _assert("открыть RSS" not in no_url, "no rss line without url")
    print("all unavailable copy checks passed")


if __name__ == "__main__":
    main()
