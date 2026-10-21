# -*- coding: utf-8 -*-
"""OPML import: the file is read safely (no DTD, a size cap), each feed once;
a feed is matched to a channel we poll (its iTunes id: iTunes-listed
delivery), else to a catalog result with the same feed, else subscribed as
RSS; the free limit names what is over; a feed that fails is named, the
rest go on. The result message part runs where the bot's requirements are
installed.

Run from the repo root: python app/service/podcast/test_opml.py
"""
import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.podcast import opml  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s" % label)


SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Pocket Casts Feeds</title></head>
  <body>
    <outline text="feeds">
      <outline type="rss" text="Known Show" xmlUrl="https://www.Feeds.Example.com/known/" />
      <outline type="rss" title="Catalog Show" xmlUrl="http://catalog.example.org/rss?x=1" />
      <outline type="rss" text="Only RSS &amp; Co" XMLURL="https://rss.example.net/feed.xml" />
      <outline type="rss" text="Known Show again" xmlUrl="http://feeds.example.com/known" />
      <outline type="link" text="A site" htmlUrl="https://example.com" />
      <outline type="rss" text="Not a web feed" xmlUrl="ftp://example.com/feed" />
      <outline type="rss" xmlUrl="https://untitled.example.com/feed" />
    </outline>
  </body>
</opml>"""


def test_parse():
    feeds = opml.parse(SAMPLE)
    _assert_eq([feed.title for feed in feeds],
               ['Known Show', 'Catalog Show', 'Only RSS & Co', 'https://untitled.example.com/feed'],
               "feeds in the file's order, nested too; title from text or title, else the URL")
    _assert_eq(feeds[2].url, 'https://rss.example.net/feed.xml', "attribute names in any case")
    _assert(all(feed.url.startswith('http') for feed in feeds), "only http(s) feeds; links and ftp are not")
    _assert_eq(len(feeds), 4, "the same feed twice (scheme, www, slash, host case) is one")
    for bad, label in ((b'<?xml version="1.0"?><!DOCTYPE lol [<!ENTITY a "aaaa">]><opml><body/></opml>',
                        "a DTD (entity expansion) is refused"),
                       (b'<opml><body><outline xmlUrl="https://a/b"/>', "broken XML is refused"),
                       (b'<rss><channel/></rss>', "a feed is not an OPML file"),
                       (b'<opml>' + b' ' * (opml.MAX_BYTES + 1) + b'</opml>', "past MAX_BYTES is refused")):
        try:
            opml.parse(bad)
        except opml.OpmlError:
            _assert(True, label)
        else:
            raise AssertionError(label)
    _assert_eq(opml.parse(b'<opml><body><outline text="x"/></body></opml>'), [], "no feeds: an empty list")


def test_names():
    _assert_eq(opml.feed_key('HTTPS://www.Example.COM/Path/'), 'example.com/Path', "host case, www, scheme, slash")
    _assert_eq(opml.feed_key('http://example.com/a?b=1'), 'example.com/a?b=1', "the query stays")
    _assert(opml.looks_like_opml('subs.OPML', None), ".opml whatever its type")
    _assert(opml.looks_like_opml('export.xml', 'text/xml'), ".xml as XML")
    _assert(not opml.looks_like_opml('photo.jpg', 'image/jpeg') and not opml.looks_like_opml(None, 'text/xml')
            and not opml.looks_like_opml('a.xml', 'image/svg+xml'), "other documents are not read")


def _known():
    connection = sqlite3.connect(':memory:')
    connection.executescript("""
        CREATE TABLE channels (id INTEGER PRIMARY KEY, itunes_id INTEGER, name TEXT, rss_link TEXT);
        INSERT INTO channels VALUES (21, 160904630, 'Known', 'http://feeds.example.com/known'),
            (22, NULL, 'Rss only', 'https://rss.example.net/feed.xml'), (23, 5, 'No link', NULL);
    """)
    return opml.known_channels(connection)


def test_resolve():
    known = _known()
    searched = []

    def search(term):
        searched.append(term)
        return {'results': [{'collectionId': 777, 'feedUrl': 'https://other.example.org/rss'},
                            {'collectionId': 888, 'feedUrl': 'https://catalog.example.org/rss?x=1'}]}
    feeds = opml.parse(SAMPLE)
    _assert_eq(opml.resolve(feeds[0], known, search), (21, 160904630, 'itunes'),
               "a channel we poll: its iTunes id, no catalog call")
    _assert_eq(searched, [], "and no search for it")
    _assert_eq(opml.resolve(feeds[1], known, search), (None, 888, 'itunes'),
               "else the catalog result with the same feed, not the first one")
    _assert_eq(opml.resolve(feeds[2], known, search), (22, 'https://rss.example.net/feed.xml', 'rss'),
               "a channel we poll without an iTunes id: as RSS")
    _assert_eq(opml.resolve(feeds[3], known, search), (None, 'https://untitled.example.com/feed', 'rss'),
               "no title, no search: as RSS")
    _assert_eq(searched, ['Catalog Show'], "searched by the title only when needed")

    def down(term):
        raise RuntimeError('catalog down')
    _assert_eq(opml.resolve(opml.Feed('Catalog Show', 'http://catalog.example.org/rss?x=1'), {}, down),
               (None, 'http://catalog.example.org/rss?x=1', 'rss'), "the catalog down: the feed itself")


def test_moved():
    """One show at two addresses: the same name and a shared episode, or the file's address gone."""
    known = _known()
    darknet = opml.Feed('Darknet  diaries', 'https://feeds.megaphone.fm/darknetdiaries')
    results = {'results': [{'collectionId': 1296350485, 'collectionName': 'Darknet Diaries',
                            'feedUrl': 'https://podcast.darknetdiaries.com'},
                           {'collectionId': 1815617006, 'collectionName': 'Darknet Diaries en español',
                            'feedUrl': 'https://darknetdiaries.com/es/podcast.xml'}]}
    episodes = {'https://feeds.megaphone.fm/darknetdiaries': {('guid', 'ep-163'), ('title', 'EP 163')},
                'https://podcast.darknetdiaries.com': {('guid', 'ep-163'), ('title', 'EP 163'), ('guid', 'ep-162')}}
    _assert_eq(opml.resolve(darknet, known, lambda term: results, episodes.get), (None, 1296350485, 'itunes'),
               "the one result with that name and a shared episode: its iTunes id")
    known[('itunes', 1296350485)] = (1909, 1296350485)
    _assert_eq(opml.resolve(darknet, known, lambda term: results, episodes.get), (1909, 1296350485, 'itunes'),
               "a channel we poll by that iTunes id is named (the user may have it)")
    other = dict(episodes)
    other['https://feeds.megaphone.fm/darknetdiaries'] = {('guid', 'unrelated')}
    _assert_eq(opml.resolve(darknet, {}, lambda term: results, other.get)[2], 'rss',
               "the same name, no shared episode: another show, the file's feed itself")
    gone = {'https://podcast.darknetdiaries.com': {('guid', 'x')}}
    _assert_eq(opml.resolve(darknet, {}, lambda term: results, gone.get), (None, 1296350485, 'itunes'),
               "the file's address no longer answers: the listed show")
    twice = {'results': results['results'] + [{'collectionId': 5, 'collectionName': 'Darknet Diaries',
                                               'feedUrl': 'https://copy.example.com/rss'}]}
    _assert_eq(opml.resolve(darknet, {}, lambda term: twice, gone.get)[2], 'rss',
               "two shows with that name: neither is guessed")
    root = [type('E', (), {'tag': 'title', 'text': 'Show'})(),
            type('E', (), {'tag': 'item', '__iter__': lambda self: iter([
                type('E', (), {'tag': 'guid', 'text': ' g1 '})(), type('E', (), {'tag': 'title', 'text': 'T1'})()])})()]
    _assert_eq(opml.episode_marks('u', lambda url: root), {('guid', 'g1'), ('title', 'T1')}, "an episode's guid and title")
    _assert_eq(opml.episode_marks('u', lambda url: False), None, "a feed that does not parse: None")

    def raises(url):
        raise RuntimeError('timeout')
    _assert_eq(opml.episode_marks('u', raises), None, "nor one that does not answer")


