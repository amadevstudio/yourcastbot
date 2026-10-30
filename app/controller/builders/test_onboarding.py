# -*- coding: utf-8 -*-
"""Welcome picker: a tap subscribes (a tick is a subscription, a second tap
undoes it), the list does not move when one is ticked, a changed list is not
subscribed to, "Done" only sums up, a button drawn before (a mask of ticks
never subscribed) still subscribes them, the free subscription limit holds,
callbacks fit Telegram's 64 bytes and are read as Telethon sends them
(bytes), names in a script the language does not use stay out; a link from
Apple Podcasts opens that podcast.

Run from the repo root: python app/controller/builders/test_onboarding.py
(the behaviour runs where the bot's requirements are installed).
"""
import json
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.controller.builders.test_open_recs import import_builder  # noqa: E402

TOP = [{'id': 10000 + i, 'name': 'Show <%d> &amp; friends' % i} for i in range(8)]
PERSIAN = {'id': 20000, 'name': 'رادیو کارنکن'}
CHANNELS = {row['id']: {'id': row['id'], 'itunes_id': 500 + i if i % 2 == 0 else None,
                        'rss_link': 'https://feeds.example/%d.xml' % i}
            for i, row in enumerate(TOP)}


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class FakeDB:
    tariff = None
    subs = 0
    rows = {}  # chat -> {channel_id: subscription row id}, for the tap flow

    def __init__(self, *_):
        pass

    def select_top(self, *args):
        # popular among the language's users: a Persian show first; worldwide: nothing new
        return [PERSIAN] + TOP if args[2] else TOP

    def get_uccs_by_tg(self, chat_id, notifications_enabled=True):
        if chat_id in self.rows:
            return [{'id': row_id, 'channel_id': channel_id} for channel_id, row_id in self.rows[chat_id].items()]
        return [{'id': 7, 'channel_id': 10001}] if chat_id == 4002 else []

    def remove_sub(self, chat_id, channel_id, service_id, service_name):
        self.rows.get(chat_id, {}).pop(channel_id, None)

    def getUserSubscriptionByTg(self, chat_id):
        return self.tariff

    def get_uccs_count_by_tg(self, chat_id):
        return self.subs

    def get_channel(self, channel_id):
        return CHANNELS.get(channel_id)

    def close(self):
        pass


def _buttons(screen):
    return [button for row in screen[0]['reply_markup'] for button in row]


def _fake_popular(onboarding):
    onboarding.popular_podcasts = lambda language_code, lang_top, limit, database=None, chat_id=None: \
        FakeDB().select_top(None, language_code, lang_top)


def test_picker(onboarding):
    onboarding.SQLighter = FakeDB
    top = onboarding.top_podcasts('en')
    _assert([row['id'] for row in top] == [row['id'] for row in TOP],
            "the top in the user's language, without a name English readers cannot read")
    _assert(onboarding.top_podcasts('fa')[0]['id'] == PERSIAN['id'], "a language without a script rule keeps it")
    _assert(10001 not in [row['id'] for row in onboarding.top_podcasts('en', 4002)],
            "a podcast the user already has is not offered again")
    _assert(onboarding.readable('Подкаст', 'ru') and onboarding.readable('Lex Fridman', 'ru')
            and not onboarding.readable('رادیو', 'pt-BR') and onboarding.readable('42', 'en')
            and not onboarding.readable('پادکست WonderLand', 'en'),
            "Russian reads Cyrillic and Latin, Portuguese not Arabic, no letters is fine, no mixed names")

    screen = onboarding.welcome_message('en', top, {10000, 10002}, mark=35506)
    _assert('popular channels' not in screen[0]['text'], "one invitation, not two")
    buttons = _buttons(screen)
    picks = [b for b in buttons if b['callback_data']['tp'] == onboarding.PICK_ACTION]
    _assert(len(picks) == 8, "eight podcasts to tick")
    _assert([b['text'].startswith('✅') for b in picks[:3]] == [True, False, True], "ticked ones are marked")
    _assert('<' not in picks[0]['text'] and '&amp;' not in picks[0]['text'], "feed names are plain text")
    _assert(all(len(json.dumps(b['callback_data']).encode()) <= 64 for b in buttons),
            "every callback fits Telegram's 64 bytes")
    tps = [b['callback_data']['tp'] for b in buttons]
    _assert(tps[-3:] == [onboarding.SUBSCRIBE_ACTION, 'search', 'menu'], "subscribe, search and skip stay")
    _assert('(2)' in buttons[8]['text'], "the subscribe button counts the ticked ones")

    index, _, checksum, mark = onboarding.read_tap(json.dumps(picks[1]['callback_data']))
    _assert((index, mark) == (1, 35506), "a tap carries its index and the mark of the screen")
    _assert(checksum == onboarding.list_checksum(top), "and the checksum of the list it was drawn from")
    _assert(onboarding.list_checksum(list(reversed(top))) != checksum, "a reordered list has another checksum")
    _assert(onboarding.read_tap(json.dumps(picks[1]['callback_data']).encode())[::3] == (1, 35506),
            "Telethon's bytes are read the same")
    _assert(onboarding.read_tap('not json') == (None, 0, None, None), "a broken callback selects nothing")
    old = {'tp': onboarding.SUBSCRIBE_ACTION, 'm': 0b101, 'h': checksum}
    _assert(onboarding.read_tap(json.dumps(old))[1:] == (0b101, checksum, None),
            "a button drawn before has no mark: its mask is ticks never subscribed")
    _assert([row['id'] for row in onboarding.picked(top, 0b101)] == [10000, 10002], "mask to podcasts")
    plain = [b['callback_data']['tp'] for b in _buttons(onboarding.welcome_message('en', top, set(), mark=1))]
    _assert(onboarding.SUBSCRIBE_ACTION not in plain and plain[-2:] == ['search', 'menu'],
            "nothing ticked: no \"Done (0)\", search and skip stay")
    big = onboarding.welcome_message('en', top, set(range(10000, 10008)), mark=10 ** 9)
    _assert(all(len(json.dumps(b['callback_data']).encode()) <= 64 for b in _buttons(big)),
            "and with a mark of ten digits")


