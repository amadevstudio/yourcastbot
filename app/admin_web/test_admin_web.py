# -*- coding: utf-8 -*-
"""Admin API: auth, stats, users without N+1, mailing as a job.

Uses a temporary file DB only. Run from the repo root:
python app/admin_web/test_admin_web.py
"""
import hashlib
import os
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402
from app.admin_web import auth, mail_jobs, mailer, queries  # noqa: E402
from app.admin_web.server import app  # noqa: E402
from db.hot_indexes import ensure_hot_path_indexes  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


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
            level INTEGER NOT NULL,
            price INTEGER NOT NULL,
            notify_count INTEGER NOT NULL,
            compression INTEGER,
            channel_control INTEGER
        );
        CREATE TABLE admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mail TEXT NOT NULL,
            password TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO admins (mail, password) VALUES (?, ?)",
        ("ops@yourcast.test", hashlib.sha256(b"secret").hexdigest()),
    )
    conn.execute(
        "INSERT INTO users (telegramId, lang) VALUES (1001, 'ru')")
    conn.execute(
        "INSERT INTO users (telegramId, lang) VALUES (1002, 'en')")
    conn.execute(
        "INSERT INTO users (telegramId, lang, deleted_at) "
        "VALUES (2001, 'ru', '2026-01-01')")
    conn.execute(
        "INSERT INTO channels (id, itunes_id, name) VALUES (1, 1, 'Alpha')")
    conn.execute(
        "INSERT INTO channels (id, itunes_id, name) VALUES (2, 2, 'Beta')")
    conn.execute(
        "INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) "
        "VALUES (1001, 1, 1)")
    conn.execute(
        "INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) "
        "VALUES (1001, 2, 0)")
    conn.execute(
        "INSERT INTO user_tariff_cs "
        "(uid, tariff_id, balance, notify_count, time_left) "
        "VALUES (1, 3, 0, -1, 100)")
    conn.execute(
        "INSERT INTO tariffs "
        "(id, level, price, notify_count, compression, channel_control) "
        "VALUES (1, 1, 199, 10, 0, 0)")
    conn.commit()


def _prepare(path):
    db = SQLighter(path)
    try:
        _schema(db.connection)
        ensure_hot_path_indexes(db.connection, path + "-schema")
    finally:
        db.close()


def test_auth_roundtrip():
    token = auth.sign_session(7, "ops@yourcast.test", now=1_000_000)
    payload = auth.read_session(token, now=1_000_001)
    _assert_eq(payload["id"], 7, "session id")
    _assert_eq(payload["mail"], "ops@yourcast.test", "session mail")
    expired = auth.read_session(token, now=1_000_000 + auth.SESSION_TTL_SEC + 5)
    _assert_eq(expired, None, "expired session")
    tampered = token[:-2] + ("ab" if token[-2:] != "ab" else "cd")
    _assert_eq(auth.read_session(tampered, now=1_000_001), None, "bad sig")


def test_login_rate_limit():
    auth._login_attempts.clear()
    ip = "10.0.0.9"
    for _ in range(auth.MAX_LOGIN_ATTEMPTS):
        _assert_eq(auth.login_allowed(ip, now=50), True, "under limit")
        auth.register_login_failure(ip, now=50)
    _assert_eq(auth.login_allowed(ip, now=50), False, "locked")
    _assert_eq(
        auth.login_allowed(ip, now=50 + auth.LOGIN_WINDOW_SEC + 1),
        True, "lock expired")


def test_queries_and_mailer(path):
    original = config.db_path
    config.db_path = path
    try:
        admin = queries.find_admin("ops@yourcast.test", "secret", database=path)
        _assert_eq(admin["mail"], "ops@yourcast.test", "admin login")
        _assert_eq(
            queries.find_admin("ops@yourcast.test", "nope", database=path),
            None, "bad password")
        stats = queries.stats(database=path)
        _assert_eq(stats["total"], 2, "live users")
        _assert_eq(stats["with_subs"], 1, "with subs")
        _assert_eq(stats["blocked"], 1, "blocked")
        listing = queries.list_users(database=path)
        first = listing["users"][0]
        _assert_eq(first["telegramId"], 1001, "paid user first")
        names = sorted(s["name"] for s in first["subs"])
        _assert_eq(names, ["Alpha", "Beta"], "subs in one query")
        updated = queries.update_tariff(1, 1, 250, 20, 1, 1, database=path)
        _assert_eq(updated["price"], 250, "tariff price")

        sent = []

        def fake_send(tgid, message, parse_mode, attachments, attachment_type):
            sent.append(tgid)
            return True, None

        job = mail_jobs.enqueue(
            message="hello", to_creator_only=False,
            recipients_text="1001,1002,-100999",
            created_by="ops@yourcast.test", database=path)
        mailer.mailer_loop(
            database=path, send_fn=fake_send, stop_after=1)
        done = mail_jobs.get_job(job["id"], database=path)
        _assert_eq(done["status"], "done", "mail job finished")
        _assert_eq(done["sent"], 2, "two users sent")
        _assert_eq(done["skipped"], 1, "channel skipped")
        _assert_eq(config.creatorId in sent, True, "creator start/end ping")
    finally:
        config.db_path = original


def test_http(path):
    original = config.db_path
    original_server = config.server
    config.db_path = path
    config.server = False
    mail_jobs._ready.clear()
    try:
        client = TestClient(app)
        denied = client.get("/api/stats")
        _assert_eq(denied.status_code, 401, "stats requires auth")
        bad = client.post(
            "/api/login", json={"mail": "ops@yourcast.test", "password": "x"})
        _assert_eq(bad.status_code, 401, "bad login")
        _assert_eq(
            bad.json()["detail"], "Неверная почта или пароль", "login error text")
        ok = client.post(
            "/api/login",
            json={"mail": "ops@yourcast.test", "password": "secret"})
        _assert_eq(ok.status_code, 200, "login ok")
        stats = client.get("/api/stats")
        _assert_eq(stats.status_code, 200, "authed stats")
        _assert_eq(stats.json()["total"], 2, "stats total")
        users = client.get("/api/users")
        _assert_eq(users.status_code, 200, "users list")
        _assert_eq(len(users.json()["users"][0]["subs"]), 2, "no N+1 payload")
        job = client.post(
            "/api/mail",
            data={
                "message": "ping",
                "to_creator_only": "true",
                "parse_mode": "html",
            },
        )
        _assert_eq(job.status_code, 200, "enqueue mail")
        _assert_eq(job.json()["status"], "queued", "mail queued")
        listed = client.get("/api/mail")
        _assert_eq(listed.json()["jobs"][0]["id"], job.json()["id"], "mail list")
    finally:
        config.db_path = original
        config.server = original_server


def main():
    test_auth_roundtrip()
    test_login_rate_limit()
    tmpdir = tempfile.mkdtemp(prefix="yourcast_admin_web_")
    path = os.path.join(tmpdir, "admin.db")
    _prepare(path)
    test_queries_and_mailer(path)
    test_http(path)
    print("all admin_web checks passed")


if __name__ == "__main__":
    main()
