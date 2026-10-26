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
            deleted_at TEXT,
            created_at TEXT
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
        "INSERT INTO users (telegramId, lang, created_at) "
        "VALUES (1001, 'ru', '2024-03-15 10:30:00')")
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
    ok, upgraded = auth.verify_password("secret", hashlib.sha256(b"secret").hexdigest())
    _assert_eq(ok, True, "legacy sha256")
    _assert_eq(upgraded.startswith(auth.PBKDF2_PREFIX), True, "upgrade hash")
    ok2, again = auth.verify_password("secret", upgraded)
    _assert_eq(ok2, True, "pbkdf2 login")
    _assert_eq(again, None, "no rehash")
    bad, _ = auth.verify_password("nope", upgraded)
    _assert_eq(bad, False, "pbkdf2 reject")


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
        _assert_eq(
            first["created_at"], "2024-03-15 10:30:00", "known registration")
        by_tg = {u["telegramId"]: u for u in listing["users"]}
        _assert_eq(by_tg[1002]["created_at"], None, "unknown registration")
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

        sent2 = []
        job2 = mail_jobs.enqueue(
            message="hello2", to_creator_only=False,
            recipients_text="1001,1002,1003",
            created_by="ops@yourcast.test", database=path)

        def fake_send_pause(tgid, message, parse_mode, attachments, attachment_type):
            sent2.append(tgid)
            if tgid == 1001:
                mail_jobs.request_cancel(job2["id"], database=path)
            return True, None

        mailer.mailer_loop(
            database=path, send_fn=fake_send_pause, stop_after=1)
        paused = mail_jobs.get_job(job2["id"], database=path)
        _assert_eq(paused["status"], "paused", "paused after stop")
        _assert_eq(paused["sent"], 1, "one real send before pause")
        _assert_eq(paused["can_resume"], True, "can resume")
        _assert_eq(paused["remaining"] > 0, True, "remaining after pause")
        resumed = mail_jobs.resume(job2["id"], database=path)
        _assert_eq(resumed["status"], "queued", "resume queues")
        mailer.mailer_loop(
            database=path, send_fn=fake_send_pause, stop_after=1)
        done2 = mail_jobs.get_job(job2["id"], database=path)
        _assert_eq(done2["status"], "done", "finished after resume")
        _assert_eq(done2["sent"], 3, "all three sent once")
        real = [x for x in sent2 if x in (1001, 1002, 1003)]
        _assert_eq(real, [1001, 1002, 1003], "no double send")

        job3 = mail_jobs.enqueue(
            message="stale", to_creator_only=True, database=path)
        conn = __import__("app.admin_web.dbutil", fromlist=["connect"]).connect(path)
        conn.execute(
            "UPDATE admin_mail_jobs SET status = 'running' WHERE id = ?",
            (job3["id"],))
        conn.commit()
        conn.close()
        mail_jobs.recover_interrupted(database=path)
        recovered = mail_jobs.get_job(job3["id"], database=path)
        _assert_eq(recovered["status"], "queued", "stale running requeued")
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
        _assert_eq(
            users.json()["users"][0]["created_at"],
            "2024-03-15 10:30:00",
            "http registration date")
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
        stopped = client.post("/api/mail/%s/cancel" % job.json()["id"])
        _assert_eq(stopped.status_code, 200, "pause queued job")
        _assert_eq(stopped.json()["status"], "paused", "queued becomes paused")
        again = client.post("/api/mail/%s/resume" % job.json()["id"])
        _assert_eq(again.status_code, 200, "resume")
        _assert_eq(again.json()["status"], "queued", "back to queue")
    finally:
        config.db_path = original
        config.server = original_server


