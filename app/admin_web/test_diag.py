# -*- coding: utf-8 -*-
"""Read-only diag reports and the diag token. Temp DB and logs, no FastAPI.

The fixture is shaped like prod: done circle rows list no chats (the sender
rewrites chat_ids to the chats still waiting), recipients live only in the
updater log line written by logger.log("Sending automatically...\\n", bytes).

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


def _sending(stamp, channel_id, title, recipients):
    """The two log lines podcastsUpdater writes when it queues an episode."""
    body = ("Channel id: %s, '%s' (itunes id:111) to %s ___ link: https://cdn.example/x.mp3"
            " ___ (feed: https://feed.example/rss)" % (channel_id, title, repr(recipients)))
    return "[%s] LOG Sending automatically...\n %s\n" % (stamp, str(body.encode("utf-8")))


def _circle_row(conn, row_id, created, channel_id, title):
    payload = {"action": "circle", "user_id": "c%s" % channel_id, "func_params": {
        "link": "https://cdn.example/%s.mp3" % row_id, "chat_ids": {},
        "podcastInfo": {"id": channel_id, "title": title, "recordUniqId": title}}}
    conn.execute(
        "INSERT INTO send_outbox VALUES (?, ?, 'circle', ?, ?, 'done', 1, NULL, ?)",
        (row_id, created, "c%s" % channel_id, json.dumps(payload), created))


def _rec_row(conn, row_id, created, tg, channel_id, title):
    payload = {"action": "rec", "user_id": str(tg), "func_params": {
        "link": "https://cdn.example/%s.mp3" % row_id, "chat_ids": {},
        "podcastInfo": {"id": channel_id, "title": title, "recordUniqId": title}}}
    conn.execute(
        "INSERT INTO send_outbox VALUES (?, ?, 'rec', ?, ?, 'done', 1, NULL, ?)",
        (row_id, created, str(tg), json.dumps(payload), created))


def _prepare(work_dir):
    path = os.path.join(work_dir, "diag.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE, lang TEXT,
            deleted_at TEXT, nosub_digest_sent_at TEXT, created_at TEXT);
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
        INSERT INTO users VALUES (1, 42, 'en', NULL, '2026-09-30 05:06:03', '2025-01-01 10:00:00');
        INSERT INTO user_tariff_cs VALUES (1, 1, 3, 30746, -1, 717);
        INSERT INTO digest_outbox VALUES (42, '2026-09-30T05:06:01Z', 'done', 1, NULL, 'x');
        -- 4004: flag at 01:30, paid at 01:40, period from 02:00: bought after the digest
        INSERT INTO users VALUES (4, 4004, 'en', NULL, '2026-09-29 22:30:05', '2025-01-01 10:00:00');
        INSERT INTO user_tariff_cs VALUES (4, 4, 3, 100, -1, 710);
        INSERT INTO digest_outbox VALUES (4004, '2026-09-29T22:30:01Z', 'done', 1, NULL, 'x');
        INSERT INTO payment_history VALUES (4004, 'stars', 'i1', NULL, 'paid', 500,
            '2026-09-29T22:40:00');
        -- 5005: renewed five days ago, no flag since: clean
        INSERT INTO users VALUES (5, 5005, 'en', NULL, '2026-09-01 10:00:00', '2025-01-01 10:00:00');
        INSERT INTO user_tariff_cs VALUES (5, 5, 3, 9000, -1, 600);
        -- 2002: renewed two weeks ago: flags purged
        INSERT INTO users VALUES (2, 2002, 'en', NULL, NULL, '2025-01-01 10:00:00');
        INSERT INTO user_tariff_cs VALUES (2, 2, 3, 30000, -1, 400);
        -- 7007: registered 29.09 15:30 local (12:30 UTC), welcome Relay 336h;
        -- registration wrote nosub_digest_sent_at: not a digest, not a gap
        INSERT INTO users VALUES (7, 7007, 'en', NULL, '2026-09-29 12:30:00', '2026-09-29 12:30:00');
        INSERT INTO user_tariff_cs VALUES (7, 7, 3, 0, -1, 316);
        -- 3003: expired, not a payer now
        INSERT INTO users VALUES (3, 3003, 'en', NULL, NULL, '2025-01-01 10:00:00');
        INSERT INTO user_tariff_cs VALUES (3, 3, 3, 100, -1, 0);

        INSERT INTO channels VALUES (7, 111, 'World News Tonight', 'wed', '2026-09-30T05:00:00+0000');
        INSERT INTO channels VALUES (8, 222, 'Other Pod', 'ep1', '2026-09-28T09:00:00+0000');
        INSERT INTO channels VALUES (9, 333, 'Solo Pod', 'solo', '2026-09-30T04:00:00+0000');
        INSERT INTO channels VALUES (10, 444, 'Muted Pod', 'm2', '2026-09-30T04:00:00+0000');
        INSERT INTO user_channel_cs VALUES (1, 42, 7, 'wed', '2026-09-30T05:00:00+0000', 1);
        INSERT INTO user_channel_cs VALUES (2, 42, 8, 'ep1', '2026-09-28T09:00:00+0000', 1);
        INSERT INTO user_channel_cs VALUES (3, 42, 9, 'solo', '2026-09-30T04:00:00+0000', 1);
        INSERT INTO user_channel_cs VALUES (4, 42, 10, 'm1', '2026-09-01T04:00:00+0000', 0);
    """)
    _circle_row(conn, 1, "2026-09-30T03:45:00Z", 7, "Tuesday")
    _circle_row(conn, 2, "2026-09-30T05:06:01Z", 7, "Wednesday Special")
    _rec_row(conn, 3, "2026-09-30T04:30:00Z", 42, 9, "Solo 5")
    conn.commit()
    conn.close()
    os.makedirs(os.path.join(work_dir, "log"))
    with open(os.path.join(work_dir, "log", "updater_29_09_2026.log"), "w") as log:
        log.write("[12:00:00 29.09.2026] LOG Processig channel 8\n")
        log.write(_sending("12:00:01 29.09.2026", 8, "Ep 1", {42: {}, 2002: {}}))
    with open(os.path.join(work_dir, "log", "updater_30_09_2026.log"), "w") as log:
        log.write("[06:45:00 30.09.2026] LOG Processig channel 7\n")
        log.write(_sending("06:45:01 30.09.2026", 7, "Tuesday", {
            42: {}, 2002: {},
            -1001: {'silent': True, 'based_on_user_id': 42, 'description_mode': 'none'}}))
        log.write("[08:05:50 30.09.2026] LOG Processig channel 8\n")
        # 42 got "Ep 1" yesterday: queued again for another chat is not a miss
        log.write(_sending("08:05:51 30.09.2026", 8, "Ep 1", {3003: {}}))
        log.write("[08:06:00 30.09.2026] LOG Processig channel 7\n")
        # the episode 42 lost: queued in the gap for 2002 only
        log.write(_sending("08:06:01 30.09.2026", 7, "Wednesday – Special 'live'",
                           {2002: {}}))
        log.write("[08:06:01 30.09.2026] LOG ENQUEUED AUTOMATICALLY! To:  [2002]\n")
        # 42 tapped "Solo 5" (rec row): not a miss
        log.write("[08:07:00 30.09.2026] LOG Processig channel 9\n")
        log.write(_sending("08:07:01 30.09.2026", 9, "Solo 5", {5005: {}}))
        # muted podcast: not followed with notifications, never a miss
        log.write(_sending("08:08:01 30.09.2026", 10, "Muted 2", {5005: {}}))
        log.write("[08:10:00 30.09.2026] LOG Processig channel 9\n")
        log.write("[08:10:01 30.09.2026] LOG Feed not modified for channel 9 ; "
                  "paid listeners behind: [42, 5005] ; refetching without validators\n")
        log.write("[09:20:01 30.09.2026] LOG Feed not modified for channel 9 ; "
                  "paid listeners behind: [42] ; refetching without validators\n")
        log.write("[09:30:01 30.09.2026] LOG Feed not modified for channel 7 ; "
                  "paid listeners behind: [5005] ; refetching without validators\n")
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


