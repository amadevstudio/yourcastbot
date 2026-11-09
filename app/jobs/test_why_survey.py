# -*- coding: utf-8 -*-
""""What stops you from taking a plan?": asked once of the chats nearest to paying;
the trials nobody used are asked what got in the way.
A free chat with the week's episodes by click in the last 14 days, and a chat
whose Relay ended two days ago or more and that used the bot itself (one that
only got the welcome show is asked the idle question); not a chat with a plan
running, not a blocked one,
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
from db import tariff_rows  # noqa: E402

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
                            created_at TEXT, flags TEXT, nosub_digest_sent_at TEXT);
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
        (6005, 'en', None),  # Relay ended 3 days ago, only the welcome show's files: asked (idle)
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
    saved = why_survey.survey_message, analytics_events.track, why_survey.why_survey_until, why_survey.why_old_limit
    why_survey.why_old_limit = 0  # the old accounts: test_old
    why_survey.survey_message = lambda lang, tg, database=None, group='ended': {
        'type': 'text', 'text': 'why %s %s' % (lang, group)}
    analytics_events.track = lambda tg, event, props=None, database=None, **kw: events.append((tg, event, props))
    why_survey.why_survey_until = time.strftime('%Y-%m-%d', time.gmtime(now + DAY))

    def telegram(chat_id, messages):
        sent.append((chat_id, messages[0]['text']))
        return chat_id != 6009 and [{'id': 1}]

    try:
        _db(path, now)
        due = {tg: group for tg, _, group in why_survey.due(path, now)}
        _assert(due == {6001: 'limit', 6004: 'ended', 6005: 'idle', 6007: 'ended', 6009: 'limit'},
                "the free chats at the week's cap, the ended trials that used the bot, and the idle ones")
        _assert(why_survey.send_surveys(path, now, send=telegram) == 4, "four got it")
        _assert(sorted(sent) == [(6001, 'why en limit'), (6004, 'why de ended'), (6005, 'why en idle'),
                                 (6007, 'why fa ended'), (6009, 'why pt-BR limit')],
                "in each chat's language, each its group's question")
        flags = _flags(path)
        _assert(flags[6001] == 'sent' and flags[6009] == 'unsent' and flags[6002] is None,
                "marked; the one Telegram did not take is marked unsent")
        _assert(_flags(path, 'why_group')[6005] == 'idle', "with the group it was sent for")
        _assert(sorted(e[2]['group'] for e in events if e[1] == 'survey_sent') == ['ended', 'ended', 'idle', 'limit'],
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
        (why_survey.survey_message, analytics_events.track, why_survey.why_survey_until,
         why_survey.why_old_limit) = saved
        os.remove(path)


def test_old():
    now = time.time()
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    sent, events = [], []
    saved = (why_survey.survey_message, analytics_events.track, why_survey.why_survey_until,
             why_survey.why_old_limit, why_survey.OLD_PER_RUN)
    why_survey.survey_message = lambda lang, tg, database=None, group='ended': {'type': 'text', 'text': group}
    analytics_events.track = lambda tg, event, props=None, database=None, **kw: events.append((tg, event, props))
    why_survey.why_survey_until = time.strftime('%Y-%m-%d', time.gmtime(now + DAY))
    why_survey.why_old_limit, why_survey.OLD_PER_RUN = 4, 3

    def telegram(chat_id, messages):
        sent.append(chat_id)
        return [{'id': 1}]

    def digest(days_ago):
        return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now - days_ago * DAY))
    try:
        c = sqlite3.connect(path)
        c.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, lang TEXT, deleted_at TEXT,
                                created_at TEXT, flags TEXT, nosub_digest_sent_at TEXT);
            CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER, channel_id INTEGER,
                                          notify INTEGER);
            CREATE TABLE usage_events (id INTEGER PRIMARY KEY, at REAL, user_id INTEGER, kind TEXT, ref TEXT);
            CREATE TABLE winback (user_telegram_id INTEGER PRIMARY KEY, ended_at REAL, stage INTEGER DEFAULT 0);
            CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER, notify_count INTEGER);
            CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER, balance INTEGER,
                                         time_left INTEGER, notify_count INTEGER);
            INSERT INTO tariffs VALUES (3, 3, 500, -1);
        """)
        # by row id (newest last): 7101, 7102 (a digest a week ago: the A/B's), 7000 (holdout), 7103, 7104,
        # 7105 (a digest a month ago: old), 7106 (a Relay that ended: the trials' groups, not old), 7107 (blocked),
        # a channel's @name where a chat id goes (an old row: it failed every batch).
        # The adapter backfills a NULL digest time with now (as on the server long ago): old ones have a date.
        c.executemany("INSERT INTO users (telegramId, lang, deleted_at, nosub_digest_sent_at) VALUES (?, 'en', ?, ?)",
                      [(7101, None, digest(400)), (7102, None, digest(7)), (7000, None, digest(400)),
                       (7103, None, digest(400)), (7104, None, digest(400)), (7105, None, digest(30)),
                       (7106, None, digest(400)), (7107, '2026-01-01 00:00:00', digest(400)),
                       ('@somechannel', None, digest(400))])
        c.execute("INSERT INTO winback VALUES (7106, ?, 0)", (now - DAY,))
        c.commit()
        c.close()
        _assert(why_survey.send_surveys(path, now, send=telegram) == 3 and sent == [7105, 7104, 7103],
                "the old accounts, newest first, OLD_PER_RUN an hour; not a digest's, a trial's, a blocked one "
                "or an @name")
        _assert(_flags(path)[7103] == 'sent' and _flags(path, 'why_group')[7103] == 'old', "marked old")
        _assert([e for e in events if e[1] == 'survey_sent'][0][2] == {'group': 'old'}, "counted as old")
        sent.clear()
        why_survey.send_surveys(path, now + 3600, send=telegram)
        _assert(sent == [] and _flags(path)[7000] == 'control' and _flags(path, 'why_group')[7000] == 'old'
                and (7000, 'survey_control', {'group': 'old'}) in events,
                "one in ten (hundreds digit 0) is the holdout: marked, counted, never sent; it fills the cap")
        why_survey.send_surveys(path, now + 7200, send=telegram)
        _assert(sent == [] and _flags(path)[7101] is None, "why_old_limit in all: the pilot stops there")
        c = sqlite3.connect(path)
        c.execute("INSERT INTO users (telegramId, lang, nosub_digest_sent_at) VALUES (7108, 'en', ?)", (digest(400),))
        c.commit()
        c.close()
        why_survey.why_old_limit = 6
        saved_level = tariff_rows.running_plan_level

        def level(chat_id, database=None):
            if chat_id == 7101:
                raise ValueError("a row that cannot be read")
            return saved_level(chat_id, database)
        tariff_rows.running_plan_level = level
        try:
            why_survey.send_surveys(path, now + 10800, send=telegram)
        finally:
            tariff_rows.running_plan_level = saved_level
        _assert(sent == [7108] and _flags(path)[7101] is None,
                "a row the plan check cannot read is skipped, the rest of the batch goes")
        _assert(why_survey.holdout(7000) and why_survey.holdout(123456009)
                and not why_survey.holdout(123456109) and not why_survey.holdout(5551234567), "the holdout digit")
    finally:
        (why_survey.survey_message, analytics_events.track, why_survey.why_survey_until,
         why_survey.why_old_limit, why_survey.OLD_PER_RUN) = saved
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
        _assert([b.get("a") for b in buttons[:5]] == list(why_survey.PAY_ANSWERS) and buttons[0]['tp'] == 'why',
                "a button per reason, the route why")
        _assert(buttons[5]['tp'] == 'bs_stars_pay' and buttons[5].get('o') and buttons[5].get('s') == 'why',
                "a trial that has not spent it gets the first month's offer, tagged as the survey's")
        _assert(buttons[6] == {'tp': 'bs_trfs', 's': 'why'}, "change-plan next to the Relay offer (storefront)")
        _assert('$3.50' in message['text'] and 'what stops you' in message['text']
                and '7 days of Relay' in message['text'], "the question, the gift and the offer")
        again = why_survey.survey_message('ru', 6004, path)
        _assert(len(again['reply_markup']) == 7 and 'план' in again['text'] and '7 дней' in again['text'],
                "in Russian too")
        _assert(len(why_survey.survey_message('en', 6001, path, 'limit')['reply_markup']) in (5, 7),
                "a free chat gets the reasons")
        old = why_survey.survey_message('en', 6002, path, 'old')
        _assert([row[0]['callback_data'].get('a') for row in old['reply_markup'][:5]] == list(why_survey.OLD_ANSWERS)
                and len(old['reply_markup']) == 5
                and 'Why did you stop' in old['text'] and '7 days of Relay' in old['text'],
                "an old account hears what is new and why it stopped, with the gift (search: after the answer)")
        idle = why_survey.survey_message('en', 6005, path, 'idle')
        _assert([row[0]['callback_data']['a'] for row in idle['reply_markup']] == list(why_survey.IDLE_ANSWERS)
                and 'What got in the way' in idle['text'] and '7 days of Relay' in idle['text'],
                "an idle trial is asked what got in the way, with the gift and no offer")
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
        def __init__(self, text, message_id=None):
            self.text, self.message_id = text, message_id

    import db.sqliteAdapter as adapter
    saved = (adapter.SQLighter, module.storage.set_user_state_data, module.storage.get_user_state_data,
             module.storage.add_user_state, module.render_messages, module.send_message_to_creator,
             module.analytics_events.track, module.notify, module.grant_week, module.message_editor,
             module.storage.set_user_message_structures, module.storage.del_user_resend_flag)
    edits, screens, sent_anew = [], {}, []
    module.message_editor = lambda chat, structure, message_id: (
        edits.append(message_id) or renders.append(structure))
    module.storage.set_user_message_structures = lambda chat, value: screens.__setitem__(chat, value)
    module.storage.del_user_resend_flag = lambda chat: None
    gifts = []
    module.grant_week = lambda tg: 0 if tg in gifts else (gifts.append(tg) or 168)
    adapter.SQLighter = FakeDB
    module.storage.set_user_state_data = lambda chat, route, value: state.__setitem__((chat, route), value)
    module.storage.get_user_state_data = lambda chat, route: state.get((chat, route))
    module.storage.add_user_state = lambda chat, route: state.__setitem__((chat, 'current'), route)
    module.render_messages = lambda chat, structures, *a, **k: (
        sent_anew.append(k.get('resending')) or renders.append(structures[0]))
    module.send_message_to_creator = lambda text, level='info': creator.append(text) or True
    module.analytics_events.track = lambda tg, event, props=None, **kw: events.append((event, props))
    module.notify = lambda call, message, text, alert=False: toasts.append(text)
    try:
        tap = {'callback': object(), 'message': Message(None, 55), 'chat_id': 7001, 'language_code': 'en',
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
                and [b['url'] for b in renders[-1]['reply_markup'][0]] == [config.channel_url,
                                                                           config.channel_direct_url]
                and "our channel" in renders[-1]['text']
                and renders[-1]['reply_markup'][1][0]['callback_data'] == {'tp': 'bck'},
                "the answer says the gift and asks for more, the channel to read and to write, and Back")
        _assert(edits == [55] and not sent_anew and screens[7001] == [{'id': 55, 'type': 'text'}],
                "it replaces the tapped question, which becomes the screen Back and search edit")
        module.why_route(dict(tap, united_data={'tp': 'why', 'a': 'own'}))
        _assert('Write it in one message' in renders[-1]['text'] and 'Relay is on' not in renders[-1]['text']
                and events[-1][1]['reward_hours'] == 0, "a second answer: no second gift; 'own' asks for the text")
        flags[(7002, 'why_survey')], flags[(7002, 'why_group')] = 'sent', 'old'
        module.why_route(dict(tap, chat_id=7002, united_data={'tp': 'why', 'a': 'forgot'}))
        _assert('Find your podcast' in renders[-1]['text']
                and renders[-1]['reply_markup'][0][0]['callback_data'] == {'tp': 'search'},
                "an old account's answer: find your podcast, with the search button")
        flags[(7003, 'why_survey')] = 'control'
        _assert(module.why_route(dict(tap, chat_id=7003)) is False, "a holdout's crafted button does nothing")
        module.why_route(dict(tap, united_data={'tp': 'why', 'a': 'find'}))
        _assert('what got in the way' in renders[-1]['text'], "an idle answer asks what got in the way")
        _assert(module.why_route(dict(tap, united_data={'tp': 'why', 'a': 'x'})) is False,
                "an unknown answer is ignored")
        saved_editor = module.message_editor

        def cannot_edit(chat, structure, message_id):
            raise RuntimeError("message to edit not found")
        module.message_editor = cannot_edit
        try:
            module.why_route(dict(tap, united_data={'tp': 'why', 'a': 'find'}))
        finally:
            module.message_editor = saved_editor
        _assert(sent_anew == [True] and 'what got in the way' in renders[-1]['text'],
                "a question that cannot be edited: the answer comes as a new message")
        text = {'callback': None, 'message': Message('Stars are hard to buy in my country <3'), 'chat_id': 7001,
                'language_code': 'en', 'united_data': {}}
        _assert(module.why_route(text) is False and state[(7001, 'current')] == 'menu',
                "the text after it: back at the menu")
        _assert(flags[(7001, 'why_text')] == 'Stars are hard to buy in my country <3'
                and flags[(7001, 'why_text_at')] > 0, "and kept for the admin page")
        _assert(creator[-1].endswith('Stars are hard to buy in my country <3') and '#survey find' in creator[-1],
                "the creator gets the text as it is")
        _assert(events[-1] == ('survey_text', {'answer': 'find', 'chars': 38}), "the text is counted")
        state[(7001, 'why')]['at'] = time.time() - 2 * module.IDLE_SECONDS
        searched = []
        saved_search = module.summaryModule.search_instead
        module.summaryModule.search_instead = lambda data: searched.append(data) or False
        try:
            module.why_route(dict(text, message=Message('Lex Fridman')))
        finally:
            module.summaryModule.search_instead = saved_search
        _assert(searched and len(creator) == 6, "long after the tap a text is a search, not an answer")
    finally:
        (adapter.SQLighter, module.storage.set_user_state_data, module.storage.get_user_state_data,
         module.storage.add_user_state, module.render_messages, module.send_message_to_creator,
         module.analytics_events.track, module.notify, module.grant_week, module.message_editor,
         module.storage.set_user_message_structures, module.storage.del_user_resend_flag) = saved


def main():
    test_schedule()
    test_old()
    test_message()
    test_grant()
    test_answers()
    print("all why survey checks passed")


if __name__ == "__main__":
    main()