def test_diag_http(path):
    """/api/diag/*: its own read-only token, never the admin cookie."""
    original = config.db_path
    original_token = getattr(config, "diag_token", None)
    token = "d" * 40
    config.db_path = path
    auth._login_attempts.clear()
    db = SQLighter(path)
    try:  # cursor columns the prod schema has and this fixture skipped
        for table in ("user_channel_cs", "channels"):
            for column in ("last_guid", "last_date"):
                db.connection.execute(
                    "ALTER TABLE %s ADD COLUMN %s TEXT" % (table, column))
        db.connection.commit()
    finally:
        db.close()
    try:
        client = TestClient(app)
        config.diag_token = None
        _assert_eq(client.get("/api/diag/ping").status_code, 404, "diag off without a token")
        config.diag_token = "short"
        _assert_eq(
            client.get("/api/diag/ping", headers={"Authorization": "Bearer short"}).status_code,
            404, "diag off with a short token")
        config.diag_token = token
        _assert_eq(client.get("/api/diag/ping").status_code, 401, "no header")
        _assert_eq(
            client.get("/api/diag/ping", headers={"Authorization": "Bearer " + "x" * 40}).status_code,
            401, "wrong token")
        client.post("/api/login", json={"mail": "ops@yourcast.test", "password": "secret"})
        _assert_eq(client.get("/api/diag/audit").status_code, 401,
                   "admin session does not open diag")
        bearer = {"Authorization": "Bearer " + token}
        _assert_eq(TestClient(app).get("/api/stats", headers=bearer).status_code, 401,
                   "diag token does not open admin endpoints")
        ping = client.get("/api/diag/ping", headers=bearer)
        _assert_eq((ping.status_code, ping.text), (200, "ok\n"), "ping")
        audit = client.get("/api/diag/audit", headers=bearer)
        _assert_eq(audit.status_code, 200, "audit")
        _assert_eq("== Paying users" in audit.text, True, "audit is the report text")
        missed = client.get("/api/diag/missed", params={"tg": 1001, "hour": "2026-09-30 08"},
                            headers=bearer)
        _assert_eq(missed.status_code, 200, "missed report")
        _assert_eq("== Verdict for 2026-09-30 08:00:00" in missed.text, True, "hour honoured")
        _assert_eq(
            client.get("/api/diag/missed", params={"tg": 1001, "hour": "yesterday"},
                       headers=bearer).status_code, 400, "bad hour")
        _assert_eq(client.post("/api/diag/audit", headers=bearer).status_code, 405,
                   "diag is GET only")
        refetches = client.get("/api/diag/refetches", params={"hours": 6}, headers=bearer)
        _assert_eq(refetches.status_code, 200, "refetches summary")
        _assert_eq("== Full refetches after 304" in refetches.text, True, "refetches text")
        _assert_eq(client.get("/api/diag/refetches", params={"hours": 500},
                              headers=bearer).status_code, 400, "hours bounded")
        _assert_eq(client.get("/api/diag/refetches").status_code, 401, "refetches needs the token")
        _assert_eq(client.get("/api/diag/feed", params={"channel": 21}).status_code, 401,
                   "feed probe needs the token")
        errors = client.get("/api/diag/errors", params={"hours": 6}, headers=bearer)
        _assert_eq(errors.status_code, 200, "errors summary")
        _assert_eq("== ERR / WARN in role logs" in errors.text, True, "errors text")
        _assert_eq(client.get("/api/diag/errors", params={"q": "ab"},
                              headers=bearer).status_code, 400, "errors: q too short")
        _assert_eq(client.get("/api/diag/errors", params={"hours": 100},
                              headers=bearer).status_code, 400, "errors: hours bounded by the logs")
        _assert_eq(client.get("/api/diag/errors").status_code, 401, "errors needs the token")
        digest = client.get("/api/diag/digest", params={"hours": 6}, headers=bearer)
        _assert_eq(digest.status_code, 200, "digest stats")
        _assert_eq("== Nosub digests, last 6h" in digest.text, True, "digest stats text")
        _assert_eq(client.get("/api/diag/digest", params={"hours": 0},
                              headers=bearer).status_code, 400, "digest hours bounded")
        _assert_eq(client.get("/api/diag/feed", params={"channel": "x"},
                              headers=bearer).status_code, 422, "channel must be an id")
        pools = client.get("/api/diag/outbox", params={"hours": 6}, headers=bearer)
        _assert_eq(pools.status_code, 200, "outbox stats")
        _assert_eq("== send_outbox rows created in the last 6h" in pools.text, True,
                   "outbox stats text")
        _assert_eq(client.get("/api/diag/outbox").status_code, 401, "outbox needs the token")
        _assert_eq(client.get("/api/diag/outbox", params={"hours": 500},
                              headers=bearer).status_code, 400, "outbox hours bounded")
    finally:
        config.db_path = original
        config.diag_token = original_token
        auth._login_attempts.clear()


