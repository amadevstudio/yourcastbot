# -*- coding: utf-8 -*-
"""Subscriptions from another podcast app: an OPML file sent to the bot.

Every app exports the list as OPML: <outline> elements whose xmlUrl is a
feed. A feed is subscribed to as the bot would subscribe to it from search:

1. a channel we already poll with that feed (by its address without the
   scheme, "www." and a trailing slash): its iTunes id, so delivery is the
   iTunes-listed one (files over 20 MB are downloaded);
2. else the catalog searched by the outline's title, a result with the same
   feed: its iTunes id;
3. else the one result with exactly that name, when it is the same show at
   another address (apps keep the address they subscribed to: megaphone for
   a show that moved to its own domain, radio-t.com for a feedburner one):
   the two feeds share an episode, or the file's feed no longer answers;
4. else the feed itself, as a typed RSS link is (RSS-only delivery rules).

The free limit is the subscribe screen's (onboarding.subscribe_room): the
first ones that fit, the others named. The file is data from a user: no
DTD or entities, at most MAX_BYTES and MAX_FEEDS.
"""
import re
import xml.etree.ElementTree as ET
from typing import Callable, NamedTuple, Optional

from app.service.podcast import catalog
from lib.tools.logger import logger

MAX_BYTES = 2 * 1024 * 1024
MAX_FEEDS = 100
MARK_EPISODES = 5  # newest episodes compared to tell one show at two addresses
EXTENSIONS = ('.opml', '.xml')
MIME_TYPES = ('text/x-opml', 'text/x-opml+xml', 'application/xml', 'text/xml', 'application/octet-stream')


class OpmlError(Exception):
    pass


class Feed(NamedTuple):
    title: str
    url: str


class Result(NamedTuple):
    done: list
    had: list
    failed: list
    over: list


def looks_like_opml(file_name, mime_type) -> bool:
    """A document the bot should read as OPML (by its name; a mime type alone is too vague)."""
    name = str(file_name or '').lower()
    if name.endswith('.opml'):
        return True
    return name.endswith('.xml') and str(mime_type or '').lower() in MIME_TYPES


def feed_key(url) -> str:
    """A feed's address as the channels table may hold it: no scheme, no "www.", no trailing slash."""
    text = re.sub(r'^[a-z][a-z0-9+.-]*://', '', str(url or '').strip(), flags=re.I)
    host, _, rest = text.partition('/')
    host = host.lower()
    if host.startswith('www.'):
        host = host[4:]
    return (host + ('/' + rest if rest else '')).rstrip('/')


def parse(data: bytes) -> list[Feed]:
    """The feeds of an OPML file, in its order, each once; OpmlError when it is not one."""
    if len(data) > MAX_BYTES:
        raise OpmlError('too big')
    head = data[:4096].lower()
    if b'<!doctype' in head or b'<!entity' in data.lower():
        raise OpmlError('a DTD')
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise OpmlError(str(e))
    if not root.tag.lower().endswith('opml'):
        raise OpmlError('not OPML: <%s>' % root.tag[:40])
    feeds, seen = [], set()
    for element in root.iter():
        if not element.tag.lower().endswith('outline'):
            continue
        attributes = {key.lower(): value for key, value in element.attrib.items()}
        url = (attributes.get('xmlurl') or '').strip()
        if not re.match(r'^https?://\S+$', url, flags=re.I):
            continue
        key = feed_key(url)
        if key in seen:
            continue
        seen.add(key)
        title = (attributes.get('text') or attributes.get('title') or '').strip() or url
        feeds.append(Feed(title[:300], url))
    return feeds


def known_channels(connection) -> dict:
    """{feed key or ('itunes', id): (channel id, iTunes id or None)} of the channels we poll."""
    known = {}
    for row in connection.execute('SELECT id, itunes_id, rss_link FROM channels'):
        if row[2]:
            known[feed_key(row[2])] = (int(row[0]), row[1])
        if row[1]:
            known.setdefault(('itunes', int(row[1])), (int(row[0]), row[1]))
    return known


def _name(text) -> str:
    return ' '.join(str(text or '').casefold().split())


def episode_marks(url, fetch=None) -> Optional[set]:
    """The guids and titles of a feed's newest episodes; None when it does not answer."""
    if fetch is None:
        from app.service.podcast.rss import get_rss_root as fetch
    try:
        root = fetch(url)
    except Exception:
        return None
    if root is None or root is False:
        return None
    marks = set()
    for item in [child for child in root if child.tag == 'item'][:MARK_EPISODES]:
        for child in item:
            if child.tag in ('guid', 'title') and (child.text or '').strip():
                marks.add((child.tag, child.text.strip()))
    return marks


def _itunes(known, item) -> tuple:
    itunes_id = int(item['collectionId'])
    channel = known.get(('itunes', itunes_id)) or known.get(feed_key(item.get('feedUrl')))
    return (channel[0] if channel else None), itunes_id, 'itunes'


def resolve(feed: Feed, known: dict, search: Callable = catalog.search, marks: Callable = episode_marks) -> tuple:
    """(channel id or None, service id, service name) to subscribe to `feed` by."""
    key = feed_key(feed.url)
    channel = known.get(key)
    if channel is not None:
        channel_id, itunes_id = channel
        return (channel_id, int(itunes_id), 'itunes') if itunes_id else (channel_id, feed.url, 'rss')
    if feed.title == feed.url:
        return None, feed.url, 'rss'
    try:
        results = [item for item in search(feed.title).get('results', [])
                   if item.get('collectionId') and item.get('feedUrl')]
    except Exception as e:  # the catalog is down: the feed itself still works
        logger.warn("opml search:", type(e).__name__, e)
        return None, feed.url, 'rss'
    for item in results:
        if feed_key(item['feedUrl']) == key:
            return _itunes(known, item)
    named = [item for item in results if _name(item.get('collectionName')) == _name(feed.title)]
    if len(named) == 1:
        mine = marks(feed.url)
        if mine is None:  # the address in the file is gone; the show is still listed
            return _itunes(known, named[0])
        theirs = marks(named[0]['feedUrl'])
        if mine and theirs and mine & theirs:
            return _itunes(known, named[0])
    return None, feed.url, 'rss'


def import_feeds(chat_id, feeds: list[Feed], known: dict, subscribed: set, room: Optional[int],
                 subscriber: Callable, search: Callable = catalog.search,
                 progress: Optional[Callable] = None, marks: Callable = episode_marks) -> Result:
    """Subscribe `chat_id` to `feeds` in order. `subscribed`: the channel ids it has;
    `room`: how many more it may add (None: unlimited, a running plan)."""
    result = Result([], [], [], [])
    for number, feed in enumerate(feeds[:MAX_FEEDS], 1):
        if progress is not None:
            progress(number, len(feeds[:MAX_FEEDS]))
        try:
            channel_id, service_id, service_name = resolve(feed, known, search, marks)
            if channel_id is not None and channel_id in subscribed:
                result.had.append(feed.title)
                continue
            if room is not None and len(result.done) >= room:
                result.over.append(feed.title)
                continue
            name, new_id = subscriber(chat_id, channel_id, service_id, service_name)
        except Exception as e:  # the feed or the catalog did not answer: name it, go on
            logger.warn("opml subscribe:", feed.url, type(e).__name__, e)
            name = None
        if name is None:
            result.failed.append(feed.title)
        else:
            result.done.append(str(name))
            if new_id is not None:
                subscribed.add(new_id)
    return result
