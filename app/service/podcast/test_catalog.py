# -*- coding: utf-8 -*-
"""Apple's directory with the Podcast Index beside it: search shows Apple's
results first and adds the Index's others; Apple down or slow, the Index
alone; lookup asks the Index only when Apple fails or has no feed; neither
answering is "unavailable", never a crash.

Run from the repo root: python app/service/podcast/test_catalog.py
"""
import json
import os
import sys
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.podcast import catalog  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class Response:
    def __init__(self, results, status=200):
        self.status_code, self.content = status, json.dumps({'resultCount': len(results), 'results': results}).encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise IOError('HTTP %d' % self.status_code)


def show(cid, name, feed='https://feed.example/%s'):
    return {'collectionId': cid, 'collectionName': name, 'feedUrl': feed % cid if '%s' in feed else feed, 'trackCount': 3,
            'collectionViewUrl': 'https://podcasts.apple.com/us/podcast/*/id%s' % cid,
            'releaseDate': '2026-10-01T00:00:00Z'}


def directory(apple=None, index=None, slow_index=None):
    """A fake requests.get: a list answers, an exception is raised, None is a 503."""
    calls = []

    def get(url, params=None, timeout=None, headers=None):
        calls.append(url)
        answer = apple if url in (catalog.APPLE_SEARCH, catalog.APPLE_LOOKUP) else index
        if url == catalog.INDEX_SEARCH and slow_index is not None:
            slow_index.wait(5)
        if isinstance(answer, Exception):
            raise answer
        return Response(answer if answer is not None else [], status=200 if answer is not None else 503)
    get.calls = calls
    return get


def test_search():
    apple = [show(1, 'Huberman Lab'), show(2, 'Lex Fridman Podcast')]
    index = [show(2, 'Lex Fridman Podcast'), show(3, 'Психология'),
             {'collectionId': 4, 'collectionName': 'No feed'},
             dict(show(5, 'No page link'), collectionViewUrl='')]
    found = catalog.search('term', get=directory(apple, index))
    _assert([r['collectionId'] for r in found['results']] == [1, 2, 3] and found['resultCount'] == 3,
            "Apple's results first, in its order, then the Index's others; one row per podcast; only Index rows with every field the search and inline screens read")
    _assert([r['collectionId'] for r in catalog.search('term', get=directory(TimeoutError(), index))['results']]
            == [2, 3], "Apple down: the Index alone")
    _assert([r['collectionId'] for r in catalog.search('term', get=directory(apple, None))['results']] == [1, 2],
            "the Index down: Apple alone, as before")
    released = threading.Event()
    try:
        found = catalog.search('term', get=directory(apple, index, slow_index=released), grace=0.1)
        _assert([r['collectionId'] for r in found['results']] == [1, 2],
                "a slow Index does not hold the search: Apple's answer goes after a short wait")
    finally:
        released.set()
    try:
        catalog.search('term', get=directory(TimeoutError(), None))
        _assert(False, "neither answering raises")
    except catalog.CatalogUnavailable:
        _assert(True, "neither answering is CatalogUnavailable")


def test_lookup():
    apple = [show(7, 'Show', 'https://apple.example/%s')]
    index = [show(7, 'Show', 'https://older.example/%s')]
    get = directory(apple, index)
    results, source = catalog.lookup(7, get=get)
    _assert(source == catalog.APPLE and results[0]['feedUrl'] == 'https://apple.example/7'
            and get.calls == [catalog.APPLE_LOOKUP], "Apple answers: the Index is not asked")
    results, source = catalog.lookup(7, get=directory(TimeoutError(), index))
    _assert(source == catalog.INDEX and results[0]['feedUrl'] == 'https://older.example/7', "Apple down: the Index")
    results, source = catalog.lookup(7, get=directory([], index))
    _assert(source == catalog.INDEX, "Apple has no feed for the id (delisted): the Index")
    results, source = catalog.lookup(7, get=directory([], TimeoutError()))
    _assert(results == [] and source == catalog.APPLE, "Apple has none and the Index is down: no feed, as before")
    try:
        catalog.lookup(7, get=directory(TimeoutError(), None))
        _assert(False, "neither answering raises")
    except catalog.CatalogUnavailable:
        _assert(True, "neither answering is CatalogUnavailable (the page says unavailable)")


def test_page_lookup():
    try:
        from app.service.podcast import podcast
    except Exception as e:  # CI has no bot requirements
        print("skip page (%s)" % e.__class__.__name__)
        return
    saved = catalog.lookup

    def down(itunes_id, get=None):
        raise catalog.CatalogUnavailable(itunes_id)
    catalog.lookup = down
    try:
        root, info = podcast.podcast_info_query({'entity': 'podcast', 'id': 7})
        _assert(root is False and info['failureReason'] == podcast.FEED_STATUS_UNAVAILABLE,
                "the page: both directories down is 'unavailable'")
    finally:
        catalog.lookup = saved


def test_subscribe():
    try:
        from app.service.podcast import subscription
    except Exception as e:  # CI has no bot requirements
        print("skip subscribe (%s)" % e.__class__.__name__)
        return
    stored, written = {'rss_link': 'http://stored.example/feed'}, []

    class DB:
        def __init__(self, *_):
            pass

        def get_channel_by_service(self, service_id, service_name='itunes'):
            return stored

        def close(self):
            pass

    saved = (catalog.lookup, subscription.SQLighter, subscription.add_sub_rss)
    subscription.SQLighter = DB
    subscription.add_sub_rss = lambda u, p, sid, sname, rss_link, additional_info=None: (written.append(rss_link)
                                                                                          or ('Show', 5))
    try:
        for source, feed in ((catalog.INDEX, 'https://older.example/feed'), (catalog.APPLE, 'https://apple.example/feed')):
            catalog.lookup = lambda itunes_id, get=None, s=source, f=feed: (
                [show(7, 'Show', f)], s)
            subscription.add_sub(1, 5, 7)
        _assert(written == ['http://stored.example/feed', 'https://apple.example/feed'],
                "subscribing through the Index keeps the channel's own feed; Apple's URL is stored as before")
        stored = None
        catalog.lookup = lambda itunes_id, get=None: ([show(7, 'Show', 'https://older.example/feed')], catalog.INDEX)
        subscription.add_sub(1, None, 7)
        _assert(written[-1] == 'https://older.example/feed', "a new channel takes the Index's feed")
        catalog.lookup = lambda itunes_id, get=None: (_ for _ in ()).throw(catalog.CatalogUnavailable(7))
        _assert(subscription.add_sub(1, None, 7) == (None, None), "both directories down: not subscribed, no crash")
    finally:
        catalog.lookup, subscription.SQLighter, subscription.add_sub_rss = saved


def main():
    test_search()
    test_lookup()
    test_page_lookup()
    test_subscribe()
    print("all catalog checks passed")


if __name__ == "__main__":
    main()
