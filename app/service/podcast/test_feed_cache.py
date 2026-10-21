# -*- coding: utf-8 -*-
"""The last copy of a feed a person opened: read without the network while
fresh, after a 304 when older, replaced by a changed feed in one download,
dropped when the updater fetches a new version, kept within its space and
never at the cost of the disk's free room.

Run from the repo root: python app/service/podcast/test_feed_cache.py
(the rss part runs where the bot's requirements are installed).
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.podcast import feed_cache  # noqa: E402
from lib.system.disk_budget import MB  # noqa: E402

PLENTY = lambda: 10_000 * MB  # noqa: E731
FEED = b'<rss><channel><title>Show</title><item><title>One</title></item></channel></rss>'
NEWER = b'<rss><channel><title>Show</title><item><title>Two</title></item></channel></rss>'


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def test_store(db, folder):
    url = 'https://feeds.example/show.xml'
    _assert(feed_cache.get(url, database=db, directory=folder) is None, "nothing kept yet")
    _assert(feed_cache.put(url, FEED, 'etag-1', None, now=1000, database=db, directory=folder,
                           disk_free=PLENTY), "a copy is kept")
    entry = feed_cache.get(url, now=1000 + feed_cache.FRESH_SECONDS - 1, database=db, directory=folder)
    _assert(entry.content == FEED and entry.etag == 'etag-1' and entry.fresh, "fresh within the window")
    _assert(not feed_cache.get(url, now=1000 + feed_cache.FRESH_SECONDS + 1, database=db,
                               directory=folder).fresh, "older: to be asked for with its ETag")
    feed_cache.touch(url, now=5000, database=db)
    _assert(feed_cache.get(url, now=5001, database=db, directory=folder).fresh, "a 304 makes it fresh again")

    low = lambda: feed_cache.MIN_FREE_BYTES + feed_cache.DOWNLOAD_ROOM_BYTES  # noqa: E731
    _assert(not feed_cache.put(url, NEWER, None, None, database=db, directory=folder, disk_free=low),
            "no room on the disk: not kept")
    _assert(feed_cache.get(url, database=db, directory=folder) is None,
            "and the old copy goes too: it must not stand for a feed that changed")

    feed_cache.put(url, FEED, None, None, database=db, directory=folder, disk_free=PLENTY)
    os.remove(os.path.join(folder, feed_cache._file_name(url)))
    _assert(feed_cache.get(url, database=db, directory=folder) is None, "a lost file is no copy")


def test_space(db, folder):
    saved = feed_cache.TOTAL_BYTES
    feed_cache.TOTAL_BYTES = 3 * len(FEED)
    try:
        for i, url in enumerate(('https://a/1', 'https://a/2', 'https://a/3')):
            feed_cache.put(url, FEED, None, None, now=100 + i, database=db, directory=folder, disk_free=PLENTY)
        feed_cache.get('https://a/1', now=200, database=db, directory=folder)  # used again
        feed_cache.put('https://a/4', FEED, None, None, now=300, database=db, directory=folder, disk_free=PLENTY)
        kept = [u for u in ('https://a/1', 'https://a/2', 'https://a/3', 'https://a/4')
                if feed_cache.get(u, now=301, database=db, directory=folder) is not None]
        _assert(kept == ['https://a/1', 'https://a/3', 'https://a/4'], "the least recently used goes first")
        _assert(len(os.listdir(folder)) == 3, "and its file with it")
    finally:
        feed_cache.TOTAL_BYTES = saved


def test_rss(db, folder):
    try:
        from app.service.podcast import rss
    except Exception as e:  # CI has no bot requirements
        print("skip rss (%s)" % e.__class__.__name__)
        return
    calls, answers = [], []

    def load(url, headers=None, etag=None, last_modified=None):
        calls.append(dict(headers or {}))
        return answers.pop(0)

    def ok(content, etag):
        return {'content': content, 'status': rss.FEED_STATUS_OK,
                'validators': rss.empty_validators(etag, None), 'error': None}

    not_modified = {'content': False, 'status': rss.FEED_STATUS_NOT_MODIFIED,
                    'validators': rss.empty_validators('e1', None), 'error': None}
    saved = (getattr(rss, '__load_rss_root'), feed_cache.get, feed_cache.put, feed_cache.touch, feed_cache.forget)
    setattr(rss, '__load_rss_root', load)
    feed_cache.get = lambda url, **k: saved[1](url, database=db, directory=folder, **k)
    feed_cache.put = lambda url, content, etag=None, lm=None, **k: saved[2](
        url, content, etag, lm, database=db, directory=folder, disk_free=PLENTY)
    feed_cache.touch = lambda url, **k: saved[3](url, database=db)
    feed_cache.forget = lambda url, **k: saved[4](url, database=db, directory=folder)
    url = 'https://feeds.example/big.xml'

    def titles(root):
        return [item.findtext('title') for item in root.iter('item')]

    try:
        answers[:] = [ok(FEED, 'e1')]
        root, status, _ = rss.get_rss_root_with_status(url, cached=True)
        _assert(titles(root) == ['One'] and len(calls) == 1, "first open: downloaded and kept")
        root, _, _ = rss.get_rss_root_with_status(url, cached=True)
        _assert(titles(root) == ['One'] and len(calls) == 1, "the next tap reads the copy, no network")

        feed_cache.touch = lambda url, **k: saved[3](url, now=0, database=db)  # make it old
        feed_cache.touch(url)
        feed_cache.touch = lambda url, **k: saved[3](url, database=db)
        answers[:] = [not_modified]
        root, _, _ = rss.get_rss_root_with_status(url, cached=True)
        _assert(titles(root) == ['One'] and len(calls) == 2 and calls[-1].get('If-None-Match') == 'e1',
                "an old copy is asked for with its ETag; a 304 reads it from disk")

        feed_cache.touch = lambda url, **k: saved[3](url, now=0, database=db)
        feed_cache.touch(url)
        feed_cache.touch = lambda url, **k: saved[3](url, database=db)
        answers[:] = [ok(NEWER, 'e2')]
        root, _, validators = rss.get_rss_root_with_status(url, cached=True)
        _assert(titles(root) == ['Two'] and len(calls) == 3 and validators['etag'] == 'e2',
                "a changed feed is downloaded once and replaces the copy")

        answers[:] = [ok(NEWER, 'e3')]
        rss.get_rss_root_with_status(url)
        _assert(saved[1](url, database=db, directory=folder) is None,
                "the updater fetching a new version drops the copy: no new episode hides behind it")

        answers[:] = [ok(FEED, 'e1')]
        rss.get_rss_root_with_status(url, etag='e0', cached=True)
        _assert(saved[1](url, database=db, directory=folder) is None,
                "a conditional caller (the updater's own ETag) never reads or fills the copy")
    finally:
        setattr(rss, '__load_rss_root', saved[0])
        feed_cache.get, feed_cache.put, feed_cache.touch, feed_cache.forget = saved[1:]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'test.sqlite')
        for test in (test_store, test_space, test_rss):
            folder = os.path.join(tmp, test.__name__)
            os.makedirs(folder)
            test(db, folder)
    print("all feed cache checks passed")


if __name__ == "__main__":
    main()