class _FakeResponse:
    def __init__(self, url, content):
        self.status_code = 200
        self.url = url
        self.headers = {"Content-Type": "application/rss+xml"}
        self.content = content
        self.history = []


def test_feed_probe():
    """GET /api/diag/feed explains an empty parse: a comment before <channel>."""
    from app.admin_web import diag
    import sqlite3
    path = os.path.join(tempfile.mkdtemp(prefix="yourcast_probe_"), "p.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE channels (id INTEGER PRIMARY KEY, itunes_id INTEGER, name TEXT,
            rss_link TEXT, last_guid TEXT, last_date TEXT);
        CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER,
            channel_id INTEGER, notify INTEGER);
        INSERT INTO channels VALUES (21, 160904630, 'TED Talks Daily',
            'http://old.example/ted', '__', '2026-09-29T15:00:00+0000');
        INSERT INTO channels VALUES (22, NULL, 'Fine', 'http://fine.example/rss', 'g_d_t', 'x');
        INSERT INTO user_channel_cs VALUES (1, 42, 21, 1);
        INSERT INTO user_channel_cs VALUES (2, 43, 21, 1);
    """)
    conn.commit()
    conn.close()
    feed = (b"<?xml version='1.0'?><rss version='2.0'><!-- generated by host -->"
            b"<channel><title>TED Talks Daily</title><item><title>Ep</title>"
            b"<guid>g1</guid><pubDate>Tue, 29 Sep 2026 15:00:00 GMT</pubDate>"
            b"<enclosure url='https://cdn.example/1.mp3'/></item></channel></rss>")
    urls = []

    def get(url):
        urls.append(url)
        return _FakeResponse(url, feed)

    conn = diag.connect_ro(path)
    try:
        text = diag.as_text(diag.feed_probe, conn, 21, get=get,
                            itunes=lambda _id: "https://new.example/ted")
    finally:
        conn.close()
    _assert_eq("[0] comment 'generated by host'" in text, True, "shows the comment first")
    _assert_eq("before the fix, the updater took [0] as the channel: comment" in text,
               True, "shows what the old parser picked")
    _assert_eq("the updater now takes (feed_xml.channel_element): element channel, items 1"
               in text, True, "shows what the parser picks now")
    _assert_eq("real <channel> at [1]: tag channel, title 'TED Talks Daily', items 1" in text,
               True, "shows the real channel and its items")
    _assert_eq(urls, ["http://old.example/ted", "https://new.example/ted"],
               "fetches rss_link and the differing iTunes feedUrl")
    _assert_eq("#21 TED Talks Daily: 2 listeners" in text, True, "counts empty-id channels")
    _assert_eq("#22" in text.split("latest id is empty")[1], False, "healthy channel not counted")


def test_payment_scripts_no_debug_side_effects():
    root = _ROOT
    crypto = open(
        os.path.join(root, "scripts/payment/cryptoBot.py"), encoding="utf-8"
    ).read()
    robo = open(
        os.path.join(root, "scripts/payment/subscription_income.py"),
        encoding="utf-8",
    ).read()
    _assert_eq(
        "notify = 0 where id = 1" in crypto.lower(),
        False,
        "cryptoBot must not flip notify on webhook error")
    _assert_eq(
        "'Key: ' + payment_p2" in robo,
        False,
        "robokassa must not telegram the merchant key")


class _Done:
    def __init__(self, stdout):
        self.stdout = stdout


def test_payment_webhooks():
    """The payment webhooks are Python at the paths the PHP listeners had (PHP 7.4 is open
    to PHP2Shell): the same script gets the same arguments, the answer is the listener's."""
    import base64
    import json as _json
    from app.admin_web import webhooks
    calls, out = [], [b"OK\n"]

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return _Done(out[0])

    saved = webhooks.subprocess.run
    webhooks.subprocess.run = runner
    try:
        client = TestClient(app)
        response = client.post(webhooks.CRYPTOBOT_PATH, content=b'{"update_type":"invoice_paid"}',
                               headers={"Crypto-Pay-Api-Signature": "abc"})
        _assert_eq((response.status_code, response.text), (200, "OK"),
                   "CryptoBot: no Origin, no admin session, the script's OK is OK")
        args = calls[-1][0]
        _assert_eq(args[1].endswith("scripts/payment/cryptoBot.py") and args[2] == config.BASE_DIR, True,
                   "the CryptoBot script from the bot's folder")
        _assert_eq((base64.b64decode(args[3]), _json.loads(base64.b64decode(args[4]))),
                   (b'{"update_type":"invoice_paid"}', {"Crypto-Pay-Api-Signature": "abc"}),
                   "the raw body and the signature header, base64, as listener.php passed them")
        out[0] = b"bad\n"
        _assert_eq(client.post(webhooks.CRYPTOBOT_PATH, content=b"x").status_code, 400,
                   "anything but OK from the script is 400")
        _assert_eq(_json.loads(base64.b64decode(calls[-1][0][4])), {}, "no signature: an empty object")

        out[0] = b"OK42\n"
        response = client.get(webhooks.ROBOKASSA_PATH + "?OutSum=5.0&InvId=42&SignatureValue=S",
                              headers={"X-Real-IP": webhooks.ROBOKASSA_IPS[0]})
        _assert_eq((response.status_code, response.text), (200, "OK42\n"),
                   "Robokassa from its address: the script's answer as it is")
        args = calls[-1][0]
        _assert_eq((args[1].endswith("scripts/payment/subscription_income.py"), args[3]),
                   (True, config.BASE_DIR), "the Robokassa script, params first, then the bot's folder")
        _assert_eq(_json.loads(base64.b64decode(args[2])), {"OutSum": "5.0", "InvId": "42", "SignatureValue": "S"},
                   "the query parameters as a JSON object")
        before = len(calls)
        response = client.get(webhooks.ROBOKASSA_PATH + "?InvId=1", headers={"X-Real-IP": "203.0.113.9"})
        _assert_eq((response.status_code, len(calls)), (403, before),
                   "Robokassa from another address: 403, the script never runs")
        _assert_eq(client.get(webhooks.CRYPTOBOT_PATH).status_code, 405, "CryptoBot posts only")
    finally:
        webhooks.subprocess.run = saved