def test_parse_sending():
    text = _sending("08:06:01 30.09.2026", 7, "Wednesday – Special 'live' \"x\"", {
        2002: {}, -1001: {'silent': True, 'based_on_user_id': 42}})
    parsed = diag.parse_sending(text)
    _assert_eq(parsed, (7, "Wednesday – Special 'live' \"x\"", {"2002", "-1001"}),
               "channel, title (non-ASCII, both quotes) and recipients from the log line")
    _assert_eq(diag.parse_sending("[08:00:00 30.09.2026] LOG Processig channel 7"), None,
               "other lines are not sends")


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
        text = diag.as_text(diag.report, conn, 42, work_dir=work_dir, now=NOW)
    finally:
        conn.close()
    _assert_in("08:06:03 server-local", text, "digest time converted to server-local")
    _assert_in("SENT #7 'Wednesday – Special 'live'' to 1 chats, this chat not included",
               text, "send line summarised with its recipients")
    _assert_in("MISSED: #7 World News Tonight | Wednesday – Special 'live'", text,
               "episode queued for others in the gap hour is reported")
    _assert_eq("MISSED: #8" in text, False, "got it yesterday: not a miss")
    _assert_eq("MISSED: #9" in text, False, "tapped it (rec row): not a miss")
    _assert_eq("MISSED: #10" in text, False, "notifications off: not a miss")
    _assert_eq("Muted Pod" in text, False, "muted podcasts are not listed")
    _assert_in("cursor:  2026-09-30T05:00:00+0000 | wed", text, "cursor shows its date")
    old = diag.as_text(diag.report, diag.connect_ro(path), 42, work_dir=work_dir,
                       now=NOW + datetime.timedelta(days=4))
    _assert_in("log of that hour is purged", old, "past log retention: says so, no guess")