def test_import():
    feeds = [opml.Feed('Show %d' % i, 'https://f%d.example.com/rss' % i) for i in range(6)]
    known = {opml.feed_key(feeds[0].url): (10, 100), opml.feed_key(feeds[1].url): (11, 101)}
    calls, progress = [], []

    def subscriber(chat_id, channel_id, service_id, service_name):
        calls.append((channel_id, service_id, service_name))
        if service_id == 'https://f3.example.com/rss':
            return None, None  # the feed did not parse
        if service_id == 'https://f4.example.com/rss':
            raise RuntimeError('timeout')
        return 'Name of %s' % service_id, 50 + len(calls)

    no_search = lambda term: {'results': []}  # noqa: E731
    result = opml.import_feeds(1001, feeds, known, {10}, None, subscriber, no_search,
                               progress=lambda n, total: progress.append((n, total)))
    _assert_eq(result.had, ['Show 0'], "a podcast the user has is not subscribed again")
    _assert_eq(result.done, ['Name of 101', 'Name of https://f2.example.com/rss', 'Name of https://f5.example.com/rss'],
               "the others, by the name the subscription gives")
    _assert_eq(result.failed, ['Show 3', 'Show 4'], "a feed that fails, or raises, is named; the rest go on")
    _assert_eq(calls[0], (11, 101, 'itunes'), "a known channel by its iTunes id")
    _assert_eq(progress[0], (1, 6) if progress else None, "progress per feed")

    calls.clear()
    limited = opml.import_feeds(1001, feeds, known, {10}, 2, subscriber, no_search)
    _assert_eq((limited.done, limited.over), (['Name of 101', 'Name of https://f2.example.com/rss'],
                                               ['Show 3', 'Show 4', 'Show 5']),
               "the free limit: the first that fit, the others named, not subscribed")
    _assert_eq(len(calls), 2, "nothing over the limit is fetched")
    _assert_eq(opml.import_feeds(1001, feeds, known, set(), 0, subscriber, no_search).over,
               [feed.title for feed in feeds], "no room: everything is over")

    many = [opml.Feed('S%d' % i, 'https://m%d.example.com/' % i) for i in range(opml.MAX_FEEDS + 5)]
    calls.clear()
    opml.import_feeds(1001, many, {}, set(), None, subscriber, no_search)
    _assert_eq(len(calls), opml.MAX_FEEDS, "at most MAX_FEEDS feeds are imported")


