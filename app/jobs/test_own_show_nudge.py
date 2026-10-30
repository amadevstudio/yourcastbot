# -*- coding: utf-8 -*-
"""The own-show nudge: a newcomer with only the welcome show, 1 to 6 hours after
/start, gets one message (even ids; odd ids are the control, only marked). Not
before an hour, not after six, not to a chat with a show of its own, not to a
blocked one, never twice; a send Telegram did not take is marked and not retried.
The message keeps the welcome screen's buttons. Temp DB only.

Run from the repo root: python app/jobs/test_own_show_nudge.py
(the message part runs where the bot's requirements are installed)
"""
import os
import sqlite3
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs import own_show_nudge  # noqa: E402
from app.service import analytics_events  # noqa: E402

WELCOME = own_show_nudge.WELCOME_CHANNEL_ID


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _db(path, now):
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, lang TEXT, deleted_at TEXT,
                            created_at TEXT, flags TEXT);
        CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER, channel_id INTEGER,
                                      notify INTEGER);
    """)

    def joined(hours):
        return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now - hours * 3600))
    users = [
        (5002, 'en', None, joined(2)),     # even, only the welcome show: nudged
        (5003, 'ru', None, joined(2)),     # odd: the control
        (5004, 'en', None, joined(0.5)),   # too early
        (5006, 'en', None, joined(8)),     # too late
        (5008, 'en', None, joined(2)),     # a show of their own
        (5010, 'en', '2026-10-30 10:00:00', joined(2)),  # blocked the bot
        (5012, 'es', None, joined(3)),     # Telegram does not take it
        (-1005, 'en', None, joined(2)),    # a channel
    ]
    c.executemany("INSERT INTO users (telegramId, lang, deleted_at, created_at) VALUES (?, ?, ?, ?)", users)
    c.executemany("INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) VALUES (?, ?, 1)",
                  [(tg, WELCOME) for tg, *_ in users] + [(5008, 77)])
    c.commit()
    c.close()


def _flags(path):
    c = sqlite3.connect(path)
    try:
        return {tg: flag for tg, flag in c.execute(
            "SELECT telegramId, json_extract(flags, '$.own_show_nudge') FROM users")}
    finally:
        c.close()


def test_schedule():
    now = time.time()
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    sent, events = [], []
    saved = own_show_nudge.nudge_message, analytics_events.track
    own_show_nudge.nudge_message = lambda lang, tg, database=None: {'type': 'text', 'text': 'nudge ' + lang}
    analytics_events.track = lambda tg, event, props=None, database=None, **kw: events.append((tg, event, props))

    def telegram(chat_id, messages):
        sent.append((chat_id, messages[0]['text']))
        return [] if chat_id == 5012 else [{'id': 1}]
    try:
        _db(path, now)
        _assert(sorted(tg for tg, _ in own_show_nudge.due(path, now)) == [5002, 5003, 5012],
                "due: joined 1-6 hours ago, only the welcome show, here still, a user")
        _assert(own_show_nudge.send_nudges(path, now, send=telegram) == 1, "one nudge went")
        _assert(sent == [(5002, 'nudge en'), (5012, 'nudge es')], "even ids are sent it, in their language")
        flags = _flags(path)
        _assert((flags[5002], flags[5003], flags[5012]) == ('sent', 'control', 'unsent'),
                "each group is marked: sent, control, unsent")
        _assert(flags[5004] is None and flags[5006] is None and flags[5008] is None and flags[5010] is None,
                "the others are not")
        _assert(sorted((tg, props['group']) for tg, event, props in events if event == 'own_show_nudge')
                == [(5002, 'sent'), (5003, 'control')], "Amplitude hears the sent one and the control")
        del sent[:]
        own_show_nudge.send_nudges(path, now + 600, send=telegram)
        _assert(sent == [], "never twice, and an unsent one is not retried")
    finally:
        own_show_nudge.nudge_message, analytics_events.track = saved
        os.remove(path)


def test_message():
    try:
        from app.controller.builders import onboarding
    except ModuleNotFoundError as e:
        print("skip nudge message (%s)" % e.name)
        return
    top = [{'id': 10 + i, 'name': 'Show %d' % i} for i in range(3)]
    saved = onboarding.picker
    onboarding.picker = lambda lang, chat_id=None, mark=None, count=8, database=None: (top, 42, set())
    try:
        screen = own_show_nudge.nudge_message('en', 5002)
    finally:
        onboarding.picker = saved
    data = [button.get('callback_data') for row in screen['reply_markup'] for button in row]
    _assert(screen['text'].startswith('🎧 What do you listen to?'), "the nudge's text")
    _assert([d['tp'] for d in data[:3]] == ['wPick'] * 3 and data[0]['u'] == 42,
            "the welcome screen's buttons: a tap subscribes, state independent")
    _assert({'tp': 'search'} in data and {'tp': 'menu'} in data, "search and the menu stay")


def main():
    test_schedule()
    test_message()
    print("all own show nudge checks passed")


if __name__ == "__main__":
    main()
