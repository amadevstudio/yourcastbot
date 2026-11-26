# -*- coding: utf-8 -*-
"""A link from iVoox (the podcast platform of Spain and Latin America): which show, which episode.

A Spanish-speaking reader asked for iVoox (2026-11-26). Its shows were in the bot already (180 polled
from iVoox feeds, all in Apple's catalog), but a link from iVoox opened nothing: the link page took
the show's web page for a feed.

- A show's page `https://www.ivoox.com/<slug>_sq_f<show>_1.html`, its feed
  `.../<slug>_fg_f<show>_filtro_1.xml` and the short link `https://go.ivoox.com/sq/<n>` (`f1<n>` in
  the long ones) name the same show; its feed is `feed_fg_f<show>_filtro_1.xml`, whatever the slug.
  A channel we poll from iVoox keeps its own address (`stored_feed`): a feed with another slug is
  the same show.
- An episode's page `.../<slug>-audios-mp3_rf_<episode>_1.html` (or `go.ivoox.com/rf/<episode>`)
  does not name its show: the page does, in its schema.org data (`partOfSeries`), else in its
  "Episodio de" link. The feed lists the episode with that number in its guid
  (`https://www.ivoox.com/<episode>`), link (`_rf_<episode>_`) or file (`_mf_<episode>_`).
Fetching the page is the only network call, through `public_only`; a failure is None, never an
exception.
Lock: python app/service/podcast/test_ivoox.py
"""
import re
from typing import Callable, Iterable, NamedTuple, Optional

from lib.tools.logger import logger

_HOST = r'https?://(?:[\w-]+\.)*ivoox\.com/'
SHOW = re.compile(_HOST + r'\S*?_(?:sq|fg)_f(\d+)', re.I)
SHORT_SHOW = re.compile(r'https?://go\.ivoox\.com/sq/(\d+)', re.I)
EPISODE = re.compile(_HOST + r'\S*?_rf_(\d+)', re.I)
SHORT_EPISODE = re.compile(r'https?://go\.ivoox\.com/rf/(\d+)', re.I)
FEED = 'https://www.ivoox.com/feed_fg_f%s_filtro_1.xml'
PAGE = 'https://www.ivoox.com/episode_rf_%s_1.html'
SERIES = re.compile(r'"partOfSeries"\s*:\s*\{[^}]*?_sq_f(\d+)')
EPISODE_OF = re.compile(r'Episodio de\s*<a href="[^"]*?_sq_f(\d+)')
TIMEOUT = 6
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; podcast bot)'}
MAX_PAGE = 3 * 1024 * 1024


class Link(NamedTuple):
    show: Optional[str]      # the `f<...>` number of the show, None for an episode until its page says
    episode: Optional[str]   # the episode's number, None for a show


def parse(text) -> Optional[Link]:
    """The show or the episode an iVoox link names, or None: not an iVoox link."""
    text = str(text or '').strip()
    for pattern in (EPISODE, SHORT_EPISODE):
        found = pattern.search(text)
        if found:
            return Link(None, found.group(1))
    found = SHOW.search(text)
    if found:
        return Link(found.group(1), None)
    found = SHORT_SHOW.search(text)
    if found:
        return Link('1' + found.group(1), None)
    return None


def feed_url(show: str) -> str:
    return FEED % show


def stored_feed(show: str, feed_keys: Iterable[str]) -> Optional[str]:
    """The address of a channel we poll from this iVoox show (a feed key: no scheme, no www.)."""
    mark = '_fg_f%s_' % show
    for key in feed_keys:
        if isinstance(key, str) and key.lower().startswith('ivoox.com/') and mark in key:
            return 'https://www.' + key
    return None


def _default_get(url):
    from lib.net import public_only
    return public_only.session().get(url, timeout=TIMEOUT, headers=HEADERS)


def show_of_episode(episode: str, get: Callable = None) -> Optional[str]:
    """The show an episode belongs to, read from the episode's page; None when it cannot be."""
    get = get or _default_get
    try:
        response = get(PAGE % episode)
        if response.status_code != 200:
            return None
        text = response.content[:MAX_PAGE].decode('utf-8', 'replace')
    except Exception as e:
        logger.warn("ivoox episode page:", episode, type(e).__name__, e)
        return None
    found = SERIES.search(text) or EPISODE_OF.search(text)
    return found.group(1) if found else None


def episode_guid(root, episode: str) -> Optional[str]:
    """The guid of the feed's item that is this episode (by its number in the guid, link or file)."""
    number = re.compile(r'(?:ivoox\.com/|_rf_|_mf_)%s(?:\D|$)' % re.escape(str(episode)))
    if root is False or root is None:
        return None
    for item in root:
        if item.tag != 'item':
            continue
        guid = link = enclosure = ''
        for child in item:
            if child.tag == 'guid':
                guid = str(child.text or '').strip()
            elif child.tag == 'link':
                link = str(child.text or '').strip()
            elif child.tag == 'enclosure':
                enclosure = str(child.attrib.get('url') or '')
        if guid and any(number.search(value) for value in (guid, link, enclosure)):
            return guid
    return None
