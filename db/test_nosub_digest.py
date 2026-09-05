# -*- coding: utf-8 -*-
"""users.nosub_digest_* columns. Run: python db/test_nosub_digest.py"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.connection import connect_sqlite  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402
from app.jobs.nosub_digest import should_send_nosub_digest  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok ", label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _schema_without_digest(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            telegramId INTEGER NOT NULL UNIQUE,
            lang char(15),
            deleted_at TEXT
        );
    """)
    conn.commit()


def test_backfill_existing_users(db_path):
    conn = connect_sqlite(db_path)
    try:
        _schema_without_digest(conn)
        conn.execute("INSERT INTO users (telegramId) VALUES ('1001')")
        conn.execute("INSERT INTO users (telegramId) VALUES ('1002')")
        conn.commit()
    finally:
        conn.close()

    db = SQLighter(db_path)
    try:
        columns = {
            row[1] for row in
            db.connection.execute("PRAGMA table_info(users)").fetchall()}
        _assert("nosub_digest_enabled" in columns, "enabled column exists")
        _assert("nosub_digest_sent_at" in columns, "sent_at column exists")

        rows = db.connection.execute(
            "SELECT telegramId, nosub_digest_enabled, nosub_digest_sent_at "
            "FROM users ORDER BY telegramId").fetchall()
        _assert_eq(len(rows), 2, "both users kept")
        for row in rows:
            _assert_eq(row["nosub_digest_enabled"], 1, "default enabled")
            _assert(
                row["nosub_digest_sent_at"] not in (None, ""),
                "sent_at backfilled for %s" % row["telegramId"])
            _assert(
                not should_send_nosub_digest(row),
                "backfilled user is not due yet")
    finally:
        db.close()


def test_does_not_overwrite_existing_sent_at(db_path):
    old = "2026-01-01 00:00:00"
    conn = connect_sqlite(db_path)
    try:
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
                telegramId INTEGER NOT NULL UNIQUE,
                nosub_digest_enabled INTEGER NOT NULL DEFAULT 1,
                nosub_digest_sent_at TEXT
            );
        """)
        conn.execute(
            "INSERT INTO users (telegramId, nosub_digest_sent_at) "
            "VALUES ('2001', ?)",
            (old,))
        conn.commit()
    finally:
        conn.close()

    db = SQLighter(db_path)
    try:
        row = db.get_user_by_tg(2001)
        _assert_eq(row["nosub_digest_sent_at"], old, "existing sent_at kept")
        _assert(
            should_send_nosub_digest(
                row, now=datetime(2026, 9, 5, 0, 0, 0)),
            "old sent_at is due")
        db.set_nosub_digest_enabled(2001, False)
        row = db.get_user_by_tg(2001)
        _assert_eq(row["nosub_digest_enabled"], 0, "opt-out persisted")
        _assert(
            not should_send_nosub_digest(
                row, now=datetime(2026, 9, 5, 0, 0, 0)),
            "opt-out skips even when due")
        db.set_nosub_digest_enabled(2001, True)
        db.mark_nosub_digest_sent(
            2001, datetime(2026, 9, 5, 0, 0, 0))
        row = db.get_user_by_tg(2001)
        _assert(
            not should_send_nosub_digest(
                row, now=datetime(2026, 9, 5, 1, 0, 0)),
            "just marked sent is not due")
        _assert(
            should_send_nosub_digest(
                row, now=datetime(2026, 9, 5, 0, 0, 0) + timedelta(days=7)),
            "due again after a week")
        created = db.get_user_by_tg(3001)
        _assert(
            created["nosub_digest_sent_at"] not in (None, ""),
            "new user is stamped as just sent")
        _assert(
            not should_send_nosub_digest(created),
            "new user waits a week")
    finally:
        db.close()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_backfill_existing_users(os.path.join(tmp, "backfill.db"))
        test_does_not_overwrite_existing_sent_at(os.path.join(tmp, "keep.db"))
    print("all nosub digest column checks passed")


if __name__ == "__main__":
    main()