def test_popular(onboarding):
    """Popular is listeners, not ratings: alive, in Apple's catalog, MIN_LISTENERS+, and the
    chat's own subscriptions do not count (its tick must not move the list)."""
    import sqlite3
    import tempfile
    import time
    recent = time.strftime('%Y-%m-%dT%H:%M:%S+0000', time.gmtime(time.time() - 86400))
    old = time.strftime('%Y-%m-%dT%H:%M:%S+0000', time.gmtime(time.time() - 200 * 86400))
    fd, path = tempfile.mkstemp(suffix='.sqlite')
    os.close(fd)
    try:
        c = sqlite3.connect(path)
        c.executescript("""
            CREATE TABLE users (telegramId INTEGER, lang TEXT, deleted_at TEXT);
            CREATE TABLE channels (id INTEGER, itunes_id INTEGER, name TEXT, last_date TEXT);
            CREATE TABLE user_channel_cs (user_telegram_id INTEGER, channel_id INTEGER, notify INTEGER);
        """)
        c.executemany("INSERT INTO channels VALUES (?, ?, ?, ?)", [
            (1, 11, 'Big', recent), (2, 12, 'Small', recent), (3, None, 'Not listed', recent),
            (4, 14, 'Dead', old), (5, 15, 'Spanish', recent)])
        users = [(100 + i, 'en', None) for i in range(6)] + [(200 + i, 'es', None) for i in range(3)]
        c.executemany("INSERT INTO users VALUES (?, ?, ?)", users + [(300, 'en', '2026-10-01')])
        subs = [(100 + i, 1, 1) for i in range(5)] + [(100 + i, 2, 1) for i in range(3)] \
            + [(100 + i, 3, 1) for i in range(6)] + [(100 + i, 4, 1) for i in range(6)] \
            + [(200 + i, 5, 1) for i in range(3)] + [(105, 2, 0), (300, 2, 1)]
        c.executemany("INSERT INTO user_channel_cs VALUES (?, ?, ?)", subs)
        c.commit()
        c.close()
        _assert([r['name'] for r in onboarding.popular_podcasts('en', True, 8, path)] == ['Big', 'Small'],
                "by listeners; not listed, dead, muted and blocked listeners left out")
        _assert([r['name'] for r in onboarding.popular_podcasts('es', True, 8, path)] == ['Spanish'],
                "in the user's language")
        _assert([r['name'] for r in onboarding.popular_podcasts('es', False, 8, path)] == ['Big', 'Small', 'Spanish'],
                "worldwide: everyone's")
        _assert([r['name'] for r in onboarding.popular_podcasts('en', True, 8, path, chat_id=100)] == ['Big'],
                "the chat's own subscriptions do not count: Small falls under the minimum without it")
    finally:
        os.remove(path)


def test_ticks_are_subscriptions(onboarding):
    """The list stays put when a tick subscribes: rows up to the mark are what the chat had."""
    onboarding.SQLighter = FakeDB
    FakeDB.rows = {4003: {10001: 40}}
    top, mark, ticked = onboarding.picker('en', 4003)
    _assert(mark == 40 and 10001 not in [row['id'] for row in top] and ticked == set(),
            "drawn: what the chat had stays out, the mark is its newest subscription")
    FakeDB.rows[4003][10003] = 41  # the tap on Show 3 subscribed
    again, mark2, ticked2 = onboarding.picker('en', 4003, mark)
    _assert(onboarding.list_checksum(again) == onboarding.list_checksum(top) and mark2 == 40 and ticked2 == {10003},
            "the next tap sees the same list, the new subscription ticked")
    _assert(10003 not in [row['id'] for row in onboarding.picker('en', 4003)[0]],
            "/start again: it is something the chat has, and new ones are offered")
    onboarding.unsubscribe(4003, {'id': 10003})
    _assert(onboarding.picker('en', 4003, mark)[2] == set(), "a second tap unsubscribes: the tick goes")
    FakeDB.rows = {}


