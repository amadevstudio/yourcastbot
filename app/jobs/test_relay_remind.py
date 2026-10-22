# -*- coding: utf-8 -*-
"""D-3 Relay reminder: once per period. Temp DB only.

Run from the repo root: python app/jobs/test_relay_remind.py
"""
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs import relay_remind  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _schema(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegramId INTEGER NOT NULL UNIQUE,
            lang char(15),
            deleted_at TEXT
        );
        CREATE TABLE tariffs (
            id INTEGER PRIMARY KEY,
            level INTEGER NOT NULL,
            price INTEGER NOT NULL,
            notify_count INTEGER NOT NULL
        );
        CREATE TABLE user_tariff_cs (
            id INTEGER PRIMARY KEY,
            uid INTEGER NOT NULL,
            tariff_id INTEGER NOT NULL,
            balance INTEGER,
            notify_count INTEGER,
            time_left INTEGER
        );
    """)
    conn.execute(
        "INSERT INTO tariffs (id, level, price, notify_count) VALUES (3, 3, 500, -1)")
    conn.commit()


def _add_user(conn, telegram_id, time_left, deleted_at=None, lang="en", balance=0, tariff_id=3):
    conn.execute(
        "INSERT INTO users (telegramId, lang, deleted_at) VALUES (?, ?, ?)",
        (telegram_id, lang, deleted_at))
    uid = conn.execute(
        "SELECT id FROM users WHERE telegramId = ?", (telegram_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO user_tariff_cs "
        "(uid, tariff_id, balance, notify_count, time_left) "
        "VALUES (?, ?, ?, -1, ?)",
        (uid, tariff_id, balance, time_left))
    conn.commit()


def _plans(sent):
    """Bronze, Silver and Relay users all expire: each is told about its own plan."""
    from app.i18n.messages import get_message
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        db = SQLighter(path)
        try:
            _schema(db.connection)
            db.connection.execute(
                "INSERT INTO tariffs (id, level, price, notify_count) VALUES (1, 1, 100, 100)")
            db.connection.execute(
                "INSERT INTO tariffs (id, level, price, notify_count) VALUES (2, 2, 300, 500)")
            db.connection.commit()
            _add_user(db.connection, 201, 48, tariff_id=1, lang="ru")
            _add_user(db.connection, 202, 48, tariff_id=2, lang="en")
            _add_user(db.connection, 203, 48, tariff_id=3, lang="en")
            _add_user(db.connection, 204, 48, tariff_id=1, lang="en", balance=100)  # renewed by the tick
        finally:
            db.close()
        del sent[:]
        count = relay_remind.send_relay_d3_reminders(database=path)
        by_user = {row[0]: row for row in sent}
        _assert_eq(count, 3, "Bronze, Silver and Relay users that will expire are reminded")
        _assert_eq(204 in by_user, False, "a Bronze user whose balance renews it is not reminded")
        _assert("«Бронза»" in by_user[201][1] and "Relay заканчивается" not in by_user[201][1],
                "a Bronze user is told Bronze ends, not Relay (ru)")
        _assert('"Silver"' in by_user[202][1] and "Relay ends" not in by_user[202][1],
                "a Silver user is told Silver ends, not Relay (en)")
        _assert_eq(by_user[203][1], get_message("relay_trial_ending", "en") % 2,
                   "the Relay text is exactly what it was")
        for chat_id in (201, 202, 203):
            _assert_eq([row[0]["callback_data"]["tp"] for row in by_user[chat_id][2][:2]], ["bs_stars", "bs_trfs"],
                       "%s: still Stars first, change-plan next to it" % chat_id)
    finally:
        os.remove(path)


def _recap(sent):
    """Under the plan's text, what the plan brought: the Relay text stays as it is, first."""
    import time
    from app.i18n.messages import get_message
    from db import ai, usage
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        db = SQLighter(path)
        try:
            _schema(db.connection)
            db.connection.execute(
                "CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER, "
                "channel_id INTEGER, notify INTEGER)")
            db.connection.executemany(
                "INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) VALUES (?, ?, ?)",
                [(301, 1, 1), (301, 2, 1), (301, 3, 0), (302, 1, 1)])
            db.connection.commit()
            _add_user(db.connection, 301, 48, lang="ru")
            _add_user(db.connection, 302, 48, lang="en")
        finally:
            db.close()
        now = time.time()
        for i in range(3):
            usage.record_deliveries([301], 'circle', 'https://a/%d.mp3' % i, database=path, at=now - 3600)
        usage.record_deliveries([301], 'rec', 'https://a/r.mp3', database=path, at=now - 3600)
        usage.record_deliveries([301], 'rec', 'https://a/old.mp3', database=path, at=now - 40 * 86400)
        done, _ = ai.enqueue(301, 'ep', 'original', 600, database=path)
        ai.finish(done, 'done', database=path)
        failed, _ = ai.enqueue(301, 'ep2', 'original', 600, database=path)
        ai.finish(failed, 'failed', database=path)
        _assert_eq(relay_remind.recap_counts(301, database=path), {'episodes': 4, 'summaries': 1, 'shows': 2},
                   "the last 30 days' episodes, done summaries, podcasts on auto-delivery")

        del sent[:]
        relay_remind.send_relay_d3_reminders(database=path)
        by_user = {row[0]: row[1] for row in sent}
        relay = get_message("relay_trial_ending", "ru") % 2
        _assert(by_user[301].startswith(relay + "\n\n"), "the Relay text stays as it is, first")
        _assert_eq(by_user[301][len(relay) + 2:].split("\n"),
                   [get_message("planRecap", "ru"), "🎧 выпусков в чате: 4", "🎙 подкастов на автодоставке: 2",
                    "📝 ИИ-пересказов: 1"], "then what the plan brought")
        _assert_eq(by_user[302], get_message("relay_trial_ending", "en") % 2,
                   "nothing delivered yet: no recap, the text alone")

        # The ledger started on 2026-10-21: younger than the window, its count is
        # not the user's (a two-week trial read "1 episode"), unless the user is
        # younger still.
        conn = sqlite3.connect(path)
        conn.execute("DELETE FROM usage_events WHERE at < ?", (now - 30 * 86400,))
        conn.execute("UPDATE users SET created_at = datetime(?, 'unixepoch') WHERE telegramId = 301",
                     (now - 10 * 86400,))
        conn.commit()
        conn.close()
        _assert_eq(relay_remind.recap_counts(301, database=path), {'episodes': None, 'summaries': 1, 'shows': 2},
                   "a ledger younger than the window and the user: no episode count")
        _assert_eq(relay_remind.recap_text(301, "ru", database=path).split("\n"),
                   [get_message("planRecap", "ru"), "🎙 подкастов на автодоставке: 2", "📝 ИИ-пересказов: 1"],
                   "the recap goes without the episodes line")
        usage.record_deliveries([302], 'circle', 'https://a/0.mp3', database=path, at=now - 3600)
        _assert_eq(relay_remind.recap_text(302, "en", database=path), "",
                   "no count and no summary: no recap")
        usage.record_deliveries([999], 'rec', 'https://a/x.mp3', database=path, at=now - 5 * 86400)
        conn = sqlite3.connect(path)
        conn.execute("UPDATE users SET created_at = datetime(?, 'unixepoch') WHERE telegramId = 301",
                     (now - 2 * 86400,))
        conn.commit()
        conn.close()
        _assert_eq(relay_remind.recap_counts(301, database=path)['episodes'], 4,
                   "a user who joined after the ledger started: the count is whole")
    finally:
        os.remove(path)


