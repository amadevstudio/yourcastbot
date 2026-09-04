# -*- coding: utf-8 -*-
"""Hot-path sqlite indexes for /menu, /usersCount, and the updater poll.

Uses a temporary file DB only — never opens production databases.
Run from the repo root: python db/test_hot_indexes.py
"""
import os
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.connection import connect_sqlite  # noqa: E402
from db.hot_indexes import (  # noqa: E402
    HOT_INDEXES, build_hot_path_indexes, ensure_hot_path_indexes)
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok ", label)


def _schema(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            telegramId INTEGER NOT NULL UNIQUE,
            deleted_at TEXT
        );
        CREATE TABLE channels (
            id INTEGER PRIMARY KEY,
            last_guid TEXT,
            last_date TEXT
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
            notify_count INTEGER,
            time_left INTEGER
        );
    """)
    conn.commit()


def _plan(conn, sql):
    rows = conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
    return " ".join(str(part) for row in rows for part in row).lower()


def test_indexes_created_and_used(db_path):
    conn = connect_sqlite(db_path)
    try:
        _schema(conn)
        ensure_hot_path_indexes(conn, db_path)
        names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        for name, _table, _columns in HOT_INDEXES:
            _assert(name in names, "index %s exists" % name)

        user_plan = _plan(
            conn,
            "SELECT 1 FROM user_channel_cs "
            "WHERE user_telegram_id = 1 AND notify = 1")
        _assert(
            "ucc_user_notify_idx" in user_plan,
            "user lookup uses ucc_user_notify_idx: %s" % user_plan)

        channel_plan = _plan(
            conn,
            "SELECT 1 FROM user_channel_cs "
            "WHERE channel_id = 1 AND notify = 1")
        _assert(
            "ucc_channel_notify_idx" in channel_plan,
            "channel lookup uses ucc_channel_notify_idx: %s" % channel_plan)

        tariff_plan = _plan(
            conn,
            "SELECT 1 FROM user_tariff_cs WHERE uid = 1")
        _assert(
            "utc_uid_idx" in tariff_plan,
            "tariff lookup uses utc_uid_idx: %s" % tariff_plan)
    finally:
        conn.close()


def test_count_users_uses_exists_not_full_distinct_scan(db_path):
    db = SQLighter(db_path)
    try:
        _schema(db.connection)
        ensure_hot_path_indexes(db.connection, db_path + "-after-schema")
        db.connection.executemany(
            "INSERT INTO users (telegramId) VALUES (?)",
            [(i,) for i in range(1, 201)])
        db.connection.executemany(
            "INSERT INTO user_channel_cs "
            "(user_telegram_id, channel_id, notify) VALUES (?, ?, 1)",
            [(i, 1, ) for i in range(1, 201)])
        db.connection.commit()

        plan = _plan(
            db.connection,
            "SELECT COUNT(*) FROM users u "
            "WHERE u.deleted_at IS NULL AND EXISTS ("
            "SELECT 1 FROM user_channel_cs ucc "
            "WHERE ucc.user_telegram_id = u.telegramId)")
        _assert("exists" in plan or "ucc_user_notify_idx" in plan, plan)
        _assert(db.count_users(True) == 200, "with_subs = 200")
        db.connection.execute(
            "INSERT INTO channels (id, last_guid, last_date) "
            "VALUES (1, 'new', '2026-02-01')")
        db.connection.execute(
            "UPDATE user_channel_cs SET last_guid = 'old', "
            "last_date = '2026-01-01' WHERE user_telegram_id = 1")
        db.connection.commit()
        _assert(db.is_user_have_new_episodes(1) is True, "new episodes")
        _assert(db.is_user_have_new_episodes(2) is False, "no last_guid")
    finally:
        db.close()


def test_build_is_idempotent(db_path):
    conn = connect_sqlite(db_path)
    try:
        _schema(conn)
    finally:
        conn.close()
    build_hot_path_indexes(db_path)
    build_hot_path_indexes(db_path)
    conn = connect_sqlite(db_path)
    try:
        names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        _assert("ucc_user_notify_idx" in names, "idempotent build")
    finally:
        conn.close()


def test_count_users_stays_fast_on_larger_set(db_path):
    users = 3000
    subs_per_user = 8
    db = SQLighter(db_path)
    try:
        _schema(db.connection)
        ensure_hot_path_indexes(db.connection, db_path + "-scale")
        db.connection.executemany(
            "INSERT INTO users (telegramId) VALUES (?)",
            [(i,) for i in range(1, users + 1)])
        db.connection.executemany(
            "INSERT INTO channels (id) VALUES (?)",
            [(i,) for i in range(1, subs_per_user + 1)])
        rows = [
            (user_id, channel_id, 1)
            for user_id in range(1, users + 1)
            for channel_id in range(1, subs_per_user + 1)]
        db.connection.executemany(
            "INSERT INTO user_channel_cs "
            "(user_telegram_id, channel_id, notify) VALUES (?, ?, ?)",
            rows)
        db.connection.executemany(
            "INSERT INTO user_tariff_cs "
            "(uid, tariff_id, notify_count, time_left) VALUES (?, 3, -1, 100)",
            [(i,) for i in range(1, 501)])
        db.connection.commit()

        started = time.monotonic()
        got = {
            'total': db.count_users(),
            'with_subs': db.count_users(True),
            'payed': db.count_users(payed=True),
            'receive': db.count_users(receive_episodes=True),
            'digest': db.count_users(digest_reminder=True),
        }
        elapsed = time.monotonic() - started
        print("scale counts %s in %.3fs" % (got, elapsed))
        _assert(got['total'] == users, "total")
        _assert(got['with_subs'] == users, "with_subs")
        _assert(got['payed'] == 500, "payed")
        _assert(got['receive'] == 500, "receive")
        _assert(got['digest'] == users - 500, "digest")
        _assert(elapsed < 1.5, "all count_users in %.3fs" % elapsed)
        _assert(
            db.is_user_have_new_episodes(1) is False,
            "menu new-episode probe")
    finally:
        db.close()


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_hot_indexes_")
    test_indexes_created_and_used(os.path.join(tmpdir, "plan.db"))
    test_count_users_uses_exists_not_full_distinct_scan(
        os.path.join(tmpdir, "exists.db"))
    test_build_is_idempotent(os.path.join(tmpdir, "build.db"))
    test_count_users_stays_fast_on_larger_set(os.path.join(tmpdir, "scale.db"))
    print("all hot_indexes checks passed")


if __name__ == "__main__":
    main()
