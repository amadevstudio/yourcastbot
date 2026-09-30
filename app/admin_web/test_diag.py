# -*- coding: utf-8 -*-
"""Read-only diag reports and the diag token. Temp DB and logs, no FastAPI.

Run from the repo root: python app/admin_web/test_diag.py
"""
import datetime
import json
import os
import sqlite3
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Logs are server-local and the DB is UTC: run in a zone that is not UTC.
os.environ["TZ"] = "Europe/Moscow"
time.tzset()

from app.admin_web import diag  # noqa: E402

TOKEN = "t" * 40
NOW = datetime.datetime(2026, 9, 30, 11, 50)  # server-local


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _assert_in(part, text, label):
    if part not in text:
        raise AssertionError("%s: %r not in\n%s" % (label, part, text))
    print("ok  %s" % label)


def _job(conn, job_id, created, chats, channel_id, title, uid):
    payload = {"action": "circle", "user_id": "c%s" % channel_id, "func_params": {
        "link": "https://cdn.example/%s.mp3" % job_id,
        "chat_ids": {str(chat): {} for chat in chats},
        "podcastInfo": {"id": channel_id, "title": title, "pubDate": created[:10],
                        "recordUniqId": uid}}}
    conn.execute(
        "INSERT INTO send_outbox VALUES (?, ?, 'circle', ?, ?, 'done', 1, NULL, ?)",
        (job_id, created, "c%s" % channel_id, json.dumps(payload), created))


