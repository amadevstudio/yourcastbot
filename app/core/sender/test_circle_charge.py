# -*- coding: utf-8 -*-
"""Circle notify charge: who pays, who is told, and how often.

A channel is billed to its owner; the limit notice goes to the owner's bot
chat, once, on the charge that took the last notification. Real Sender and
real SQLite (temp file), fake Telegram: the stubs come from
test_record_delivery.

Run from the repo root: python app/core/sender/test_circle_charge.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.sender.test_record_delivery import srh  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402
from db.test_count_users import _add_tariff, _add_user, _schema  # noqa: E402

OWNER, CHANNEL_A, CHANNEL_B = 5001, -1005001, -1005002


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


LOGGED = []


class _Logger:
    def log(self, *args):
        LOGGED.append(" ".join(str(arg) for arg in args))

    def err(self, *args):
        raise AssertionError("logged an error: %r" % (args,))


def _db(path, notify_count, lang='en'):
    db = SQLighter(path)
    _schema(db.connection)
    db.connection.executescript("""
        CREATE TABLE IF NOT EXISTS tg_channels (
            id INTEGER PRIMARY KEY, user_id INTEGER, tg_id INTEGER, active INTEGER);
        CREATE TABLE IF NOT EXISTS subscription_to_tg_channel_cs (
            id INTEGER PRIMARY KEY, user_channel_cs_id INTEGER, tg_channel_id INTEGER);
    """)
    for tg_id in (CHANNEL_A, CHANNEL_B):
        db.cursor.execute(
            "INSERT INTO tg_channels (user_id, tg_id, active) VALUES (?, ?, 1)",
            (OWNER, tg_id))
    db.connection.commit()
    uid = _add_user(db, OWNER)
    db.cursor.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, uid))
    db.connection.commit()
    _add_tariff(db, uid, tariff_id=3, time_left=100, notify_count=notify_count)
    db.close()


def _left(path):
    db = SQLighter(path)
    try:
        return db.getUserSubscriptionByTg(OWNER)['notify_count']
    finally:
        db.close()


def _run(path, chats, order, utg_langs=None):
    """Charge `order` through a Sender; returns the (chat, text) notices sent."""
    sent = []
    del LOGGED[:]
    srh.db_path = path
    srh.outer_sender = lambda chat_id, msgs: sent.append((chat_id, msgs[0]['text']))
    srh.get_channel_title = lambda tg_id: 'Show %d' % -tg_id
    sender = object.__new__(srh.Sender)
    sender.logger = _Logger()
    sender._quota_charged, sender._quota_notified = set(), set()
    sender.blocked_chats = set()
    sender.chats = chats
    sender.lang_codes_by_utg = utg_langs or {}
    for chat_id in order:
        sender._charge_circle_notify(chat_id)
    return sent


CHANNELS = {CHANNEL_A: {'based_on_user_id': OWNER}, CHANNEL_B: {'based_on_user_id': OWNER}}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'charge.db')

        _db(path, 1)
        db = SQLighter(path)
        _assert_eq(db.charge_notify_count(OWNER, 1), (True, 0), "the last one is taken")
        _assert_eq(db.charge_notify_count(OWNER, 1), (False, 0), "nothing left to take")
        _assert_eq(db.charge_notify_count(999, 1), (False, None), "no such user")
        db.close()

        path = os.path.join(tmp, 'a.db')
        _db(path, 1)
        sent = _run(path, CHANNELS, [CHANNEL_A, CHANNEL_B])
        _assert_eq(_left(path), 0, "a channel is billed to its owner")
        _assert_eq([chat for chat, _ in sent], [OWNER], "one notice, to the owner's bot chat")
        _assert_eq('Show 1005001' in sent[0][1] and 'Show 1005002' in sent[0][1], True,
                   "the notice names the channel that ran out and lists the others")
        _assert_eq([line.split(" for:")[0] for line in LOGGED if line.startswith("Limit notice")],
                   ["Limit notice sent to: %d" % OWNER], "the notice is in the log")
        _assert_eq([line.split("charged:")[1] for line in LOGGED if line.startswith("Channel delivery")],
                   [" True left: 0", " False left: 0"], "each channel charge is logged, one each")

        path = os.path.join(tmp, 'b.db')
        _db(path, 2)
        sent = _run(path, CHANNELS, [CHANNEL_A, CHANNEL_B])
        _assert_eq((_left(path), len(sent)), (0, 1), "limit 2, two channels: told once, on the last")

        path = os.path.join(tmp, 'c.db')
        _db(path, 3)
        sent = _run(path, CHANNELS, [CHANNEL_A, CHANNEL_B])
        _assert_eq((_left(path), sent), (1, []), "not told while some are left")

        path = os.path.join(tmp, 'd.db')
        _db(path, -1)
        sent = _run(path, CHANNELS, [CHANNEL_A])
        _assert_eq((_left(path), sent), (-1, []), "unlimited stays unlimited and quiet")

        path = os.path.join(tmp, 'e.db')
        _db(path, 1)
        sent = _run(path, {OWNER: {}, CHANNEL_A: {'based_on_user_id': OWNER}}, [OWNER, CHANNEL_A])
        _assert_eq(len(sent), 1, "the owner and a channel in one job: one notice")
        _assert_eq('Show' in sent[0][1], False, "the owner's own delivery gets the short text")

        path = os.path.join(tmp, 'f.db')
        _db(path, 1, lang=None)
        sent = _run(path, CHANNELS, [CHANNEL_A])
        _assert_eq(len(sent), 1, "an owner with no language is still told (English)")
        _assert_eq(sent[0][1].startswith('\U0001F4E2 The notification limit'), True,
                   "the fallback is English")
    print("all circle charge checks passed")


if __name__ == "__main__":
    main()
