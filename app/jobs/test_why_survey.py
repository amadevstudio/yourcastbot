# -*- coding: utf-8 -*-
""""What stops you from taking a plan?": asked once of the chats nearest to paying.
A free chat with the week's episodes by click in the last 14 days, and a chat
whose Relay ended two days ago or more and that used the bot itself; not a chat
with a plan running, not one that only got the welcome show, not a blocked one,
not the creator, never twice, not a chat whose balance would renew Relay, and only
until why_survey_until. A send Telegram did not take is marked and not
retried. The message has a button per reason, the week's gift and, for a
trial that has not spent it, the offer with change-plan. The first answer of
a chat the survey reached gives the week of Relay, once; a crafted button
does nothing. An answer is kept, counted and sent to the creator; the text
after it goes to the creator as it is.
Temp DB only.

Run from the repo root: python app/jobs/test_why_survey.py
(the message and answer parts run where the bot's requirements are installed)
"""
import os
import sqlite3
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402
from app.jobs import why_survey  # noqa: E402
from app.service import analytics_events  # noqa: E402

WELCOME = why_survey.WELCOME_CHANNEL_ID
DAY = 86400


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
        CREATE TABLE usage_events (id INTEGER PRIMARY KEY, at REAL, user_id INTEGER, kind TEXT, ref TEXT,
                                   mb REAL DEFAULT 0, cost_usd REAL DEFAULT 0);
        CREATE TABLE winback (user_telegram_id INTEGER PRIMARY KEY, ended_at REAL, stage INTEGER DEFAULT 0);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER, notify_count INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER, balance INTEGER,
                                     time_left INTEGER, notify_count INTEGER);
        INSERT INTO tariffs VALUES (1, 1, 100, 60), (2, 2, 200, 400), (3, 3, 500, -1);
    """)
    users = [
        (6001, 'en', None),  # free, ten episodes in 14 days: asked (limit)
        (6002, 'ru', None),  # free, nine: not
        (6003, 'es', None),  # ten episodes, but a plan running: not
        (6004, 'de', None),  # Relay ended 3 days ago, a show of their own: asked (ended)
        (6005, 'en', None),  # Relay ended 3 days ago, only the welcome show's files: not
        (6006, 'en', None),  # Relay ended yesterday, clicked: not yet
        (6007, 'fa', None),  # Relay ended 5 days ago, asked for a summary: asked (ended)
        (6008, 'en', '2026-11-01 10:00:00'),  # blocked, ten episodes: not
        (6009, 'pt-BR', None),  # Telegram does not take it: marked, not retried
        (6010, 'en', None),  # ten episodes, but $6 on the balance: the tick would renew the gift, not asked
        (int(config.creatorId), 'ru', None),  # the creator: never
    ]
    c.executemany("INSERT INTO users (telegramId, lang, deleted_at) VALUES (?, ?, ?)", users)
    c.executemany("INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) VALUES (?, ?, 1)",
                  [(tg, WELCOME) for tg, *_ in users] + [(6004, 77)])

    def clicks(tg, n, days_ago=3):
        c.executemany("INSERT INTO usage_events (at, user_id, kind, ref) VALUES (?, ?, 'rec', ?)",
                      [(now - days_ago * DAY - i, tg, 'ep%d' % i) for i in range(n)])
    clicks(6001, 10)
    clicks(6001, 5, days_ago=20)  # older ones do not count
    clicks(6002, 9)
    clicks(6003, 10)
    clicks(6006, 1)
    clicks(6008, 10)
    clicks(6009, 10)
    clicks(6010, 10)
    clicks(int(config.creatorId), 10)
    c.execute("INSERT INTO usage_events (at, user_id, kind, ref) VALUES (?, 6007, 'ai', 'x')", (now - 9 * DAY,))
    c.execute("INSERT INTO usage_events (at, user_id, kind, ref) VALUES (?, 6005, 'circle', 'x')", (now - 9 * DAY,))
    c.executemany("INSERT INTO winback (user_telegram_id, ended_at) VALUES (?, ?)",
                  [(6004, now - 3 * DAY), (6005, now - 3 * DAY), (6006, now - DAY), (6007, now - 5 * DAY)])
    c.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, time_left) "
              "SELECT id, 3, 0, 100 FROM users WHERE telegramId = 6003")
    c.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, time_left) "
              "SELECT id, 0, 600, 0 FROM users WHERE telegramId = 6010")
    c.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, time_left) "
              "SELECT id, 0, 114, 332 FROM users WHERE telegramId = 6001")
    c.commit()
    c.close()


def _flags(path, key='why_survey'):
    c = sqlite3.connect(path)
    try:
        return {tg: flag for tg, flag in c.execute(
            "SELECT telegramId, json_extract(flags, '$.%s') FROM users" % key)}
    finally:
        c.close()


def test_schedule():
    now = time.time()
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    sent, events = [], []
    saved = why_survey.survey_message, analytics_events.track, why_survey.why_survey_until
    why_survey.survey_message = lambda lang, tg, database=None: {'type': 'text', 'text': 'why ' + lang}
    analytics_events.track = lambda tg, event, props=None, database=None, **kw: events.append((tg, event, props))
    why_survey.why_survey_until = time.strftime('%Y-%m-%d', time.gmtime(now + DAY))

    def telegram(chat_id, messages):
        sent.append((chat_id, messages[0]['text']))
        return chat_id != 6009 and [{'id': 1}]

    try:
        _db(path, now)
        due = {tg: group for tg, _, group in why_survey.due(path, now)}
        _assert(due == {6001: 'limit', 6004: 'ended', 6007: 'ended', 6009: 'limit'},
                "the free chats at the week's cap and the ended trials that used the bot are due")
        _assert(why_survey.send_surveys(path, now, send=telegram) == 3, "three got it")
        _assert(sorted(sent) == [(6001, 'why en'), (6004, 'why de'), (6007, 'why fa'), (6009, 'why pt-BR')],
                "in each chat's language")
        flags = _flags(path)
        _assert(flags[6001] == 'sent' and flags[6009] == 'unsent' and flags[6002] is None,
                "marked; the one Telegram did not take is marked unsent")
        _assert(sorted(e[2]['group'] for e in events if e[1] == 'survey_sent') == ['ended', 'ended', 'limit'],
                "each send is counted with its group")
        sent.clear()
        _assert(why_survey.send_surveys(path, now + 600, send=telegram) == 0 and not sent,
                "never twice, an unsent one not retried")
        c = sqlite3.connect(path)
        c.execute("INSERT INTO winback (user_telegram_id, ended_at) VALUES (6002, ?)", (now - 3 * DAY,))
        c.commit()
        c.close()
        why_survey.why_survey_until = time.strftime('%Y-%m-%d', time.gmtime(now - DAY))
        _assert(why_survey.send_surveys(path, now, send=telegram) == 0 and not sent,
                "after why_survey_until nobody new is asked")
    finally:
        why_survey.survey_message, analytics_events.track, why_survey.why_survey_until = saved
        os.remove(path)


def test_message():
    try:
        from app.i18n.messages import get_message  # noqa: F401
        from db import sqliteAdapter  # noqa: F401
    except Exception as e:  # CI has no bot requirements
        print("skip  message (%s)" % e.__class__.__name__)
        return
    now = time.time()
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        _db(path, now)
        c = sqlite3.connect(path)
        c.executescript("CREATE TABLE payment_history (user_id INTEGER, service_type TEXT, invoice_id TEXT, "
                        "invoice_hash TEXT, status TEXT, amount INTEGER, datetime TEXT);")
        c.commit()
        c.close()
        message = why_survey.survey_message('en', 6004, path)
        buttons = [row[0]['callback_data'] for row in message['reply_markup']]
        _assert([b.get('a') for b in buttons[:5]] == list(why_survey.ANSWERS) and buttons[0]['tp'] == 'why',
                "a button per reason, the route why")
        _assert(buttons[5]['tp'] == 'bs_stars_pay' and buttons[5].get('o') and buttons[5].get('s') == 'why',
                "a trial that has not spent it gets the first month's offer, tagged as the survey's")
        _assert(buttons[6] == {'tp': 'bs_trfs', 's': 'why'}, "change-plan next to the Relay offer (storefront)")
        _assert('$3.50' in message['text'] and 'what stops you' in message['text']
                and '7 days of Relay' in message['text'], "the question, the gift and the offer")
        again = why_survey.survey_message('ru', 6004, path)
        _assert(len(again['reply_markup']) == 7 and 'план' in again['text'] and '7 дней' in again['text'],
                "in Russian too")
        _assert(len(why_survey.survey_message('en', 6001, path)['reply_markup']) in (5, 7),
                "a free chat gets the reasons")
    finally:
        os.remove(path)


def _plan(path, tg):
    c = sqlite3.connect(path)
    try:
        return c.execute("SELECT ut.tariff_id, ut.balance, ut.time_left, ut.notify_count FROM user_tariff_cs ut "
                         "JOIN users u ON u.id = ut.uid WHERE u.telegramId = ?", (tg,)).fetchone()
    finally:
        c.close()


def test_grant():
    now = time.time()
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        _db(path, now)
        _assert(why_survey.grant_week(6001, path, now) == 0, "not asked: no gift")
        c = sqlite3.connect(path)
        c.execute("UPDATE users SET flags = json_object('why_survey', 'sent') "
                  "WHERE telegramId IN (6001, 6003, 6004)")
        c.execute("UPDATE users SET flags = json_object('why_survey', 'unsent') WHERE telegramId = 6009")
        c.commit()
        c.close()
        _assert(why_survey.grant_week(6001, path, now) == 168 and _plan(path, 6001) == (3, 114, 168, -1),
                "a free chat gets Relay for the week, its balance stays")
        _assert(why_survey.grant_week(6001, path, now) == 0 and _plan(path, 6001) == (3, 114, 168, -1),
                "once")
        _assert(why_survey.grant_week(6003, path, now) == 168 and _plan(path, 6003)[2] == 268,
                "a running plan gets the hours on top")
        _assert(why_survey.grant_week(6004, path, now) == 168 and _plan(path, 6004) == (3, 0, 168, -1),
                "a chat with no tariff row gets one")
        _assert(why_survey.grant_week(6009, path, now) == 0, "a survey Telegram did not take: no gift")
        _assert(_flags(path, 'why_reward')[6001] == int(now), "the gift is marked")
    finally:
        os.remove(path)


def test_answers():
    try:
        from app.controller.builders import whySurveyModule as module
    except Exception as e:  # CI has no bot requirements
        print("skip  answers (%s)" % e.__class__.__name__)
        return
    state, flags, creator, renders, events, toasts = {}, {}, [], [], [], []

    class FakeDB:
        def __init__(self, *_):
            pass

        def set_user_flag(self, tg, name, value=1):
            flags[(tg, name)] = value

        def get_user_flag(self, tg, name):
            return flags.get((tg, name))

        def close(self):
            pass

    class Message:
        def __init__(self, text):
            self.text = text

    import db.sqliteAdapter as adapter
    saved = (adapter.SQLighter, module.storage.set_user_state_data, module.storage.get_user_state_data,
             module.storage.add_user_state, module.render_messages, module.send_message_to_creator,
             module.analytics_events.track, module.notify, module.grant_week)
    gifts = []
    module.grant_week = lambda tg: 0 if tg in gifts else (gifts.append(tg) or 168)
    adapter.SQLighter = FakeDB
    module.storage.set_user_state_data = lambda chat, route, value: state.__setitem__((chat, route), value)
    module.storage.get_user_state_data = lambda chat, route: state.get((chat, route))
    module.storage.add_user_state = lambda chat, route: state.__setitem__((chat, 'current'), route)
    module.render_messages = lambda chat, structures, *a, **k: renders.append(structures[0])
    module.send_message_to_creator = lambda text, level='info': creator.append(text) or True
    module.analytics_events.track = lambda tg, event, props=None, **kw: events.append((event, props))
    module.notify = lambda call, message, text, alert=False: toasts.append(text)
    try:
        tap = {'callback': object(), 'message': None, 'chat_id': 7001, 'language_code': 'en',
               'united_data': {'tp': 'why', 'a': 'pay'}}
        _assert(module.why_route(tap) is False and not events and not creator,
                "a chat the survey did not go to: a crafted button does nothing")
        flags[(7001, 'why_survey')] = 'sent'
        _assert(module.why_route(tap) is None, "a reason's tap opens the route (its state is set)")
        _assert(flags[(7001, 'why_answer')] == 'pay'
                and events[-1] == ('survey_answer', {'answer': 'pay', 'reward_hours': 168}),
                "the answer is kept and counted, with the gift")
        _assert('#survey pay (en) from 7001, +7 d of Relay' in creator[-1], "and sent to the creator")
        _assert('Relay is on for you for 7 days' in renders[-1]['text'] and 'a few words' in renders[-1]['text']
                and renders[-1]['reply_markup'][0][0]['url'] == config.channel_direct_url
                and renders[-1]['reply_markup'][1][0]['callback_data'] == {'tp': 'bck'},
                "a new message says the gift and asks for more, the channel's messages and Back")
        module.why_route(dict(tap, united_data={'tp': 'why', 'a': 'own'}))
        _assert('Write it in one message' in renders[-1]['text'] and 'Relay is on' not in renders[-1]['text']
                and events[-1][1]['reward_hours'] == 0, "a second answer: no second gift; 'own' asks for the text")
        _assert(module.why_route(dict(tap, united_data={'tp': 'why', 'a': 'x'})) is False,
                "an unknown answer is ignored")
        text = {'callback': None, 'message': Message('Stars are hard to buy in my country <3'), 'chat_id': 7001,
                'language_code': 'en', 'united_data': {}}
        _assert(module.why_route(text) is False and state[(7001, 'current')] == 'menu',
                "the text after it: back at the menu")
        _assert(creator[-1].endswith('Stars are hard to buy in my country <3') and '#survey own' in creator[-1],
                "the creator gets the text as it is")
        _assert(events[-1] == ('survey_text', {'answer': 'own', 'chars': 38}), "the text is counted")
        state[(7001, 'why')]['at'] = time.time() - 2 * module.IDLE_SECONDS
        searched = []
        saved_search = module.summaryModule.search_instead
        module.summaryModule.search_instead = lambda data: searched.append(data) or False
        try:
            module.why_route(dict(text, message=Message('Lex Fridman')))
        finally:
            module.summaryModule.search_instead = saved_search
        _assert(searched and len(creator) == 3, "long after the tap a text is a search, not an answer")
    finally:
        (adapter.SQLighter, module.storage.set_user_state_data, module.storage.get_user_state_data,
         module.storage.add_user_state, module.render_messages, module.send_message_to_creator,
         module.analytics_events.track, module.notify, module.grant_week) = saved


def main():
    test_schedule()
    test_message()
    test_grant()
    test_answers()
    print("all why survey checks passed")


if __name__ == "__main__":
    main()
