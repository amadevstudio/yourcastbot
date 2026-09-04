# -*- coding: utf-8 -*-
"""usersCount must not block the sticky incoming worker.

Uses a temporary file DB only — never opens production databases.
Run from the repo root: python db/test_users_count_async.py
"""
import os
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402
from app.controller.builders import adminModule  # noqa: E402
from db.hot_indexes import ensure_hot_path_indexes  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _schema(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            telegramId INTEGER NOT NULL UNIQUE,
            deleted_at TEXT
        );
        CREATE TABLE channels (
            id INTEGER PRIMARY KEY
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
    conn.execute("INSERT INTO users (telegramId) VALUES (1)")
    conn.execute("INSERT INTO channels (id) VALUES (1)")
    conn.commit()


def test_handler_returns_before_sql(db_path):
    original_db = config.db_path
    original_compute = adminModule.compute_users_count_text
    original_render = adminModule.render_messages
    original_flag = adminModule.storage.set_user_resend_flag
    started = threading.Event()
    released = threading.Event()
    replies = []

    def slow_compute():
        started.set()
        if not released.wait(2.0):
            raise AssertionError("compute was not unblocked")
        return "ok-count"

    def fake_render(chat_id, message_structures, **_kwargs):
        replies.append(message_structures[0]['text'])
        return []

    config.db_path = db_path
    adminModule._users_count_running = False
    adminModule.compute_users_count_text = slow_compute
    adminModule.render_messages = fake_render
    adminModule.storage.set_user_resend_flag = lambda _chat_id: None
    try:
        t0 = time.monotonic()
        adminModule.send_users_count_to_creator({
            'chat_id': 1, 'language_code': 'ru'})
        elapsed = time.monotonic() - t0
        if elapsed > 0.2:
            raise AssertionError(
                "send_users_count_to_creator blocked for %.3fs" % elapsed)
        if not started.wait(1.0):
            raise AssertionError("background compute did not start")
        adminModule.send_users_count_to_creator({
            'chat_id': 1, 'language_code': 'ru'})
        released.set()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and replies != ["ok-count"]:
            time.sleep(0.01)
        if replies != ["ok-count"]:
            raise AssertionError("expected one reply, got %r" % replies)
        print("ok  handler returns immediately and single-flights")
    finally:
        released.set()
        config.db_path = original_db
        adminModule.compute_users_count_text = original_compute
        adminModule.render_messages = original_render
        adminModule.storage.set_user_resend_flag = original_flag
        adminModule._users_count_running = False


def test_compute_text(db_path):
    original_db = config.db_path
    db = SQLighter(db_path)
    try:
        _schema(db.connection)
        ensure_hot_path_indexes(db.connection, db_path + "-schema")
        db.connection.execute(
            "INSERT INTO user_channel_cs "
            "(user_telegram_id, channel_id, notify) VALUES (1, 1, 1)")
        db.connection.commit()
    finally:
        db.close()
    config.db_path = db_path
    try:
        text = adminModule.compute_users_count_text()
        if "Всего: 1" not in text:
            raise AssertionError(text)
        print("ok  compute_users_count_text")
    finally:
        config.db_path = original_db


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_users_count_async_")
    test_handler_returns_before_sql(os.path.join(tmpdir, "async.db"))
    test_compute_text(os.path.join(tmpdir, "compute.db"))
    print("all usersCount async checks passed")


if __name__ == "__main__":
    main()
