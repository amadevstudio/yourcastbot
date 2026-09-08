# -*- coding: utf-8 -*-
"""users.created_at is set on insert, never backfilled. Run:
python db/test_users_created_at.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.connection import connect_sqlite  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok ", label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _schema_without_created_at(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            telegramId INTEGER NOT NULL UNIQUE,
            lang char(15),
            deleted_at TEXT
        );
    """)
    conn.commit()


def test_existing_rows_stay_null(db_path):
    conn = connect_sqlite(db_path)
    try:
        _schema_without_created_at(conn)
        conn.execute("INSERT INTO users (telegramId) VALUES ('1001')")
        conn.commit()
    finally:
        conn.close()

    db = SQLighter(db_path)
    try:
        columns = {
            row[1] for row in
            db.connection.execute("PRAGMA table_info(users)").fetchall()}
        _assert("created_at" in columns, "created_at column exists")
        row = db.connection.execute(
            "SELECT created_at FROM users WHERE telegramId = '1001'"
        ).fetchone()
        _assert_eq(row["created_at"], None, "old user has no fake date")
    finally:
        db.close()


def test_register_sets_and_does_not_overwrite(db_path):
    conn = connect_sqlite(db_path)
    try:
        _schema_without_created_at(conn)
    finally:
        conn.close()

    db = SQLighter(db_path)
    try:
        new_user, by_refer = db.register_new_user(2001, "ru")
        _assert_eq(new_user, True, "first register is new")
        _assert_eq(by_refer, False, "no refer")
        first = db.connection.execute(
            "SELECT created_at FROM users WHERE telegramId = '2001'"
        ).fetchone()["created_at"]
        _assert(first not in (None, ""), "new user gets created_at")

        db.connection.execute(
            "UPDATE users SET created_at = '2020-01-02 03:04:05' "
            "WHERE telegramId = '2001'")
        db.connection.commit()
        again, _ = db.register_new_user(2001, "en")
        _assert_eq(again, False, "second register is existing")
        row = db.connection.execute(
            "SELECT lang, created_at FROM users WHERE telegramId = '2001'"
        ).fetchone()
        _assert_eq(row["lang"], "en", "lang updated")
        _assert_eq(
            row["created_at"], "2020-01-02 03:04:05",
            "created_at not overwritten")
    finally:
        db.close()


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_created_at_")
    test_existing_rows_stay_null(os.path.join(tmpdir, "old.db"))
    test_register_sets_and_does_not_overwrite(os.path.join(tmpdir, "new.db"))
    print("all users.created_at checks passed")


if __name__ == "__main__":
    main()
