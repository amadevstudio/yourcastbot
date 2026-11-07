# -*- coding: utf-8 -*-
"""Right after a subscription the show's newest episode is queued as a click
would queue it: the newest item, counted by the free limit, quiet when it
cannot go (a feed that fails, the limit, several clicks already waiting), and
never failing the subscription. A click on an episode is unchanged. An
episode link from Apple Podcasts queues that episode (Apple's guid) the same way.

Run from the repo root: python app/controller/builders/test_latest_episode.py
(the behaviour runs where the bot's requirements are installed).
"""
import os
import sys
from hashlib import sha256

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.controller.builders.test_open_recs import import_builder  # noqa: E402

FEED = b"""<rss><channel><title>Show</title><link>https://show.example/</link>
<item><title>Newest</title><guid>g2</guid><pubDate>Thu, 22 Oct 2026 10:00:00 GMT</pubDate>
<enclosure url="https://cdn.example/2.mp3"/></item>
<item><title>Older</title><guid>g1</guid><pubDate>Wed, 21 Oct 2026 10:00:00 GMT</pubDate>
<enclosure url="https://cdn.example/1.mp3"/></item>
</channel></rss>"""


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class FakeDB:
    def __init__(self, *_):
        pass

    def get_channel(self, channel_id):
        return {'id': channel_id, 'itunes_id': 500, 'rss_link': 'https://feeds.example/x.xml'} if channel_id == 7 else None

    def get_channel_by_service(self, service_id, service_name='itunes'):
        return {'id': 7, 'itunes_id': 500, 'rss_link': None} if service_id == 500 else None

    def get_user_by_tg(self, chat_id):
        return {'bitrate': None}

    def close(self):
        pass


def test_behaviour(recs):
    from lxml import etree
    root = etree.fromstring(FEED).find('channel')
    state = {'root': root, 'allowed': True, 'open': set()}
    queued, renders = [], []
    recs.SQLighter = FakeDB
    recs.app.service.podcast.podcast.podcast_info_query = lambda *a, **k: (state['root'], {'itunesLink': None})
    recs.outbox.open_user_rec_links = lambda chat_id: state['open']
    recs.outbox.enqueue_user_rec = lambda job: queued.append(job)
    hits = []
    recs.free_limit.limit_hit = lambda chat_id, link, open_links: (
        None if state['allowed'] else recs.free_limit.Hit('week', 3600, 0))
    recs.free_limit.hit_message = lambda hit, lang: {'type': 'text', 'text': 'limit'}
    recs.analytics_events.free_limit_hit = lambda chat_id, limit, quiet, wait: hits.append((chat_id, limit, quiet))
    recs.render_messages = lambda chat_id, structures, *a, **k: renders.append(structures)

    _assert(recs.send_latest_episode(7, 1001, 'en') is True, "a subscription queues an episode")
    info = queued[-1]['func_params']['podcastInfo']
    _assert(queued[-1]['func_params']['link'] == 'https://cdn.example/2.mp3' and info['title'] == 'Newest'
            and info['recNum'] == 0 and queued[-1]['action'] == 'rec' and queued[-1]['user_id'] == 1001,
            "the newest one, as a click on it (the rec pool, one at a time per chat)")

    state['allowed'] = False
    _assert(recs.send_latest_episode(7, 1001, 'en') is False and not renders,
            "at the free limit: nothing, and no limit message for a gift nobody asked for")
    _assert(hits == [(1001, 'week', True)], "the stop is counted, as a quiet one")
    state['allowed'], state['open'] = True, {'a', 'b', 'c'}
    _assert(recs.send_latest_episode(7, 1001, 'en') is False, "three clicks waiting: no more (several ticks at once)")
    state['open'], state['root'] = set(), False
    _assert(recs.send_latest_episode(7, 1001, 'en') is False and not renders, "a feed that fails: quiet")
    _assert(recs.send_latest_episode(8, 1001, 'en') is False, "a channel gone: nothing")
    recs.SQLighter = None  # a database error
    _assert(recs.send_latest_episode(7, 1001, 'en') is False, "an error never reaches the subscription")
    recs.SQLighter = FakeDB

    state['root'], state['allowed'] = root, True
    older = sha256('g1_Wed, 21 Oct 2026 10:00:00 GMT_Older'.encode()).hexdigest()[:recs.maxPodcastDateCallDataHexLen]
    recs.send_record_direct({'id': 7, 'itunes_id': 500}, 1001, 'en', older, None)
    _assert(queued[-1]['func_params']['podcastInfo']['title'] == 'Older', "a click still sends the episode it names")
    state['allowed'] = False
    recs.send_record_direct({'id': 7, 'itunes_id': 500}, 1001, 'en', older, None)
    _assert(renders and renders[-1][0]['text'] == 'limit', "and a click at the limit still hears why")
    test_apple_link(recs, state, queued, renders)


def test_apple_link(recs, state, queued, renders):
    from app.service.podcast.apple_episode import Episode, Link
    state['allowed'] = True
    found = {'episode': Episode(500, 'g1')}
    recs.apple_episode.find = lambda link: found['episode']
    link = Link(500, 1000000001, 'us')
    _assert(recs.send_apple_episode(link, 1001, 'en') is True, "an Apple episode link queues an episode")
    job = queued[-1]['func_params']
    _assert(job['link'] == 'https://cdn.example/1.mp3' and job['podcastInfo']['title'] == 'Older'
            and job['podcastInfo']['id'] == 7 and queued[-1]['action'] == 'rec',
            "the one with Apple's guid, not the newest, as a click (our channel's id when we have it)")

    found['episode'] = Episode(501, 'g2')
    recs.send_apple_episode(link, 1001, 'en')
    _assert(queued[-1]['func_params']['podcastInfo']['id'] is None
            and queued[-1]['func_params']['podcastInfo']['title'] == 'Newest',
            "a show we do not poll: sent from its feed all the same")

    before, renders[:] = len(queued), []
    found['episode'] = Episode(500, 'not-in-the-feed')
    _assert(recs.send_apple_episode(link, 1001, 'en') is False and len(queued) == before
            and renders and renders[-1][0]['text'] == recs.get_message('notFoundOrFuture', 'en'),
            "a guid our feed does not have: said, nothing queued")
    found['episode'], renders[:] = None, []
    _assert(recs.send_apple_episode(link, 1001, 'en') is False and len(queued) == before
            and renders[-1][0]['text'] == recs.get_message('notFoundOrFuture', 'en'),
            "Apple does not know the episode: said, nothing queued")
    recs.apple_episode.find = lambda link: (_ for _ in ()).throw(RuntimeError('boom'))
    _assert(recs.send_apple_episode(link, 1001, 'en') is False, "an error stays inside")


def main():
    recs = import_builder("recsModule")
    if recs is None:
        return
    test_behaviour(recs)
    print("all latest episode checks passed")


if __name__ == "__main__":
    main()
