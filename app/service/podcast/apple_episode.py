# -*- coding: utf-8 -*-
"""An episode link from Apple Podcasts: which episode of which show.

Share on an episode in Apple Podcasts gives
`https://podcasts.apple.com/us/podcast/<slug>/id<show>?i=<episode>`. The
link page and search open the show's page from `id<show>`; this finds the
episode's RSS guid, so the episode itself can be sent (asked for 2026-11-07:
share the link, get the file to listen offline).

Apple's lookup does not answer an episode id (`lookup?id=<episode>`: 0
results). It lists a show's newest 200 episodes (`entity=podcastEpisode`,
`limit` past 200 gives 200), each with `trackId` (the `i=`) and
`episodeGuid`. An older one is read from the episode's web page: its
`serialized-server-data` JSON carries the episode's `guid` and the show it
belongs to (`showAdamId`, which can differ from the link's id: Apple
redirects a link to the right show). The page is Apple's own format, not an
API, so it is the fallback; either failing is None, never an exception.
"""
import json
import re
from typing import NamedTuple, Optional

import requests

from app.service.podcast import catalog
from lib.tools.logger import logger

LINK = re.compile(
    r'https?://(?:podcasts|itunes)\.apple\.com/(?:([a-z]{2})/)?\S*?/id(\d+)\S*?[?&]i=(\d+)')
PAGE = 'https://podcasts.apple.com/%s/podcast/id%s?i=%s'
PAGE_DATA = re.compile(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', re.S)


class Link(NamedTuple):
    show_id: int
    episode_id: int
    storefront: str


class Episode(NamedTuple):
    show_id: int
    guid: str


def parse(text) -> Optional[Link]:
    """The show and the episode an Apple Podcasts episode link names, or None."""
    found = LINK.search(str(text or ''))
    if not found:
        return None
    return Link(int(found.group(2)), int(found.group(3)), found.group(1) or 'us')


def _from_lookup(link: Link, get) -> Optional[Episode]:
    for item in catalog.episodes(link.show_id, get):
        if str(item.get('trackId')) == str(link.episode_id) and item.get('episodeGuid'):
            return Episode(int(item.get('collectionId') or link.show_id), str(item['episodeGuid']).strip())
    return None


def _find_guid(node, episode_id: str) -> Optional[str]:
    """The guid inside the first object of the page that is this episode (its id or adamId)."""
    if isinstance(node, dict):
        if str(node.get('id')) == episode_id or str(node.get('adamId')) == episode_id:
            guid = _any_guid(node)
            if guid:
                return guid
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        guid = _find_guid(child, episode_id)
        if guid:
            return guid
    return None


def _any_guid(node) -> Optional[str]:
    if isinstance(node, dict):
        if isinstance(node.get('guid'), str) and node['guid']:
            return node['guid']
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        guid = _any_guid(child)
        if guid:
            return guid
    return None


def from_page(html: str, episode_id: int) -> Optional[Episode]:
    """The episode in an Apple Podcasts episode page, or None (another page, or its format changed)."""
    found = PAGE_DATA.search(html or '')
    if not found:
        return None
    data = json.loads(found.group(1))
    pages = data.get('data') if isinstance(data, dict) else None
    if not isinstance(pages, list):
        return None
    for page in pages:
        intent = page.get('intent') if isinstance(page, dict) else None
        if not isinstance(intent, dict) or str(intent.get('adamId')) != str(episode_id) \
                or not str(intent.get('showAdamId') or '').isdigit():
            continue
        guid = _find_guid(page.get('data'), str(episode_id))
        if guid:
            return Episode(int(intent['showAdamId']), guid.strip())
    return None


def _from_page(link: Link, get) -> Optional[Episode]:
    response = (get or requests.get)(PAGE % (link.storefront, link.show_id, link.episode_id),
                                     timeout=catalog.TIMEOUT, headers=catalog.HEADERS)
    response.raise_for_status()
    return from_page(response.content.decode('utf-8'), link.episode_id)


def find(link: Link, get=None) -> Optional[Episode]:
    """The episode's show and RSS guid: Apple's lookup, else the episode's page; None when neither knows."""
    for name, way in (('lookup', _from_lookup), ('page', _from_page)):
        try:
            episode = way(link, get)
        except Exception as e:
            logger.warn("apple episode", name, "failed:", link.show_id, link.episode_id,
                        type(e).__name__, str(e)[:120])
            continue
        if episode is not None:
            return episode
    return None