def test_subscribe(onboarding):
    onboarding.SQLighter = FakeDB
    calls = []

    def subscriber(chat_id, channel_id, service_id, service_name):
        calls.append((channel_id, service_id, service_name))
        return (None, None) if channel_id == 10002 else ('name', channel_id)

    FakeDB.tariff, FakeDB.subs = None, onboarding.max_subscriptions_without_tariff - 3
    done, failed, over = onboarding.subscribe(4001, TOP[:5], subscriber=subscriber)
    _assert(calls[0] == (10000, 500, 'itunes') and calls[1] == (10001, 'https://feeds.example/1.xml', 'rss'),
            "iTunes podcasts by their id, the others by their feed")
    _assert(failed == ['Show  & friends'], "a failed one is named, as plain text")
    _assert(len(done) == 3 and len(over) == 1, "a free user stops at the subscription limit")

    calls.clear()
    FakeDB.tariff = {'tariff_id': 3, 'time_left': 100}
    done, failed, over = onboarding.subscribe(4001, TOP, subscriber=subscriber)
    _assert(len(calls) == 8 and over == [], "a running plan has no subscription limit")
    def silent_itunes(chat_id, channel_id, service_id, service_name):
        if channel_id == 10000:
            raise AttributeError("'NoneType' object has no attribute 'content'")  # iTunes did not answer
        return 'name', channel_id

    done, failed, over = onboarding.subscribe(4001, TOP[:2], subscriber=silent_itunes)
    _assert(len(failed) == 1 and len(done) == 1, "a podcast that fails to answer is named; the rest go on")
    text = onboarding.result_message('en', ['A & B'], [], [])[0]['text']
    _assert('A &amp; B' in text, "names are escaped in the result")


def test_apple_link(search):
    _assert(search.apple_podcast_id('https://podcasts.apple.com/us/podcast/ted-talks-daily/id160904630')
            == 160904630, "an Apple Podcasts link gives its iTunes id")
    _assert(search.apple_podcast_id('look https://podcasts.apple.com/de/podcast/x/id42?i=1000 ok') == 42,
            "inside text, with an episode parameter")
    _assert(search.apple_podcast_id('ted talks') is None, "a plain query is a search")


def test_taps_reach_the_handler(welcome):
    """A welcome button is routed as 'start': it must not be read as a /start link."""
    called = []
    saved = (welcome.referral_processing, welcome.action_processing)
    welcome.referral_processing = lambda *args: called.append('referral') or (False, False)
    welcome.action_processing = lambda *args: called.append('action')
    try:
        tap = {'route_name': 'start', 'callback': object(),
               'message': types.SimpleNamespace(text='Welcome!\nTick the podcasts you like')}
        _assert(welcome.start_related_options(tap)['action'] is None and called == [],
                "a tap goes to its handler: the bot's text is no /start parameter")
        command = {'route_name': 'start', 'callback': None, 'message': types.SimpleNamespace(text='/start podcast_5')}
        _assert(welcome.start_related_options(command)['action'] == 'podcast', "a /start link still opens its podcast")
        called.clear()
        welcome.referral_processing = lambda *args: called.append(args[3]) or (True, False)
        launch = {'route_name': 'start', 'callback': None, 'message': types.SimpleNamespace(text='/start src_PH')}
        options = welcome.start_related_options(launch)
        _assert(options['action'] is None and options['source'] == 'ph' and called[0] == 'ph',
                "a source link is no action (the /start screen runs) and its source reaches the sign-up")
        _assert(welcome.link_source('src_') is None and welcome.link_source('src_a b') is None
                and welcome.link_source('podcast_5') is None and welcome.link_source('src_' + 'x' * 33) is None,
                "anything else is not a source")
    finally:
        welcome.referral_processing, welcome.action_processing = saved


def main():
    onboarding = import_builder("onboarding")
    if onboarding is None:
        return
    test_popular(onboarding)
    _fake_popular(onboarding)
    test_picker(onboarding)
    test_ticks_are_subscriptions(onboarding)
    test_subscribe(onboarding)
    welcome = import_builder("welcomeModule")
    if welcome is not None:
        test_taps_reach_the_handler(welcome)
    search = import_builder("searchModule")
    if search is not None:
        test_apple_link(search)
    print("all onboarding checks passed")


if __name__ == "__main__":
    main()
