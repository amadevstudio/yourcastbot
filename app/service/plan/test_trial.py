# -*- coding: utf-8 -*-
"""The welcome trial waits for the chat's first show of its own: not the welcome show, once, not over
a running plan, never after a payment; it never fails the subscription. Temp DB, made-up ids.

Run from the repo root: python app/service/plan/test_trial.py (needs the bot's requirements)
"""
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from db.sqliteAdapter import SQLighter  # noqa: E402
except ImportError as e:
    print("skip trial checks (%s)" % e)
    sys.exit(0)
from app.service.plan import trial  # noqa: E402

WELCOME = trial.WELCOME_CHANNEL_ID
WEEKS_2 = 14 * 24


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE, lang TEXT, "
              "ref_id INTEGER, bitrate INTEGER)")
    c.commit()
    c.close()
    db = SQLighter(path)
    db.connection.executescript("""
        CREATE TABLE IF NOT EXISTS tariffs (id INTEGER PRIMARY KEY, level INTEGER,
            price INTEGER, notify_count INTEGER, compression INTEGER, channel_control INTEGER);
        CREATE TABLE IF NOT EXISTS user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER,
            tariff_id INTEGER, balance INTEGER, notify_count INTEGER, time_left INTEGER);
        CREATE TABLE IF NOT EXISTS payment_history (user_id INTEGER, service_type TEXT, invoice_id TEXT,
            invoice_hash TEXT, status TEXT, amount INTEGER, datetime TEXT, charged INTEGER, bundle_back INTEGER);
        INSERT INTO tariffs VALUES (1, 1, 100, 60, 0, 0), (3, 3, 500, -1, 0, 1);
    """)
    for tg in (7301, 7302, 7303, 7304, 7305):
        db.register_new_user(tg, 'en')
        db.subscribeUserToTariffByTg(tg, 0, 0, 0, 0)
        db.set_user_flag(tg, trial.PENDING_FLAG, WEEKS_2)
    db.subscribeUserToTariffByTg(7303, 1, 0, 100, 60)  # a plan runs
    uid = db.cursor.execute("SELECT id FROM users WHERE telegramId = 7304").fetchone()[0]
    db.connection.execute("INSERT INTO payment_history (user_id, service_type, status, amount) "
                          "VALUES (?, 'telegramStars', 'paid', 100)", (uid,))
    db.connection.commit()
    db.close()
    return path


def _plan(path, tg):
    db = SQLighter(path)
    try:
        row = db.getUserSubscriptionByTg(tg)
        return int(row['tariff_id']), int(row['time_left'])
    finally:
        db.close()


def test_start():
    path = _db()
    sent, events = [], []
    from app.service import analytics_events
    saved = trial.notice, analytics_events.track
    trial.notice = lambda tg, hours, lang: {'type': 'text', 'text': 'trial %d %s' % (hours, lang)}
    analytics_events.track = lambda tg, event, props=None, database=None, **kw: events.append((tg, event, props))

    def send(chat_id, messages):
        sent.append((chat_id, messages[0]['text']))
        return [{'id': 1}]
    try:
        _assert(trial.on_subscribed(7301, WELCOME, path, send) is None and _plan(path, 7301) == (0, 0)
                and trial.pending_hours(7301, path) == WEEKS_2, "the welcome show starts nothing")
        _assert(trial.on_subscribed(7301, 77, path, send) == WEEKS_2, "a show of its own starts it")
        _assert(_plan(path, 7301) == (3, WEEKS_2), "Relay for the pending hours")
        _assert(trial.pending_hours(7301, path) is None, "the flag is gone")
        _assert(sent == [(7301, 'trial %d en' % WEEKS_2)], "the chat hears it, in its language")
        _assert(events == [(7301, 'trial_started', {'hours': WEEKS_2, 'trigger': 'own_show'})],
                "Amplitude hears it")
        _assert(trial.on_subscribed(7301, 78, path, send) is None and len(sent) == 1, "only once")
        _assert(trial.on_subscribed(7302, None, path, send) is None and trial.pending_hours(7302, path),
                "no channel id: nothing, the flag stays")
        _assert(trial.on_subscribed(7303, 77, path, send) is None and _plan(path, 7303) == (1, 100)
                and trial.pending_hours(7303, path) == WEEKS_2, "a running plan stays; the trial waits")
        _assert(trial.on_subscribed(7304, 77, path, send) is None and _plan(path, 7304) == (0, 0)
                and trial.pending_hours(7304, path) is None, "a chat that paid gets no trial, the flag goes")
        _assert(trial.on_subscribed(7399, 77, path, send) is None, "no such user: nothing")

        def broken(chat_id, messages):
            raise RuntimeError("telegram is down")
        _assert(trial.on_subscribed(7305, 77, path, broken) is None and _plan(path, 7305) == (3, WEEKS_2),
                "a failed notice never fails the subscription; the trial runs")
    finally:
        trial.notice, analytics_events.track = saved
        os.remove(path)


def test_claim_once():
    path = _db()
    try:
        first, second = SQLighter(path), SQLighter(path)
        try:
            _assert((trial._claim(first, 7302), trial._claim(second, 7302)) == (WEEKS_2, None),
                    "two subscriptions at once claim it once")
        finally:
            first.close()
            second.close()
    finally:
        os.remove(path)


if __name__ == '__main__':
    test_start()
    test_claim_once()
    print("all trial checks passed")
