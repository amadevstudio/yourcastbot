# -*- coding: utf-8 -*-
"""Feed and iTunes URLs must reach the network as the feed wrote them.

Run from the repo root: python lib/requests/test_url.py
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.requests.url import normalize_url  # noqa: E402

# Callers of the old quote(url, safe=":/?=") that broke encoded URLs.
_URL_PARSERS = (
    "app/jobs/podcastsUpdater.py",
    "app/controller/builders/recsModule.py",
    "app/controller/builders/podcastModule.py",
    "app/service/podcast/podcast.py",
)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s" % label)


def main():
    unchanged = {
        "firstory tracker with an embedded encoded URL":
            "https://m.cdn.firstory.me/track/ckkqnneka7mxc0866j53j5ljw/cmu13bsfc00es01wzei47cz9q/"
            "https%3A%2F%2Ffile.cdn.firstory.me%2FRecord%2Fckkqnneka7mxc0866j53j5ljw%2Fcmu13bsfc00et01wzesywfkyw.mp3"
            "?v=1789381161839",
        "query separators":
            "https://injector.simplecastaudio.com/d45e/default.mp3?aid=rss_feed&awCollectionId=5936&feed=x",
        "Apple collectionViewUrl":
            "https://podcasts.apple.com/us/podcast/%E6%95%B8%E4%BD%8D%E6%99%82%E4%BB%A3-business-next/"
            "id1555393924?uo=4",
        "reserved characters":
            "https://cdn.example.com/a+b;c,d/@e!f$g'(h)*i~j.mp3?x=[1]#t",
        "podtrac prefix":
            "https://dts.podtrac.com/redirect.mp3/api.spreaker.com/download/episode/75117336/x.mp3",
    }
    for label, url in unchanged.items():
        _assert_eq(normalize_url(url), url, "unchanged: " + label)

    _assert_eq(normalize_url("https://example.com/Подкаст 1.mp3"),
               "https://example.com/%D0%9F%D0%BE%D0%B4%D0%BA%D0%B0%D1%81%D1%82%201.mp3",
               "non-ASCII and spaces are encoded")
    _assert_eq(normalize_url('https://example.com/a"b<c>.mp3'),
               "https://example.com/a%22b%3Cc%3E.mp3", "quotes and angle brackets are encoded")
    _assert_eq(normalize_url("https://example.com/100%.mp3"),
               "https://example.com/100%25.mp3", "a stray percent sign is encoded")
    _assert_eq(normalize_url("https://example.com/a%zz.mp3"),
               "https://example.com/a%25zz.mp3", "a broken escape is encoded")
    _assert_eq(normalize_url("\n  https://example.com/a.mp3 \n"),
               "https://example.com/a.mp3", "feed whitespace around the URL is dropped")

    samples = list(unchanged.values()) + ["https://example.com/Подкаст 1.mp3", "https://example.com/100%.mp3"]
    for url in samples:
        once = normalize_url(url)
        _assert_eq(normalize_url(once), once, "idempotent: " + url[:40])

    for rel in _URL_PARSERS:
        tree = ast.parse(open(os.path.join(_ROOT, rel), encoding="utf-8").read())
        quote_calls = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Name) and node.func.id == "quote"]
        _assert_eq(quote_calls, [], "%s builds URLs with normalize_url, not quote" % rel)

    print("all url checks passed")


if __name__ == "__main__":
    main()
