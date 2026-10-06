# -*- coding: utf-8 -*-
"""Opening the episode list marks the podcast seen, without skipping a file.

Until 2026-10 it never did: the builtin `id` was passed instead of the chat
id, so the "new" mark of a muted subscription stayed for good.

Uses a temporary file DB only — never opens production databases.
Run from the repo root: python db/test_mark_sub_seen.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.sqliteAdapter import SQLighter  # noqa: E402

CHANNEL_GUID = "guid-42_2026-10-06 10:00:00"
CHANNEL_DATE = "2026-10-06 10:00:00"
OLD_GUID = "guid-41_2026-09-29 10:00:00"
OLD_DATE = "2026-09-29 10:00:00"


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _schema(conn):
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, telegramId INTEGER UNIQUE);
        CREATE TABLE channels (id INTEGER PRIMARY KEY, last_guid TEXT, last_date TEXT);
        CREATE TABLE user_channel_cs (
            id INTEGER PRIMARY KEY, user_telegram_id INTEGER, channel_id INTEGER,
            last_guid TEXT, last_date TEXT, notify INTEGER);
        CREATE TABLE user_tariff_cs (
            id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
            notify_count INTEGER, time_left INTEGER);
    """)
    conn.commit()


def _user(db, telegram_id, channel_id, notify, paid):
    db.cursor.execute("INSERT INTO users (telegramId) VALUES (?)", (telegram_id,))
    uid = db.cursor.lastrowid
    if paid is not None:
        db.cursor.execute(
            "INSERT INTO user_tariff_cs (uid, tariff_id, notify_count, time_left) "
            "VALUES (?, ?, ?, ?)", (uid, 3 if paid else 0, 50 if paid else 0, 120 if paid else 0))
    db.cursor.execute(
        "INSERT INTO user_channel_cs (user_telegram_id, channel_id, last_guid, last_date, notify) "
        "VALUES (?, ?, ?, ?, ?)", (telegram_id, channel_id, OLD_GUID, OLD_DATE, notify))
    db.connection.commit()


def _cursor(db, telegram_id, channel_id):
    row = db.cursor.execute(
        "SELECT last_guid, last_date FROM user_channel_cs "
        "WHERE user_telegram_id = ? AND channel_id = ?", (telegram_id, channel_id)).fetchone()
    return row[0], row[1]


def main():
    path = os.path.join(tempfile.mkdtemp(prefix="yourcast_seen_"), "db.sqlite")
    db = SQLighter(path)
    try:
        _schema(db.connection)
        db.cursor.execute("INSERT INTO channels VALUES (1, ?, ?)", (CHANNEL_GUID, CHANNEL_DATE))
        db.cursor.execute("INSERT INTO channels VALUES (2, '__', ?)", (CHANNEL_DATE,))
        db.connection.commit()
        _user(db, 101, 1, notify=0, paid=None)    # muted, no tariff
        _user(db, 102, 1, notify=1, paid=False)   # free, reminded by the digest
        _user(db, 103, 1, notify=1, paid=True)    # gets the file from the circle
        _user(db, 104, 1, notify=0, paid=True)    # paid but muted: no file comes
        _user(db, 105, 2, notify=0, paid=None)    # channel parsed to nothing yet
        _user(db, 106, 1, notify=1, paid=None)    # free, no tariff row at all

        _assert_eq(db.mark_sub_seen(101, 1), (CHANNEL_GUID, CHANNEL_DATE),
                   "muted subscription takes the channel's cursor")
        _assert_eq(_cursor(db, 101, 1), (CHANNEL_GUID, CHANNEL_DATE), "stored in the updater's format")
        _assert_eq(db.mark_sub_seen(102, 1), (CHANNEL_GUID, CHANNEL_DATE),
                   "free listener: seen in the list, not reminded again")
        _assert_eq(db.mark_sub_seen(103, 1), None,
                   "paid with notify: the circle still sends the file")
        _assert_eq(_cursor(db, 103, 1), (OLD_GUID, OLD_DATE), "paid cursor untouched")
        _assert_eq(db.mark_sub_seen(104, 1), (CHANNEL_GUID, CHANNEL_DATE),
                   "paid but muted gets no file, so seen moves it")
        _assert_eq(db.mark_sub_seen(105, 2), None, "a '__' channel cursor is not copied")
        _assert_eq(_cursor(db, 105, 2), (OLD_GUID, OLD_DATE), "quiet start keeps that cursor")
        _assert_eq(db.mark_sub_seen(106, 1), (CHANNEL_GUID, CHANNEL_DATE),
                   "free without a tariff row (NULL) is not mistaken for paid")
        _assert_eq(db.mark_sub_seen(999, 1), None, "not subscribed: nothing to mark")
    finally:
        db.close()
    print("all mark_sub_seen checks passed")


if __name__ == "__main__":
    main()
