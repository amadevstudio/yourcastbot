# -*- coding: utf-8 -*-
"""D-3 Relay reminder: once per period. Temp DB only.

Run from the repo root: python app/jobs/test_relay_remind.py
"""
import os
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


def _add_user(conn, telegram_id, time_left, deleted_at=None, lang="en"):
    conn.execute(
        "INSERT INTO users (telegramId, lang, deleted_at) VALUES (?, ?, ?)",
        (telegram_id, lang, deleted_at))
    uid = conn.execute(
        "SELECT id FROM users WHERE telegramId = ?", (telegram_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO user_tariff_cs "
        "(uid, tariff_id, balance, notify_count, time_left) "
        "VALUES (?, 3, 0, -1, ?)",
        (uid, time_left))
    conn.commit()


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
        finally:
            db.close()

        first = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(first, 1, "only the in-window live user")
        _assert_eq(sent[0][0], 101, "reminded the in-window user")
        _assert("Relay" in sent[0][1] or "ends" in sent[0][1].lower()
                or "days" in sent[0][1].lower(),
                "D-3 copy is about Relay ending")
        nudge_types = [row[0]["callback_data"]["tp"] for row in sent[0][2]]
        _assert_eq(nudge_types[0], "bs_stars", "D-3 still offers Stars")
        _assert_eq(nudge_types[1], "bs_trfs", "D-3 still offers change-plan")

        second = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(second, 0, "second hourly tick does not spam")

        relay_remind.clear_relay_d3_sent(101, database=path)
        third = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(third, 1, "renewal clears the flag")
    finally:
        os.remove(path)

    print("all relay_remind checks passed")


if __name__ == "__main__":
    main()