def test_audit(path, work_dir):
    conn = diag.connect_ro(path)
    try:
        text = diag.as_text(diag.audit, conn, now=NOW, work_dir=work_dir)
    finally:
        conn.close()
    lines = {line.split()[0]: line for line in text.splitlines()
             if line.startswith("  ") and line.split()[0].isdigit()}
    _assert_in("GAP", lines.get("42", ""), "42: gap")
    _assert_in("MISSED: #7 World News Tonight | Wednesday – Special 'live'", text,
               "42: missed episode from the log")
    _assert_in("bought", lines.get("4004", ""), "4004: paid after the digest")
    _assert_in("clean", lines.get("5005", ""), "5005: clean")
    _assert_in("unknown", lines.get("2002", ""), "2002: flags purged")
    _assert_in("welcome Relay (336h)", lines.get("7007", ""),
               "7007: welcome period, registration stamp is not a flag")
    _assert_eq("3003" in lines, False, "expired user is not a payer")


def test_refetches(path, work_dir):
    conn = diag.connect_ro(path)
    try:
        text = diag.as_text(diag.refetches, conn, hours=6, now=NOW, work_dir=work_dir)
    finally:
        conn.close()
    _assert_in("#9 Solo Pod: 2 refetches, 09-30 08:10 .. 09-30 09:20, 1 payers behind", text,
               "repeated refetch of one channel is counted")
    _assert_in("#7 World News Tonight: 1 refetches", text, "single refetch listed")
    _assert_in("totals: 2 channels, 3 refetches", text, "totals")


def test_digest_stats(path):
    conn = diag.connect_ro(path)
    try:
        text = diag.as_text(diag.digest_stats, conn, hours=6, now=NOW)
    finally:
        conn.close()
    # 42 was sent at 05:06 UTC; 7007's stamp is its registration (12:30 UTC 29.09)
    _assert_in("sent (users.nosub_digest_sent_at, registrations excluded): 1", text,
               "sends counted, registration stamps are not")
    _assert_in("queued (digest_outbox by status): {'done': 1}", text,
               "queued rows in the window by status")
    _assert_in("Empty cursors (\"__\") with notifications left: 0 on 0 channels", text,
               "no empty cursors in the fixture")


def main():
    work_dir = tempfile.mkdtemp(prefix="yourcast_diag_")
    path = _prepare(work_dir)
    test_token()
    test_parse_sending()
    test_read_only(path)
    test_report(path, work_dir)
    test_audit(path, work_dir)
    test_refetches(path, work_dir)
    test_digest_stats(path)
    print("all diag checks passed")


if __name__ == "__main__":
    main()
