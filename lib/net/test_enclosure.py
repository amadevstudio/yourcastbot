# -*- coding: utf-8 -*-
"""Enclosure host + timeout classification. No network.

Run: python lib/net/test_enclosure.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.net.enclosure import (  # noqa: E402
    enclosure_host_fault, enclosure_hosts, host_from_error, host_from_url)


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

    # The download died at the CDN behind the redirector, and the redirector
    # carries unrelated podcasts: cool what the error names, not the URL host.
    nbc = (
        "HTTPSConnectionPool(host='nbcnews.simplecastaudio.com', port=443): "
        "Read timed out. (read timeout=15)")
    _assert_eq(
        host_from_error(nbc), "nbcnews.simplecastaudio.com", "host from pool error")
    _assert_eq(
        host_from_error("Failed to resolve 'traffic.omny.fm' ([Errno -5])"),
        "traffic.omny.fm", "host from resolver error")
    _assert_eq(
        host_from_error("404 Client Error: Not Found for url: https://x/a.mp3"),
        None, "no host in a plain http error")
    _assert_eq(host_from_error(None), None, "no error, no host")

    _assert_eq(
        enclosure_hosts(
            "https://dts.podtrac.com/redirect.mp3/chrt.fm/track/A1B2/"
            "nbcnews.simplecastaudio.com/audio/ep.mp3?aid=rss_feed"),
        ["dts.podtrac.com", "chrt.fm", "nbcnews.simplecastaudio.com"],
        "tracker link carries its target hosts")
    _assert_eq(
        enclosure_hosts(
            "https://m.cdn.firstory.me/track/ID/https%3A%2F%2Fcdn.firstory.me/a.mp3"),
        ["m.cdn.firstory.me", "cdn.firstory.me"],
        "percent-encoded target is seen too")
    _assert_eq(
        enclosure_hosts("https://traffic.megaphone.fm/EP123.mp3"),
        ["traffic.megaphone.fm"], "direct link is its own host")
    _assert_eq(enclosure_hosts(""), [], "no url, no hosts")
    print("all enclosure checks passed")


if __name__ == "__main__":
    main()
