# -*- coding: utf-8 -*-
"""The bot end to end in botsim (README.md): a fresh database, no network, a canned AI.

A new user's /start (welcome screen, the welcome plan), the menu and its
settings, the storefront (Stars first, change-plan kept), an OPML file whose
feeds do not answer, and a summary with a question: what the user sees,
through the real handlers, dispatcher and database. Needs the bot's
requirements (skipped where they are not installed, as in CI).

Run from the repo root: python tools/botsim/test_botsim.py
"""
import json
import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import telebot  # noqa: F401
    import telethon  # noqa: F401
except ImportError as e:  # CI has no bot requirements
    print("skip botsim (%s)" % e.__class__.__name__)
    sys.exit(0)

from tools.botsim import sim  # noqa: E402

USER = 1001


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _db():
    return sqlite3.connect(sim._state['database'])


def test_start(user):
    step = user.send('/start')
    _assert(step.handlers[-1] == 'processor(start)' and len(step.new) == 1, "/start: one welcome message")
    _assert(not step.errors, "no error on the way")
    plan = _db().execute("SELECT ut.tariff_id, ut.time_left FROM user_tariff_cs ut JOIN users u ON u.id = ut.uid "
                         "WHERE u.telegramId = ?", (USER,)).fetchone()
    _assert(plan is not None and plan[0] == 3 and plan[1] > 0, "a new user gets the welcome Relay")
    _assert(('start', ) == step.analytics[0][:1], "the tap reaches Amplitude (recorded, not sent)")

    menu = user.tap('menu')
    _assert(menu.edited and any('RSS & Import' in text for text in menu.edited[0].button_texts()),
            "the menu replaces the welcome screen")
    settings = user.tap('Settings')
    _assert(settings.edited and len(settings.edited[0].buttons) >= 2, "settings: a list of sections")


def test_storefront(user):
    step = user.send('/subscription')
    kinds = [json.loads(button['callback_data']).get('tp')
             for row in step.new[0].buttons for button in row if button.get('callback_data')]
    _assert(kinds[:2] == ['bs_stars', 'bs_trfs'], "/subscription: Stars first, change-plan next to it")


def test_opml_offline(user):
    opml = (b'<opml version="2.0"><body>'
            b'<outline type="rss" text="Offline Show" xmlUrl="https://feeds.example.com/offline.xml"/>'
            b'</body></opml>')
    step = user.send_file('subs.opml', opml, 'text/x-opml')
    _assert(step.handlers == ['opml_file (stop)'], "an OPML file is read before the routes, and only there")
    _assert(any('Offline Show' in text for text in step.texts), "a feed that does not answer is named")
    _assert(not step.errors, "and nothing breaks")
    other = user.send_file('photo.jpg', b'\xff\xd8\xff', 'image/jpeg')
    _assert('opml_file (stop)' not in other.handlers, "other documents are not taken for OPML")


def test_summary_and_question(user):
    from db import ai
    ai.remember_episode('simref0000000001', 'https://cdn.example.com/ep.mp3', None, 'Episode One', 'Sim Show',
                        1800)
    step = user.tap_data(json.dumps({'tp': 'sum', 'r': 'simref0000000001'}))
    _assert(step.toasts and step.toasts[0][0], "Summary: the tap is answered at once (it takes minutes)")
    made = user.run_ai()
    _assert(len(made.new) == 1 and sim.FAKE_SUMMARY.splitlines()[0] in made.new[0].text,
            "the jobs process sends the summary")
    _assert(any(button.get('text') for button in made.new[0].buttons[0]), "with its Ask button")
    ask = user.tap((0, 0), message=made.new[0])
    _assert(ask.handlers == ['processor(ask)'] and ask.new, "Ask opens the question screen")
    answer = user.send('Who is the guest?')
    _assert(answer.handlers[-1] == 'processor(ask)' and any(sim.FAKE_ANSWER in text for text in answer.texts),
            "a text there is a question, answered")
    left = _db().execute("SELECT COUNT(*) FROM usage_events WHERE user_id = ? AND kind = 'ask'", (USER,)).fetchone()
    _assert(left[0] == 1, "and counted in the usage ledger")
    done = user.tap('Done')
    _assert(done.handlers == ['action_processor(ask, askDone)'] and done.new, "Done: the menu as a new message")
    again = user.send('Who is the guest?')
    _assert('processor(ask)' not in again.handlers, "after Done a text is no question")


def main():
    sim.boot(network=False, ai='fake')
    try:
        user = sim.BotSim(USER, 'en')
        test_start(user)
        test_storefront(user)
        test_opml_offline(user)
        test_summary_and_question(user)
    finally:
        sim.shutdown()
    print("all botsim checks passed")


if __name__ == '__main__':
    main()
