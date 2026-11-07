# -*- coding: utf-8 -*-
"""An episode link from Apple Podcasts names the episode: its show and RSS
guid come from Apple's lookup (the newest 200), else from the episode's
page (any age; the page's show wins over the link's). A podcast link, a
lookup and a page that do not know the episode, or Apple down: None, never
an exception.

Run from the repo root: python app/service/podcast/test_apple_episode.py
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.podcast import apple_episode, catalog  # noqa: E402
from app.service.podcast.apple_episode import Episode, Link  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class Response:
    def __init__(self, content, status=200):
        self.status_code, self.content = status, content.encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise IOError('HTTP %d' % self.status_code)


def lookup_answer(*episodes):
    results = [{'wrapperType': 'track', 'kind': 'podcast', 'collectionId': 111}]
    results += [{'wrapperType': 'podcastEpisode', 'collectionId': 111, 'trackId': tid, 'episodeGuid': guid}
                for tid, guid in episodes]
    return json.dumps({'resultCount': len(results), 'results': results})


def page(episode_id, show_id, guid, other=None):
    """An episode page as Apple serves it, cut to what is read; `other` another episode's offer first."""
    items = []
    if other is not None:
        items.append({'id': other[0], 'playAction': {'episodeOffer': {'guid': other[1]}}})
    items.append({'id': str(episode_id), 'primaryButtonAction': {'episodeOffer': {
        'guid': guid, 'title': 'An episode', 'podcastOffer': {'adamId': show_id}}}})
    data = {'data': [{'intent': {'$kind': 'EpisodePageIntent', 'adamId': str(episode_id),
                                 'showAdamId': str(show_id)},
                      'data': {'shelves': [{'items': items}]}}]}
    return ('<html><script type="application/json" id="serialized-server-data">%s</script></html>'
            % json.dumps(data))


class Apple:
    """A fake requests.get: the lookup and the episode page."""

    def __init__(self, lookup=None, html=None, lookup_status=200, page_status=200):
        self.lookup, self.html = lookup, html
        self.lookup_status, self.page_status = lookup_status, page_status
        self.calls = []

    def __call__(self, url, params=None, **_):
        self.calls.append((url, params))
        if url == catalog.APPLE_LOOKUP:
            return Response(self.lookup or lookup_answer(), self.lookup_status)
        return Response(self.html or '<html></html>', self.page_status)


def test_parse():
    _assert(apple_episode.parse(
        'https://podcasts.apple.com/us/podcast/we-take-john-turturro/id121493804?i=1000798990714')
        == Link(121493804, 1000798990714, 'us'), "a shared episode link: show, episode, storefront")
    _assert(apple_episode.parse('look https://podcasts.apple.com/gb/podcast/id5?uo=4&i=7 thanks')
            == Link(5, 7, 'gb'), "i= after another parameter, inside a message")
    _assert(apple_episode.parse('https://podcasts.apple.com/podcast/id5?i=7') == Link(5, 7, 'us'),
            "no storefront: us")
    _assert(apple_episode.parse('https://podcasts.apple.com/us/podcast/x/id121493804') is None,
            "a podcast link is not an episode link")
    _assert(apple_episode.parse('https://example.com/podcast/id1?i=2') is None, "not Apple's")
    _assert(apple_episode.parse(None) is None, "no text")


def test_lookup_first():
    apple = Apple(lookup=lookup_answer((9, 'guid-9'), (8, 'guid-8')))
    _assert(apple_episode.find(Link(111, 8, 'us'), get=apple) == Episode(111, 'guid-8'),
            "the lookup's episode with the link's trackId")
    _assert(apple.calls[0][1] == {'id': 111, 'entity': 'podcastEpisode', 'limit': 200},
            "the show's newest 200 episodes are asked for")
    _assert(len(apple.calls) == 1, "found there: the page is not fetched")


def test_page_fallback():
    apple = Apple(lookup=lookup_answer((9, 'guid-9')), html=page(3, 222, 'old-guid', other=('9', 'guid-9')))
    _assert(apple_episode.find(Link(111, 3, 'ru'), get=apple) == Episode(222, 'old-guid'),
            "older than the lookup's 200: the page's guid, the page's show over the link's")
    _assert(apple.calls[1][0] == 'https://podcasts.apple.com/ru/podcast/id111?i=3',
            "the page in the link's storefront")

    apple = Apple(lookup_status=503, html=page(3, 111, 'g3'))
    _assert(apple_episode.find(Link(111, 3, 'us'), get=apple) == Episode(111, 'g3'),
            "the lookup down: the page")


def test_unknown():
    show_page = page(3, 111, 'g3').replace('"adamId": "3"', '"adamId": "111"')
    _assert(apple_episode.find(Link(111, 3, 'us'), get=Apple(html=show_page)) is None,
            "redirected to the show's page (a wrong i=): None")
    _assert(apple_episode.find(Link(111, 3, 'us'), get=Apple(html='<html>changed</html>')) is None,
            "a page without its data (format changed): None")
    _assert(apple_episode.find(Link(111, 3, 'us'), get=Apple(lookup_status=500, page_status=500)) is None,
            "Apple down: None, no exception")
    broken = '<script id="serialized-server-data">{not json</script>'
    _assert(apple_episode.find(Link(111, 3, 'us'), get=Apple(html=broken)) is None, "broken JSON: None")


if __name__ == '__main__':
    test_parse()
    test_lookup_first()
    test_page_fallback()
    test_unknown()
    print("all ok")