def test_nginx_php_snippet():
    """CD swaps the site's php-fpm location for the snippet: no request reaches PHP 7.4."""
    sys.path.insert(0, os.path.join(_ROOT, "deploy"))
    import ensure_nginx_php
    site = ("server {\n    root /home/yourcast/server;\n    location ~ \\.php$ {\n"
            "        include snippets/fastcgi-php.conf;\n"
            "        fastcgi_pass unix:/run/php/php7.4-fpm.sock;\n    }\n}\n") * 2
    path = os.path.join(tempfile.mkdtemp(prefix="yourcast_nginx_"), "yourcast")
    open(path, "w").write(site)
    _assert_eq(ensure_nginx_php.ensure(path), True, "the php-fpm locations are replaced")
    text = open(path).read()
    _assert_eq((text.count(ensure_nginx_php.MARKER), "fastcgi_pass" in text), (2, False),
               "both server blocks include the snippet, none passes to php-fpm")
    _assert_eq(ensure_nginx_php.ensure(path), False, "a second run changes nothing")
    snippet = open(os.path.join(_ROOT, "deploy", "nginx-yourcast-php.conf")).read()
    _assert_eq(("fastcgi_pass" in snippet, "location ~ \\.php$ { return 404; }" in snippet,
                "location ~ /\\. { deny all; }" in snippet),
               (False, True, True), "the snippet sends nothing to PHP, hides .git, 404s other .php")
    from app.admin_web import webhooks
    for path_ in (webhooks.CRYPTOBOT_PATH, webhooks.ROBOKASSA_PATH):
        _assert_eq("location = %s {" % path_ in snippet, True, "nginx proxies %s to the admin" % path_)
    for ip in webhooks.ROBOKASSA_IPS:
        _assert_eq("allow %s;" % ip in snippet, True, "nginx lets Robokassa's %s in" % ip)


def main():
    test_auth_roundtrip()
    test_login_rate_limit()
    test_payment_scripts_no_debug_side_effects()
    test_payment_webhooks()
    test_nginx_php_snippet()
    test_feed_probe()
    tmpdir = tempfile.mkdtemp(prefix="yourcast_admin_web_")
    path = os.path.join(tmpdir, "admin.db")
    _prepare(path)
    test_queries_and_mailer(path)
    test_http(path)
    test_diag_http(path)
    print("all admin_web checks passed")


if __name__ == "__main__":
    main()
