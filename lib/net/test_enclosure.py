# -*- coding: utf-8 -*-
"""Enclosure host + timeout classification. No network.

Run: python lib/net/test_enclosure.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.net.enclosure import enclosure_host_fault, host_from_url  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    _assert_eq(
        host_from_url("https://m.cdn.firstory.me/track/a.mp3?v=1"),
        "m.cdn.firstory.me", "host from url")
    _assert_eq(host_from_url(""), None, "empty url")
    _assert_eq(host_from_url("not-a-url"), None, "no host")

    timeout = (
        "HTTPSConnectionPool(host='m.cdn.firstory.me', port=443): "
        "Max retries exceeded with url: /x "
        "(Caused by ReadTimeoutError(Read timed out. (read timeout=30)))")
    _assert_eq(enclosure_host_fault(timeout), True, "read timeout is host fault")
    _assert_eq(
        enclosure_host_fault("Failed to establish a new connection: "
                             "[Errno -5] No address associated with hostname"),
        True, "dns is host fault")
    _assert_eq(
        enclosure_host_fault("404 Client Error: Not Found for url: https://x/a.mp3"),
        False, "404 is not a host cooldown")
    _assert_eq(
        enclosure_host_fault("Forbidden: bot was blocked by the user"),
        False, "blocked user is not a host fault")
    print("all enclosure checks passed")


if __name__ == "__main__":
    main()
