# -*- coding: utf-8 -*-
"""Where podcasts are found: Apple's directory, with the Podcast Index beside it.

Search, the podcast page, subscribing and feed recovery all asked Apple
alone: Apple down or slow meant no search, no page, no subscription. The
Podcast Index (podcastindex.org, open, no key for these two calls) answers
the same `search` and `lookup` in Apple's own format and lists podcasts by
their Apple id, so `channels.itunes_id` keeps its meaning (delivery trusts
iTunes-listed podcasts) whichever directory answered.

- search: both are asked at once. Apple's results come first, in Apple's
  order; then the Index's podcasts Apple did not return for that term (a
  Russian "психология": Apple 25, the Index 60). Apple slow or down: the
  Index alone. The Index slow: Apple alone, after a short wait.
- lookup: Apple first. The Index only when Apple fails or lists no feed for
  that id. Its feedUrl can be an older address of the same show
  (feedburner for TED Talks Daily), so callers that store a URL keep the
  one they have (see subscription.add_sub, feed recovery).
"""
import json
import threading

import requests

from lib.tools.logger import logger

APPLE_SEARCH = 'https://itunes.apple.com/search'
APPLE_LOOKUP = 'https://itunes.apple.com/lookup'
INDEX_SEARCH = 'https://api.podcastindex.org/search'
INDEX_LOOKUP = 'https://api.podcastindex.org/lookup'

APPLE = 'apple'
INDEX = 'index'

TIMEOUT = (5, 15)  # (connect, read)
INDEX_GRACE_SECONDS = 2  # how long a search that has Apple's answer waits for the Index
HEADERS = {'User-Agent': 'yourcastbot'}  # the Index refuses requests without one


class CatalogUnavailable(Exception):
    """Neither directory answered."""


def _results(url, params, get=None) -> list[dict]:
    response = (get or requests.get)(url, params=params, timeout=TIMEOUT, headers=HEADERS)
    response.raise_for_status()
    results = json.loads(response.content.decode('utf-8')).get('results')
    if not isinstance(results, list):
        raise ValueError('no results in the answer')
    return [item for item in results if isinstance(item, dict)]


def _ask(url, params, get, answer: dict, key: str):
    try:
        answer[key] = _results(url, params, get)
    except Exception as e:
        logger.warn("catalog", key, "failed:", url, type(e).__name__, str(e)[:120])


def _listed(item) -> bool:
    """An Index result the search screens can show (they read these keys as Apple's)."""
    return bool(item.get('collectionId') and item.get('collectionName') and item.get('feedUrl')
                and item.get('collectionViewUrl')) and 'trackCount' in item and 'releaseDate' in item


def search(term, get=None, grace=INDEX_GRACE_SECONDS) -> dict:
    """{'resultCount', 'results'} in Apple's format: Apple's, then the Index's others."""
    answer: dict = {}
    apple = threading.Thread(target=_ask, daemon=True,
                             args=(APPLE_SEARCH, {'media': 'podcast', 'term': term}, get, answer, APPLE))
    index = threading.Thread(target=_ask, daemon=True,
                             args=(INDEX_SEARCH, {'term': term}, get, answer, INDEX))
    apple.start()
    index.start()
    apple.join()
    index.join(grace if APPLE in answer else None)
    if APPLE not in answer and INDEX not in answer:
        raise CatalogUnavailable(term)

    results = list(answer.get(APPLE, []))
    seen = {item.get('collectionId') for item in results}
    for item in list(answer.get(INDEX, [])):
        if _listed(item) and item['collectionId'] not in seen:
            seen.add(item['collectionId'])
            results.append(item)
    return {'resultCount': len(results), 'results': results}


def _has_feed(results, itunes_id) -> bool:
    return any(str(item.get('collectionId')) == str(itunes_id) and item.get('feedUrl') for item in results)


def feed_urls(itunes_id, get=None) -> list[str]:
    """Every feedUrl the directories give for this id, Apple's first (feed recovery
    validates each in turn). Raises CatalogUnavailable when neither answered."""
    from lib.requests.url import normalize_url
    params = {'entity': 'podcast', 'id': itunes_id}
    urls, answered = [], 0
    for name, url in ((APPLE, APPLE_LOOKUP), (INDEX, INDEX_LOOKUP)):
        try:
            results = _results(url, params, get)
        except Exception as e:
            logger.warn("catalog", name, "lookup failed:", itunes_id, type(e).__name__, str(e)[:120])
            continue
        answered += 1
        for item in results:
            if str(item.get('collectionId')) == str(itunes_id) and item.get('feedUrl'):
                feed = normalize_url(item['feedUrl'])
                if feed.startswith(('http://', 'https://')) and feed not in urls:
                    urls.append(feed)
                break
    if not answered:
        raise CatalogUnavailable(itunes_id)
    return urls


def lookup(itunes_id, get=None) -> tuple[list[dict], str]:
    """(results in Apple's format, APPLE or INDEX): Apple, or the Index when Apple fails or has no feed."""
    params = {'entity': 'podcast', 'id': itunes_id}
    apple_error = None
    results: list[dict] = []
    try:
        results = _results(APPLE_LOOKUP, params, get)
        if _has_feed(results, itunes_id):
            return results, APPLE
    except Exception as e:
        apple_error = e
        logger.warn("catalog apple lookup failed:", itunes_id, type(e).__name__, str(e)[:120])
    try:
        index_results = _results(INDEX_LOOKUP, params, get)
    except Exception as e:
        logger.warn("catalog index lookup failed:", itunes_id, type(e).__name__, str(e)[:120])
        if apple_error is not None:
            raise CatalogUnavailable(itunes_id)
        return results, APPLE  # Apple answered without this feed, as before
    if _has_feed(index_results, itunes_id):
        return index_results, INDEX
    return results, APPLE