def main():
    _assert_eq(relay_remind.days_left_label(72), 3, "72h is 3 days")
    _assert_eq(relay_remind.days_left_label(25), 1, "25h floors to 1")
    _assert_eq(relay_remind.days_left_label(5), 1, "under a day is still 1")
    _assert_eq(
        relay_remind.should_send_d3(72, False), True, "first entry sends")
    _assert_eq(
        relay_remind.should_send_d3(72, True), False, "already sent skips")
    _assert_eq(
        relay_remind.should_send_d3(80, False), False, "outside window skips")
    _assert_eq(
        relay_remind.should_send_d3(0, False), False, "expired skips")

    sent = []

    def fake_sender(chat_id, messages, **_kwargs):
        sent.append((chat_id, messages[0]["text"], messages[0].get("reply_markup")))
        return True

    relay_remind._send = fake_sender

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        db = SQLighter(path)
        try:
            _schema(db.connection)
            _add_user(db.connection, 101, 50)
            _add_user(db.connection, 102, 200)
            _add_user(db.connection, 103, 10, deleted_at="2026-01-01")
            _add_user(db.connection, 104, 0)
            # balance covers the price (500): the tick renews it, "Relay ends
            # in 2 days, pay $5" would be false
            _add_user(db.connection, 105, 50, balance=31246)
            # short by a cent: will expire, gets the reminder
            _add_user(db.connection, 106, 60, balance=499)
        finally:
            db.close()

        first = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(first, 2, "in-window live users that will expire")
        _assert_eq([row[0] for row in sent], [101, 106], "reminded the in-window users")
        _assert_eq(105 in [row[0] for row in sent], False,
                   "balance covers the renewal: not told Relay ends")
        _assert("Relay" in sent[0][1] or "ends" in sent[0][1].lower()
                or "days" in sent[0][1].lower(),
                "D-3 copy is about Relay ending")
        markup = sent[0][2]
        nudge_types = [row[0]["callback_data"]["tp"] for row in markup[:2]]
        _assert_eq(nudge_types[0], "bs_stars", "D-3 still offers Stars")
        _assert_eq(nudge_types[1], "bs_trfs", "D-3 still offers change-plan")
        _assert("start%3D101" in markup[2][0]["url"],
                "D-3 offers to invite a friend with the user's own link")

        second = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(second, 0, "second hourly tick does not spam")

        relay_remind.clear_relay_d3_sent(101, database=path)
        third = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(third, 1, "renewal clears the flag")
        _assert_eq(sent[-1][0], 101, "and only that user is reminded again")
    finally:
        os.remove(path)

    _plans(sent)
    _recap(sent)
    print("all relay_remind checks passed")


if __name__ == "__main__":
    main()
