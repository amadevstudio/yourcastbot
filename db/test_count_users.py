# -*- coding: utf-8 -*-
"""count_users /usersCount logic.

Uses a temporary file DB only — never opens production databases.
Run from the repo root: python db/test_count_users.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.sqliteAdapter import SQLighter  # noqa: E402
from app.controller.builders.adminModule import (  # noqa: E402
    format_users_count_message)


def _schema(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            telegramId INTEGER NOT NULL UNIQUE,
            lang char(15),
            bitrate char(7),
            ref_id INTEGER,
            deleted_at TEXT
        );
        CREATE TABLE channels (
            id INTEGER PRIMARY KEY,
            itunes_id INTEGER,
            name TEXT
        );
        CREATE TABLE user_channel_cs (
            id INTEGER PRIMARY KEY,
            user_telegram_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            last_guid TEXT,
            last_date TEXT,
            notify INTEGER
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
    conn.commit()


def _add_user(db, telegram_id, deleted_at=None):
    db.cursor.execute(
        "INSERT INTO users (telegramId, deleted_at) VALUES (?, ?)",
        (telegram_id, deleted_at))
    db.connection.commit()
    return db.cursor.execute(
        "SELECT id FROM users WHERE telegramId = ?",
        (telegram_id,)).fetchone()['id']


def _add_channel(db, channel_id, name="p"):
    db.cursor.execute(
        "INSERT INTO channels (id, itunes_id, name) VALUES (?, ?, ?)",
        (channel_id, channel_id, name))
    db.connection.commit()


def _add_sub(db, telegram_id, channel_id, notify=1):
    db.cursor.execute(
        "INSERT INTO user_channel_cs "
        "(user_telegram_id, channel_id, notify) VALUES (?, ?, ?)",
        (telegram_id, channel_id, notify))
    db.connection.commit()


def _add_tariff(db, uid, tariff_id=3, time_left=100, notify_count=-1):
    db.cursor.execute(
        "INSERT INTO user_tariff_cs "
        "(uid, tariff_id, balance, notify_count, time_left) "
        "VALUES (?, ?, 0, ?, ?)",
        (uid, tariff_id, notify_count, time_left))
    db.connection.commit()


def _counts(db):
    return {
        'total': db.count_users(),
        'with_subs': db.count_users(True),
        'with_subs_notify': db.count_users(with_subs_active=True),
        'payed': db.count_users(payed=True),
        'deleted': db.count_users(deleted=True),
    }


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def test_count_users_cases(db_path):
    db = SQLighter(db_path)
    try:
        _schema(db.connection)

        live_a = _add_user(db, 1001)
        live_b = _add_user(db, 1002)
        live_c = _add_user(db, 1003)
        live_d = _add_user(db, 1004)
        live_e = _add_user(db, 1005)
        blocked_id = _add_user(db, 2001, deleted_at="2026-01-01")

        _add_channel(db, 1)
        _add_channel(db, 7)

        # A: two channel subs, notify on — counted once in both sub lines
        _add_sub(db, 1001, 1, notify=1)
        _add_sub(db, 1001, 7, notify=1)
        # B: channel sub, notify off — in with_subs, not with_subs_notify
        _add_sub(db, 1002, 1, notify=0)
        # blocked user still has a sub — excluded from live lines
        _add_sub(db, 2001, 1, notify=1)

        # A: trial-like unlimited quota (-1) counts as bot subscription
        _add_tariff(db, live_a, tariff_id=3, time_left=334, notify_count=-1)
        # B: quota exhausted — not a bot subscription
        _add_tariff(db, live_b, tariff_id=3, time_left=100, notify_count=0)
        # C: expired time
        _add_tariff(db, live_c, tariff_id=3, time_left=0, notify_count=-1)
        # D: balance-only tariff_id 0
        _add_tariff(db, live_d, tariff_id=0, time_left=100, notify_count=-1)
        # E: duplicate live tariff rows — still one user
        _add_tariff(db, live_e, tariff_id=2, time_left=50, notify_count=10)
        _add_tariff(db, live_e, tariff_id=2, time_left=50, notify_count=10)
        # blocked user with a live tariff — only in deleted
        _add_tariff(db, blocked_id, tariff_id=3, time_left=100, notify_count=-1)

        got = _counts(db)
        _assert_eq(got['total'], 5, "live users")
        _assert_eq(got['with_subs'], 2, "users with channel subs")
        _assert_eq(got['with_subs_notify'], 1, "users with notify-on subs")
        _assert_eq(got['payed'], 2, "users with bot subscription (A and E)")
        _assert_eq(got['deleted'], 1, "blocked users")
        _assert_eq(
            int(db.get_last_channel_id()['id']), 7, "max channel id")
        _assert_eq(
            db.is_user_have_bot_subscription(1001), True,
            "A has bot subscription")
        _assert_eq(
            db.is_user_have_bot_subscription(1002), False,
            "B notify_count=0 is not a bot subscription")
        _assert_eq(
            db.is_user_have_bot_subscription(1005), True,
            "E still has bot subscription despite duplicate rows")
    finally:
        db.close()


def test_mixed_telegram_id_types(db_path):
    db = SQLighter(db_path)
    try:
        db.connection.executescript("""
            CREATE TABLE users (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                telegramId TEXT NOT NULL UNIQUE,
                deleted_at TEXT
            );
            CREATE TABLE user_channel_cs (
                id INTEGER PRIMARY KEY,
                user_telegram_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                notify INTEGER
            );
            CREATE TABLE user_tariff_cs (
                id INTEGER PRIMARY KEY,
                uid INTEGER NOT NULL,
                tariff_id INTEGER NOT NULL,
                notify_count INTEGER,
                time_left INTEGER
            );
        """)
        db.connection.commit()
        db.cursor.execute(
            "INSERT INTO users (telegramId) VALUES (?)", ("1001",))
        db.connection.commit()
        db.cursor.execute(
            "INSERT INTO user_channel_cs "
            "(user_telegram_id, channel_id, notify) VALUES (?, ?, ?)",
            (1001, 1, 1))
        db.connection.commit()
        _assert_eq(db.count_users(True), 1, "TEXT/INTEGER telegram id join")
        _assert_eq(
            db.count_users(with_subs_active=True), 1,
            "TEXT/INTEGER notify join")
    finally:
        db.close()


def test_report_text():
    text = format_users_count_message(5, 2, 1, 2, 1, 3, 7)
    _assert_eq(
        text,
        "Всего: 5\n"
        "С подписками на каналы: 2\n"
        "С подписками и уведомлениями: 1\n"
        "С подпиской на бота: 2\n"
        "Заблокировали бота (не считаются выше): 1\n"
        "Апдейтер каналов: 3 / 7",
        "admin report text")


def test_live_clone_db_still_consistent():
    clone = os.path.join(_ROOT, "db", "yourcast.db")
    if not os.path.exists(clone):
        print("skip live clone db (missing)")
        return
    db = SQLighter(clone)
    try:
        got = _counts(db)
        print("clone db counts:", got)
        if not isinstance(got['total'], int):
            raise AssertionError("count_users must return int")
        last = db.get_last_channel_id()
        max_id = int(last['id']) if last else 0
        print(format_users_count_message(
            got['total'], got['with_subs'], got['with_subs_notify'],
            got['payed'], got['deleted'], 1, max_id))
    finally:
        db.close()


def main():
    test_report_text()
    tmpdir = tempfile.mkdtemp(prefix="yourcast_count_users_")
    test_count_users_cases(os.path.join(tmpdir, "cases.db"))
    test_mixed_telegram_id_types(os.path.join(tmpdir, "mixed.db"))
    test_live_clone_db_still_consistent()
    print("all count_users checks passed")


if __name__ == "__main__":
    main()
