# -*- coding: utf-8 -*-
"""Delivery policy by file size. Pure, no I/O.

Run from the repo root: python app/service/record/test_delivery.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.record.delivery import Upload, fetch_by_url_first, upload_order  # noqa: E402
from lib.telegram import limits  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    _assert_eq(fetch_by_url_first(12), True, "12 MB: Telegram fetches the URL")
    _assert_eq(fetch_by_url_first(limits.URL_FETCH_MB), True, "exactly the URL limit still fetches")
    _assert_eq(fetch_by_url_first(20.9), False, "just over 20 MB: we download")

    _assert_eq(upload_order(12), (Upload.BOT_API, Upload.AGENT), "small: Bot API, agent as fallback")
    _assert_eq(upload_order(limits.BOT_UPLOAD_MB), (Upload.BOT_API, Upload.AGENT), "50 MB still Bot API")
    _assert_eq(upload_order(389), (Upload.AGENT, Upload.BOT_API), "389 MB: agent, then its file_id")
    _assert_eq(upload_order(limits.MTPROTO_UPLOAD_MB), (Upload.AGENT, Upload.BOT_API), "2 GB: agent")
    _assert_eq(upload_order(2100), (), "over 2 GB: nothing can take it")

    print("all delivery policy checks passed")


if __name__ == "__main__":
    main()