def _prepare(work_dir):
    path = os.path.join(work_dir, "diag.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE, lang TEXT,
            deleted_at TEXT, nosub_digest_sent_at TEXT);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER,
            notify_count INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
            balance INTEGER, notify_count INTEGER, time_left INTEGER);
        CREATE TABLE channels (id INTEGER PRIMARY KEY, itunes_id INTEGER, name TEXT,
            last_guid TEXT, last_date TEXT);
        CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER,
            channel_id INTEGER, last_guid TEXT, last_date TEXT, notify INTEGER);
        CREATE TABLE digest_outbox (user_telegram_id INTEGER PRIMARY KEY, created_at TEXT,
            status TEXT, attempts INTEGER, leased_until TEXT, available_at TEXT);
        CREATE TABLE payment_history (user_id INTEGER, service_type TEXT, invoice_id TEXT,
            invoice_hash TEXT, status TEXT, amount INTEGER, datetime TEXT);
        CREATE TABLE send_outbox (id INTEGER PRIMARY KEY, created_at TEXT, action TEXT,
            user_id TEXT, payload_json TEXT, status TEXT, attempts INTEGER,
            leased_until TEXT, available_at TEXT);
        INSERT INTO tariffs VALUES (3, 3, 500, -1);

        -- 42: renewed at 09:00 local after an 08:06 flag (05:06 UTC): the gap
        INSERT INTO users VALUES (1, 42, 'en', NULL, '2026-09-30 05:06:03');
        INSERT INTO user_tariff_cs VALUES (1, 1, 3, 30746, -1, 717);
        INSERT INTO digest_outbox VALUES (42, '2026-09-30T05:06:01Z', 'done', 1, NULL, 'x');
        -- 4004: flag at 01:30, paid at 01:40, period from 02:00: bought after the digest
        INSERT INTO users VALUES (4, 4004, 'en', NULL, '2026-09-29 22:30:05');
        INSERT INTO user_tariff_cs VALUES (4, 4, 3, 100, -1, 710);
        INSERT INTO digest_outbox VALUES (4004, '2026-09-29T22:30:01Z', 'done', 1, NULL, 'x');
        INSERT INTO payment_history VALUES (4004, 'stars', 'i1', NULL, 'paid', 500,
            '2026-09-29T22:40:00');
        -- 5005: renewed five days ago, no flag since: clean
        INSERT INTO users VALUES (5, 5005, 'en', NULL, '2026-09-01 10:00:00');
        INSERT INTO user_tariff_cs VALUES (5, 5, 3, 9000, -1, 600);
        -- 2002: renewed two weeks ago: traces purged
        INSERT INTO users VALUES (2, 2002, 'en', NULL, NULL);
        INSERT INTO user_tariff_cs VALUES (2, 2, 3, 30000, -1, 400);
        -- 3003: expired, not a payer now
        INSERT INTO users VALUES (3, 3003, 'en', NULL, NULL);
        INSERT INTO user_tariff_cs VALUES (3, 3, 3, 100, -1, 0);

        INSERT INTO channels VALUES (7, 111, 'World News Tonight', 'wed', 'x');
        INSERT INTO channels VALUES (8, 222, 'Other Pod', 'x-2', 'x');
        INSERT INTO user_channel_cs VALUES (1, 42, 7, 'wed', 'x', 1);
        INSERT INTO user_channel_cs VALUES (2, 42, 8, 'x-2', 'x', 1);
    """)
    _job(conn, 1, "2026-09-29T09:00:00Z", [42], 8, "Ep 1", "x-1")
    _job(conn, 2, "2026-09-30T03:45:00Z", [42, 2002], 7, "Tuesday", "tue")
    _job(conn, 3, "2026-09-30T05:06:01Z", [2002], 7, "Wednesday Special", "wed")
    conn.commit()
    conn.close()
    os.makedirs(os.path.join(work_dir, "log"))
    with open(os.path.join(work_dir, "log", "updater_30_09_2026.log"), "w") as log:
        log.write(
            "[08:05:50 30.09.2026] LOG Processig channel 8\n"
            "[08:06:00 30.09.2026] LOG Processig channel 7\n"
            "[08:06:01 30.09.2026] LOG Sending automatically...\n"
            " b\"Channel id: 7, 'Wednesday Special' to {2002: {}}\"\n"
            "[08:06:01 30.09.2026] LOG ENQUEUED AUTOMATICALLY! To:  [2002]\n"
            "[08:06:02 30.09.2026] LOG Processig channel 9\n")
    return path


def test_token():
    _assert_eq(diag.token_ok("Bearer " + TOKEN, TOKEN), True, "right token")
    _assert_eq(diag.token_ok("Bearer " + TOKEN[:-1] + "x", TOKEN), False, "wrong token")
    _assert_eq(diag.token_ok(TOKEN, TOKEN), False, "Bearer prefix required")
    _assert_eq(diag.token_ok(None, TOKEN), False, "no header")
    _assert_eq(diag.token_ok("Bearer ", ""), False, "empty configured token: off")
    _assert_eq(diag.token_ok("Bearer short", "short"), False, "short configured token: off")
    _assert_eq(diag.enabled(None), False, "unset: off")
    _assert_eq(diag.enabled(TOKEN), True, "40 chars: on")


def test_read_only(path):
    conn = diag.connect_ro(path)
    try:
        conn.execute("UPDATE users SET lang = 'ru'")
    except sqlite3.OperationalError as e:
        _assert_in("readonly", str(e), "diag connection cannot write")
    else:
        raise AssertionError("diag connection wrote to the DB")
    finally:
        conn.close()


def test_report(path, work_dir):
    conn = diag.connect_ro(path)
    try:
        text = diag.as_text(diag.report, conn, 42, work_dir=work_dir)
    finally:
        conn.close()
    _assert_in("08:06:03 server-local", text, "digest time converted to server-local")
    _assert_in("[08:06:01 30.09.2026] LOG Sending automatically", text,
               "log lines of the chat's podcasts in that hour")
    _assert_in("Processig channel 8", text, "processed podcast listed")
    _assert_eq("Processig channel 9" in text, False, "other podcasts are not listed")
    _assert_in("MISSED: #7 World News Tonight | Wednesday Special", text,
               "episode queued for others in the gap hour is reported")
    _assert_in("processed, no circle job: #8 Other Pod", text,
               "podcast without other payers is flagged for a look")


def test_audit(path):
    conn = diag.connect_ro(path)
    try:
        text = diag.as_text(diag.audit, conn, now=NOW)
    finally:
        conn.close()
    lines = {line.split()[0]: line for line in text.splitlines()
             if line.startswith("  ") and line.split()[0].isdigit()}
    _assert_in("GAP", lines.get("42", ""), "42: gap")
    _assert_in("MISSED: #7 World News Tonight | Wednesday Special", text, "42: missed episode")
    _assert_in("bought after the digest", lines.get("4004", ""), "4004: paid after the digest")
    _assert_in("clean", lines.get("5005", ""), "5005: clean")
    _assert_in("unknown", lines.get("2002", ""), "2002: traces purged")
    _assert_eq("3003" in lines, False, "expired user is not a payer")


def main():
    work_dir = tempfile.mkdtemp(prefix="yourcast_diag_")
    path = _prepare(work_dir)
    test_token()
    test_read_only(path)
    test_report(path, work_dir)
    test_audit(path)
    print("all diag checks passed")


if __name__ == "__main__":
    main()
