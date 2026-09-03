# -*- coding: utf-8 -*-
"""Channel poll iterator + HTTP validator columns.

Uses a temporary file DB only — never opens production databases.
Run from the repo root: python db/test_channel_poll.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db import sqliteAdapter  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _schema(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            telegramId INTEGER NOT NULL UNIQUE,
            lang char(15),
            deleted_at TEXT
        );
        CREATE TABLE channels (
            id INTEGER PRIMARY KEY,
            itunes_id INTEGER,
            name TEXT,
            rss_link TEXT,
            last_guid TEXT,
            last_date TEXT,
            http_etag TEXT,
            http_last_modified TEXT
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
        CREATE TABLE tariffs (
            id INTEGER PRIMARY KEY,
            channel_control INTEGER
        );
        CREATE TABLE tg_channels (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            tg_id INTEGER,
            active INTEGER
        );
        CREATE TABLE subscription_to_tg_channel_cs (
            id INTEGER PRIMARY KEY,
            user_channel_cs_id INTEGER,
            tg_channel_id INTEGER
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


def _add_channel(db, channel_id, name="p", rss_link=None, etag=None):
    db.cursor.execute(
        "INSERT INTO channels "
        "(id, itunes_id, name, rss_link, http_etag) VALUES (?, ?, ?, ?, ?)",
        (channel_id, channel_id, name, rss_link, etag))
    db.connection.commit()


def _add_sub(db, telegram_id, channel_id, notify=1):
    db.cursor.execute(
        "INSERT INTO user_channel_cs "
        "(user_telegram_id, channel_id, notify) VALUES (?, ?, ?)",
        (telegram_id, channel_id, notify))
    db.connection.commit()


def test_iterator_skips_empty_and_includes_live_notify(db_path):
    db = SQLighter(db_path)
    try:
        _schema(db.connection)
        _add_user(db, 1001)
        _add_user(db, 1002)
        _add_user(db, 2001, deleted_at="2026-01-01")

        # 1: nobody listens
        _add_channel(db, 1, name="empty")
        # 2: notify off
        _add_channel(db, 2, name="muted")
        _add_sub(db, 1002, 2, notify=0)
        # 3: only a blocked user
        _add_channel(db, 3, name="blocked")
        _add_sub(db, 2001, 3, notify=1)
        # 4: live user with notify=1 (no tariff — nosubs still get episodes)
        _add_channel(db, 4, name="live")
        _add_sub(db, 1001, 4, notify=1)
        # 5: another empty after the live one
        _add_channel(db, 5, name="empty-after")
        # 6: live notify again
        _add_channel(db, 6, name="live-2")
        _add_sub(db, 1001, 6, notify=1)

        first = db.get_channel_or_next_to_poll(1)
        _assert_eq(int(first['id']), 4, "first pollable from id>=1")

        nxt = db.get_next_channel_to_poll(int(first['id']))
        _assert_eq(int(nxt['id']), 6, "skips empty channel 5")

        after = db.get_next_channel_to_poll(int(nxt['id']))
        _assert_eq(after, None, "no more pollable channels")

        none_before_live = db.get_next_channel_to_poll(4)
        _assert_eq(int(none_before_live['id']), 6, "id>4 skips 5, hits 6")
    finally:
        db.close()


def test_iterator_includes_tg_channel_recipient(db_path):
    db = SQLighter(db_path)
    try:
        _schema(db.connection)
        owner_id = _add_user(db, 3001)
        _add_channel(db, 10, name="tg-only")
        db.cursor.execute(
            "INSERT INTO user_channel_cs "
            "(user_telegram_id, channel_id, notify) VALUES (?, ?, ?)",
            (3001, 10, 0))
        db.connection.commit()
        uc_id = db.cursor.execute(
            "SELECT id FROM user_channel_cs WHERE channel_id = 10"
        ).fetchone()['id']
        db.cursor.execute(
            "INSERT INTO tariffs (id, channel_control) VALUES (2, 1)")
        db.cursor.execute(
            "INSERT INTO user_tariff_cs "
            "(uid, tariff_id, balance, notify_count, time_left) "
            "VALUES (?, 2, 0, -1, 100)",
            (owner_id,))
        db.cursor.execute(
            "INSERT INTO tg_channels (id, user_id, tg_id, active) "
            "VALUES (1, 3001, -100, 1)")
        db.cursor.execute(
            "INSERT INTO subscription_to_tg_channel_cs "
            "(user_channel_cs_id, tg_channel_id) VALUES (?, 1)",
            (uc_id,))
        db.connection.commit()

        row = db.get_channel_or_next_to_poll(1)
        _assert_eq(int(row['id']), 10, "tg-channel notify recipient is pollable")
    finally:
        db.close()


def test_update_and_read_http_validators(db_path):
    db = SQLighter(db_path)
    try:
        _schema(db.connection)
        _add_channel(db, 8, name="etag", rss_link="http://feed.example/rss")
        db.update_channel_http_validators(8, 'W/"x"', 'Wed, 01 Jan 2020 00:00:00 GMT')
        row = db.get_channel(8)
        _assert_eq(row['http_etag'], 'W/"x"', "stored weak etag")
        _assert_eq(
            row['http_last_modified'], 'Wed, 01 Jan 2020 00:00:00 GMT',
            "stored last-modified")
        db.update_channel_http_validators(8, '"fresh"', None)
        row = db.get_channel(8)
        _assert_eq(row['http_etag'], '"fresh"', "etag updated on 200")
        _assert_eq(row['http_last_modified'], None, "last-modified cleared")
    finally:
        db.close()


def test_ensure_columns_on_connect(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE channels (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    sqliteAdapter._channel_http_validators_checked = False
    db = SQLighter(db_path)
    try:
        columns = [
            row[1] for row in
            db.connection.execute("PRAGMA table_info(channels)").fetchall()]
        _assert_eq('http_etag' in columns, True, "ensure created http_etag")
        _assert_eq(
            'http_last_modified' in columns, True,
            "ensure created http_last_modified")
    finally:
        db.close()
        sqliteAdapter._channel_http_validators_checked = False


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_channel_poll_")
    test_iterator_skips_empty_and_includes_live_notify(
        os.path.join(tmpdir, "iter.db"))
    test_iterator_includes_tg_channel_recipient(
        os.path.join(tmpdir, "tg.db"))
    test_update_and_read_http_validators(
        os.path.join(tmpdir, "etag.db"))
    test_ensure_columns_on_connect(
        os.path.join(tmpdir, "ensure.db"))
    print("all channel poll checks passed")


if __name__ == "__main__":
    main()
