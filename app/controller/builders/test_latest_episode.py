# -*- coding: utf-8 -*-
"""Right after a subscription the show's newest episode is queued as a click
would queue it: the newest item, counted by the free limit, quiet when it
cannot go (a feed that fails, the limit, several clicks already waiting), and
never failing the subscription. A click on an episode is unchanged.

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
    recs.free_limit.check = lambda chat_id, link, open_links: (state['allowed'], 60)
    recs.free_limit.limit_message = lambda *a: {'type': 'text', 'text': 'limit'}
    recs.render_messages = lambda chat_id, structures, *a, **k: renders.append(structures)

    _assert(recs.send_latest_episode(7, 1001, 'en') is True, "a subscription queues an episode")
    info = queued[-1]['func_params']['podcastInfo']
    _assert(queued[-1]['func_params']['link'] == 'https://cdn.example/2.mp3' and info['title'] == 'Newest'
            and info['recNum'] == 0 and queued[-1]['action'] == 'rec' and queued[-1]['user_id'] == 1001,
            "the newest one, as a click on it (the rec pool, one at a time per chat)")

    state['allowed'] = False
    _assert(recs.send_latest_episode(7, 1001, 'en') is False and not renders,
            "at the free limit: nothing, and no limit message for a gift nobody asked for")
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


def main():
    recs = import_builder("recsModule")
    if recs is None:
        return
    test_behaviour(recs)
    print("all latest episode checks passed")


if __name__ == "__main__":
    main()