def test_message():
    try:
        from app.controller.builders import opmlModule
    except Exception as e:  # CI has no bot requirements
        print("skip result message (%s)" % e.__class__.__name__)
        return
    from app.i18n.messages import get_message
    message = opmlModule.result_message('en', opml.Result(['Tom &amp; Jerry', 'x < y'], ['C'], ['D'], []))
    _assert('Tom &amp; Jerry, x &lt; y' in message['text'] and 'reply_markup' not in message,
            "names are feed text made safe for HTML; within the limit no plans are sold")
    _assert(get_message('opmlHad', 'en').format(count=1) in message['text'], "what the user had is counted")
    over = opmlModule.result_message('en', opml.Result(['A'], [], [], ['E', 'F']), cut=True)
    tps = [row[0]['callback_data']['tp'] for row in over['reply_markup']]
    _assert('E, F' in over['text'] and tps[:2] == ['bs_stars_pay', 'bs_trfs'],
            "over the free limit: named, Relay's invoice and change-plan")
    _assert(str(opml.MAX_FEEDS) in over['text'], "a cut file says so")
    _assert(opmlModule.result_message('en', opml.Result([], [], [], []))['text']
            == get_message('opmlEmpty', 'en'), "nothing at all: never an empty message")

    states = {1001: {'podcast': {'id': 7, 'subscribed': True}}, 1002: {}}
    saved_storage, saved_add = opmlModule.storage, opmlModule.add_sub

    def add_sub(chat_id, *args):
        states[chat_id]['podcast'] = {'id': 99}  # as add_sub_rss does
        return 'Name', 99
    opmlModule.add_sub = add_sub
    opmlModule.storage = type('S', (), {
        'get_user_state_data': staticmethod(lambda chat_id, name: states[chat_id].get(name)),
        'set_user_state_data': staticmethod(lambda chat_id, name, value: states[chat_id].__setitem__(name, value)),
        'del_user_state_data': staticmethod(lambda chat_id, name: states[chat_id].pop(name, None))})
    try:
        _assert_eq(opmlModule.subscribe_keeping_screen(1001, None, 5, 'itunes'), ('Name', 99), "subscribed")
        _assert_eq(states[1001]['podcast'], {'id': 7, 'subscribed': True},
                   "an open podcast page keeps acting on its own podcast")
        opmlModule.subscribe_keeping_screen(1002, None, 5, 'itunes')
        _assert_eq(states[1002], {}, "no podcast screen before: none after")
    finally:
        opmlModule.storage, opmlModule.add_sub = saved_storage, saved_add

    sent = []
    saved = (opmlModule.outer_sender, opmlModule.threading)
    opmlModule.outer_sender = lambda chat_id, structures: sent.append(structures[0]['text']) or [{'message_id': 5}]

    class NoThread:
        def __init__(self, target, args, **kwargs):
            self.args = args

        def start(self):
            sent.append(('thread', self.args[0], len(self.args[2])))
    opmlModule.threading = type('T', (), {'Thread': NoThread})
    try:
        opmlModule.import_file({'chat_id': 1001, 'language_code': 'en', 'opml': b'not xml'})
        _assert_eq(sent[-1], get_message('opmlBad', 'en'), "an unreadable file: said so, nothing started")
        opmlModule.import_file({'chat_id': 1001, 'language_code': 'en', 'opml': b''})
        _assert_eq(sent[-1], get_message('opmlBad', 'en'), "a file too big to download arrives empty: the same")
        opmlModule.import_file({'chat_id': 1001, 'language_code': 'en', 'opml': SAMPLE})
        _assert_eq(sent[-1], ('thread', 1001, 4), "a good file starts the import off the incoming worker")
        opmlModule.import_file({'chat_id': 1001, 'language_code': 'en', 'opml': SAMPLE})
        _assert_eq(sent[-1], get_message('opmlBusy', 'en'), "one import per chat at a time")
        opmlModule._running.discard(1001)
    finally:
        opmlModule.outer_sender, opmlModule.threading = saved


def main():
    test_parse()
    test_names()
    test_resolve()
    test_moved()
    test_import()
    test_message()
    print("all OPML checks passed")


if __name__ == "__main__":
    main()
