# -*- coding: utf-8 -*-
"""HTTP ETag / Last-Modified feed fetch.

Uses mocked HTTP only — never opens production databases or the network.
Run from the repo root:
  python app/service/podcast/test_feed_etag.py
If cchardet/lxml are only in the app venv:
  venv/bin/python app/service/podcast/test_feed_etag.py
"""
import os
import sys
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.podcast import rss  # noqa: E402
from app.service.podcast import podcast as podcast_mod  # noqa: E402


MINIMAL_RSS = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<rss version="2.0"><channel>'
    b'<title>Test Feed</title>'
    b'<item><title>Ep1</title><guid>g1</guid></item>'
    b'</channel></rss>'
)


class FakeResponse:
    def __init__(self, status_code, content=b'', headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.ok = status_code < 400


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def test_304_is_not_modified_and_does_not_parse():
    calls = []
    parse_calls = []

    def fake_get(url, headers=None, timeout=None, **kwargs):
        calls.append({'url': url, 'headers': dict(headers or {})})
        return FakeResponse(304, content=b'', headers={'ETag': 'W/"abc"'})

    real_parse = rss.__parse_rss_root

    def spy_parse(content):
        parse_calls.append(content)
        return real_parse(content)

    with mock.patch.object(rss.feed_requester, 'get', fake_get), \
            mock.patch.object(rss, '__parse_rss_root', spy_parse):
        root, status, validators = rss.get_rss_root_with_status(
            'http://feed.example/rss', etag='W/"abc"',
            last_modified='Wed, 01 Jan 2020 00:00:00 GMT')

    _assert(root is False, "304 root is False")
    _assert(status == rss.FEED_STATUS_NOT_MODIFIED, "304 status is not_modified")
    _assert(not rss.feed_status_counts_as_failure(status),
            "304 does not count as feed failure")
    _assert(parse_calls == [], "304 does not parse body")
    _assert(len(calls) == 1, "304 is not retried with Empty headers")
    _assert(calls[0]['headers'].get('If-None-Match') == 'W/"abc"',
            "304 request sent If-None-Match")
    _assert(
        calls[0]['headers'].get('If-Modified-Since')
        == 'Wed, 01 Jan 2020 00:00:00 GMT',
        "304 request sent If-Modified-Since")
    _assert(validators.get('etag') == 'W/"abc"', "304 keeps weak ETag")


def test_304_must_not_be_treated_as_ok_content():
    # requests.Response.ok is True for 304 (status < 400). If we treated that
    # as a body, we would try to parse empty XML and call it unavailable.
    def fake_get(url, headers=None, timeout=None, **kwargs):
        return FakeResponse(304, content=b'', headers={})

    with mock.patch.object(rss.feed_requester, 'get', fake_get):
        root, status, _validators = rss.get_rss_root_with_status(
            'http://feed.example/rss', etag='"x"')

    _assert(status != rss.FEED_STATUS_OK, "304 is not ok-content")
    _assert(status != rss.FEED_STATUS_UNAVAILABLE, "304 is not unavailable")
    _assert(status != rss.FEED_STATUS_GONE, "304 is not gone")
    _assert(status == rss.FEED_STATUS_NOT_MODIFIED, "304 is not_modified")
    _assert(root is False, "304 has no parsed root")


def test_200_parses_and_returns_new_etag():
    def fake_get(url, headers=None, timeout=None, **kwargs):
        return FakeResponse(
            200, content=MINIMAL_RSS,
            headers={
                'ETag': '"new-etag"',
                'Last-Modified': 'Thu, 02 Jan 2020 00:00:00 GMT',
            })

    with mock.patch.object(rss.feed_requester, 'get', fake_get):
        root, status, validators = rss.get_rss_root_with_status(
            'http://feed.example/rss', etag='"old"')

    _assert(status == rss.FEED_STATUS_OK, "200 status is ok")
    _assert(root is not False, "200 body is parsed")
    _assert(root.tag == 'channel', "200 root is channel")
    _assert(validators.get('etag') == '"new-etag"', "200 returns new ETag")
    _assert(
        validators.get('last_modified') == 'Thu, 02 Jan 2020 00:00:00 GMT',
        "200 returns Last-Modified")


def test_podcast_info_query_threads_validators_and_304():
    def fake_get(url, headers=None, timeout=None, **kwargs):
        return FakeResponse(304, content=b'', headers={'ETag': '"keep"'})

    with mock.patch.object(rss.feed_requester, 'get', fake_get):
        root, pc_info = podcast_mod.podcast_info_query(
            {'rss_link': 'http://feed.example/rss'}, 'rss',
            etag='"keep"', last_modified=None)

    _assert(root is False, "query 304 root is False")
    _assert(pc_info.get('notModified') is True, "query 304 sets notModified")
    _assert('failureReason' not in pc_info,
            "query 304 is not a failureReason")
    _assert(pc_info.get('http_etag') == '"keep"', "query 304 returns etag")


def test_podcast_info_query_200_returns_etag():
    def fake_get(url, headers=None, timeout=None, **kwargs):
        return FakeResponse(
            200, content=MINIMAL_RSS, headers={'ETag': '"fresh"'})

    with mock.patch.object(rss.feed_requester, 'get', fake_get):
        root, pc_info = podcast_mod.podcast_info_query(
            {'rss_link': 'http://feed.example/rss'}, 'rss')

    _assert(root is not False, "query 200 has root")
    _assert(pc_info.get('http_etag') == '"fresh"', "query 200 http_etag")
    _assert(not pc_info.get('notModified'), "query 200 not notModified")


def test_scheduled_path_skips_itunes_when_rss_link_present():
    calls = []

    def fake_query(payload, service_name='itunes', direct_link=False,
                   etag=None, last_modified=None):
        calls.append({
            'service_name': service_name,
            'payload': payload,
            'etag': etag,
            'last_modified': last_modified,
        })
        return False, {
            'notModified': True,
            'http_etag': etag,
            'http_last_modified': last_modified,
        }

    channel = {
        'id': 7,
        'itunes_id': 999,
        'rss_link': 'http://feed.example/rss',
        'http_etag': '"abc"',
        'http_last_modified': 'Wed, 01 Jan 2020 00:00:00 GMT',
        'name': 'Show',
    }
    with mock.patch.object(podcast_mod, 'podcast_info_query', fake_query):
        root, pc_info, service_name, service_id = podcast_mod.fetch_channel_feed(
            channel, manual=False)

    _assert(len(calls) == 1, "scheduled rss_link: one fetch")
    _assert(calls[0]['service_name'] == 'rss', "scheduled uses rss, not itunes")
    _assert(calls[0]['payload'] == {'rss_link': 'http://feed.example/rss'},
            "scheduled payload is rss_link")
    _assert(calls[0]['etag'] == '"abc"', "scheduled sends stored etag")
    _assert(service_name == 'rss', "scheduled service_name is rss")
    _assert(pc_info.get('notModified') is True, "scheduled 304 bubbles up")
    _assert(root is False, "scheduled 304 root is False")


def test_manual_path_still_tries_itunes_first():
    calls = []

    def fake_query(payload, service_name='itunes', direct_link=False,
                   etag=None, last_modified=None):
        calls.append(service_name)
        if service_name == 'itunes':
            return False, {'failureReason': rss.FEED_STATUS_UNAVAILABLE}
        return False, {'notModified': True, 'http_etag': etag}

    channel = {
        'id': 7,
        'itunes_id': 999,
        'rss_link': 'http://feed.example/rss',
        'http_etag': '"abc"',
        'name': 'Show',
    }
    with mock.patch.object(podcast_mod, 'podcast_info_query', fake_query):
        podcast_mod.fetch_channel_feed(channel, manual=True)

    _assert(calls == ['itunes', 'rss'], "manual keeps itunes-then-rss")


def test_404_is_gone_503_is_unavailable():
    def gone_get(url, headers=None, timeout=None, **kwargs):
        return FakeResponse(404, content=b'nope')

    with mock.patch.object(rss.feed_requester, 'get', gone_get), \
            mock.patch.object(rss, 'FEED_RETRY_PAUSE_SECONDS', 0):
        root, status, _v = rss.get_rss_root_with_status('http://feed.example/rss')
    _assert(status == rss.FEED_STATUS_GONE, "404 is gone")
    _assert(rss.feed_status_counts_as_failure(status), "404 counts as failure")

    def fail_get(url, headers=None, timeout=None, **kwargs):
        return FakeResponse(503, content=b'')

    with mock.patch.object(rss.feed_requester, 'get', fail_get), \
            mock.patch.object(rss, 'FEED_RETRY_PAUSE_SECONDS', 0):
        root, status, _v = rss.get_rss_root_with_status('http://feed.example/rss')
    _assert(status == rss.FEED_STATUS_UNAVAILABLE, "503 is unavailable")


def main():
    test_304_is_not_modified_and_does_not_parse()
    test_304_must_not_be_treated_as_ok_content()
    test_200_parses_and_returns_new_etag()
    test_podcast_info_query_threads_validators_and_304()
    test_podcast_info_query_200_returns_etag()
    test_scheduled_path_skips_itunes_when_rss_link_present()
    test_manual_path_still_tries_itunes_first()
    test_404_is_gone_503_is_unavailable()
    print("all feed etag checks passed")


if __name__ == "__main__":
    main()
