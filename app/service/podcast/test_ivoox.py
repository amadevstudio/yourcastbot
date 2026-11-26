# -*- coding: utf-8 -*-
"""iVoox links (app/service/podcast/ivoox.py): a show's page, feed and short link name its feed;
an episode's page names its show; the feed's item is found by the episode's number.

No network: the episode page is a made-up one shaped as iVoox's. Run from the repo root:
python app/service/podcast/test_ivoox.py
"""
import os
import sys
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.podcast import ivoox  # noqa: E402


def test_parse():
    show = ivoox.Link('1234567', None)
    assert ivoox.parse('https://www.ivoox.com/podcast-some-show_sq_f1234567_1.html') == show
    assert ivoox.parse('  https://ivoox.com/podcast-some-show_sq_f1234567_1.html?utm=x ') == show
    assert ivoox.parse('http://www.ivoox.com/some-show_fg_f1234567_filtro_1.xml') == show
    assert ivoox.parse('https://feeds.ivoox.com/feed_fg_f1234567_filtro_1.xml') == show
    assert ivoox.parse('https://go.ivoox.com/sq/234567') == show  # the short link drops the 1
    episode = ivoox.Link(None, '987654321')
    assert ivoox.parse('https://www.ivoox.com/an-episode-title-audios-mp3_rf_987654321_1.html') == episode
    assert ivoox.parse('https://go.ivoox.com/rf/987654321') == episode
    assert ivoox.parse('Escucha esto: https://www.ivoox.com/x-audios-mp3_rf_987654321_1.html') == episode
    for other in ('https://www.ivoox.com/', 'https://example.com/podcast_sq_f1234567_1.html',
                  'https://podcasts.apple.com/us/podcast/x/id123', 'ivoox', None, ''):
        assert ivoox.parse(other) is None, other
    print("ok  show pages, feeds, short links and episode links; other links are not iVoox")


def test_feeds():
    assert ivoox.feed_url('1234567') == 'https://www.ivoox.com/feed_fg_f1234567_filtro_1.xml'
    keys = ['example.com/feed.xml', 'ivoox.com/other_fg_f17654321_filtro_1.xml',
            'ivoox.com/old-slug_fg_f1234567_filtro_1.xml', ('itunes', 5)]
    assert ivoox.stored_feed('1234567', keys) == 'https://www.ivoox.com/old-slug_fg_f1234567_filtro_1.xml'
    assert ivoox.stored_feed('123456', keys) is None  # a number is matched whole
    assert ivoox.stored_feed('7654321', keys) is None
    print("ok  the feed of a show; a channel polled from it is found whatever its slug")


class _Response:
    def __init__(self, status, text=''):
        self.status_code, self.content = status, text.encode('utf-8')


EPISODE_PAGE = (
    '<html><head><script type="application/ld+json">{"@type":"PodcastEpisode","name":"An episode",'
    '"partOfSeries":{"@type":"PodcastSeries","@id":"https://www.ivoox.com/podcast-a-show_sq_f1234567_1.html#podcast"}}'
    '</script></head><body><a href="/podcast-other_sq_f1999999_1.html">Recommended</a></body></html>')
LINK_ONLY_PAGE = ('<body><a href="/podcast-other_sq_f1999999_1.html">x</a> <span>Episodio de '
                  '<a href="/podcast-a-show_sq_f1234567_1.html" data-v-1>A show</a></span></body>')


def test_show_of_episode():
    asked = []

    def get(answer):
        def fetch(url):
            asked.append(url)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return fetch

    assert ivoox.show_of_episode('987654321', get(_Response(200, EPISODE_PAGE))) == '1234567'
    assert asked == ['https://www.ivoox.com/episode_rf_987654321_1.html'], asked
    assert ivoox.show_of_episode('987654321', get(_Response(200, LINK_ONLY_PAGE))) == '1234567'
    assert ivoox.show_of_episode('987654321', get(_Response(200, '<a href="/x_sq_f1999999_1.html">'))) is None
    assert ivoox.show_of_episode('987654321', get(_Response(404))) is None
    assert ivoox.show_of_episode('987654321', get(TimeoutError('slow'))) is None
    print("ok  an episode's show from its page (schema.org, else 'Episodio de'), recommendations aside")


FEED = '''<rss><channel><title>A show</title>
<item><title>Newest</title><guid>https://www.ivoox.com/987654999</guid>
  <enclosure url="https://www.ivoox.com/newest_mf_987654999_feed_1.mp3"/></item>
<item><title>Ours</title><guid>https://www.ivoox.com/987654321</guid>
  <link>https://www.ivoox.com/ours-audios-mp3_rf_987654321_1.html</link></item>
<item><title>Other guid</title><guid isPermaLink="false">7f3c-uuid</guid>
  <enclosure url="https://www.ivoox.com/other_mf_555_feed_1.mp3"/></item>
<item><title>Longer number</title><guid>https://www.ivoox.com/98765432100</guid></item>
</channel></rss>'''


def test_episode_guid():
    channel = ET.fromstring(FEED).find('channel')
    assert ivoox.episode_guid(channel, '987654321') == 'https://www.ivoox.com/987654321'
    assert ivoox.episode_guid(channel, '555') == '7f3c-uuid'  # the file names it, the guid does not
    assert ivoox.episode_guid(channel, '98765') is None
    assert ivoox.episode_guid(False, '987654321') is None
    print("ok  the feed's item by the episode's number in its guid, link or file")


if __name__ == '__main__':
    test_parse()
    test_feeds()
    test_show_of_episode()
    test_episode_guid()
