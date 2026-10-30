# -*- coding: utf-8 -*-
"""D-3 Relay reminder: once per period. Under the plan's text: the user's podcasts
that stop coming as files, the recap, and for a Relay trial nobody paid for the
first month at the win-back discount (its invoice first, the Stars page and
change-plan still next to it); the plan-off notice says the same. Temp DB only.

Run from the repo root: python app/jobs/test_relay_remind.py
"""
import os
import sqlite3
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs import relay_remind  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _schema(conn):
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegramId INTEGER NOT NULL UNIQUE,
            lang char(15),
            deleted_at TEXT
        );
        CREATE TABLE tariffs (
            id INTEGER PRIMARY KEY,
            level INTEGER NOT NULL,
            price INTEGER NOT NULL,
            notify_count INTEGER NOT NULL
        );
        CREATE TABLE user_tariff_cs (
            id INTEGER PRIMARY KEY,
            uid INTEGER NOT NULL,
            tariff_id INTEGER NOT NULL,
            balance INTEGER,
            notify_count INTEGER,
            time_left INTEGER
        );
    """)
    conn.execute(
        "INSERT INTO tariffs (id, level, price, notify_count) VALUES (3, 3, 500, -1)")
    conn.commit()


def _add_user(conn, telegram_id, time_left, deleted_at=None, lang="en", balance=0, tariff_id=3):
    conn.execute(
        "INSERT INTO users (telegramId, lang, deleted_at) VALUES (?, ?, ?)",
        (telegram_id, lang, deleted_at))
    uid = conn.execute(
        "SELECT id FROM users WHERE telegramId = ?", (telegram_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO user_tariff_cs "
        "(uid, tariff_id, balance, notify_count, time_left) "
        "VALUES (?, ?, ?, -1, ?)",
        (uid, tariff_id, balance, time_left))
    conn.commit()


def _plans(sent):
    """Bronze, Silver and Relay users all expire: each is told about its own plan."""
    from app.i18n.messages import get_message
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        db = SQLighter(path)
        try:
            _schema(db.connection)
            db.connection.execute(
                "INSERT INTO tariffs (id, level, price, notify_count) VALUES (1, 1, 100, 100)")
            db.connection.execute(
                "INSERT INTO tariffs (id, level, price, notify_count) VALUES (2, 2, 300, 500)")
            db.connection.commit()
            _add_user(db.connection, 201, 48, tariff_id=1, lang="ru")
            _add_user(db.connection, 202, 48, tariff_id=2, lang="en")
            _add_user(db.connection, 203, 48, tariff_id=3, lang="en")
            _add_user(db.connection, 204, 48, tariff_id=1, lang="en", balance=100)  # renewed by the tick
        finally:
            db.close()
        del sent[:]
        count = relay_remind.send_relay_d3_reminders(database=path)
        by_user = {row[0]: row for row in sent}
        _assert_eq(count, 3, "Bronze, Silver and Relay users that will expire are reminded")
        _assert_eq(204 in by_user, False, "a Bronze user whose balance renews it is not reminded")
        _assert("«Бронза»" in by_user[201][1] and "Relay заканчивается" not in by_user[201][1],
                "a Bronze user is told Bronze ends, not Relay (ru)")
        _assert('"Silver"' in by_user[202][1] and "Relay ends" not in by_user[202][1],
                "a Silver user is told Silver ends, not Relay (en)")
        _assert_eq(by_user[203][1], get_message("relay_trial_ending", "en") % 2,
                   "the Relay text is exactly what it was")
        for chat_id in (201, 202, 203):
            _assert_eq([row[0]["callback_data"]["tp"] for row in by_user[chat_id][2][:2]], ["bs_stars", "bs_trfs"],
                       "%s: still Stars first, change-plan next to it" % chat_id)
    finally:
        os.remove(path)


def _recap(sent):
    """Under the plan's text, what the plan brought: the Relay text stays as it is, first."""
    import time
    from app.i18n.messages import get_message
    from db import ai, usage
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        db = SQLighter(path)
        try:
            _schema(db.connection)
            db.connection.execute(
                "CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER, "
                "channel_id INTEGER, notify INTEGER)")
            db.connection.executemany(
                "INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) VALUES (?, ?, ?)",
                [(301, 1, 1), (301, 2, 1), (301, 3, 0), (302, 1, 1)])
            db.connection.commit()
            _add_user(db.connection, 301, 48, lang="ru")
            _add_user(db.connection, 302, 48, lang="en")
        finally:
            db.close()
        now = time.time()
        for i in range(3):
            usage.record_deliveries([301], 'circle', 'https://a/%d.mp3' % i, database=path, at=now - 3600)
        usage.record_deliveries([301], 'rec', 'https://a/r.mp3', database=path, at=now - 3600)
        usage.record_deliveries([301], 'rec', 'https://a/old.mp3', database=path, at=now - 40 * 86400)
        done, _ = ai.enqueue(301, 'ep', 'original', 600, database=path)
        ai.finish(done, 'done', database=path)
        failed, _ = ai.enqueue(301, 'ep2', 'original', 600, database=path)
        ai.finish(failed, 'failed', database=path)
        _assert_eq(relay_remind.recap_counts(301, database=path), {'episodes': 4, 'summaries': 1, 'shows': 2},
                   "the last 30 days' episodes, done summaries, podcasts on auto-delivery")

        del sent[:]
        relay_remind.send_relay_d3_reminders(database=path)
        by_user = {row[0]: row[1] for row in sent}
        relay = get_message("relay_trial_ending", "ru") % 2
        _assert(by_user[301].startswith(relay + "\n\n"), "the Relay text stays as it is, first")
        _assert_eq(by_user[301][len(relay) + 2:].split("\n"),
                   [get_message("planRecap", "ru"), "🎧 выпусков в чате: 4", "🎙 подкастов на автодоставке: 2",
                    "📝 ИИ-пересказов: 1"], "then what the plan brought")
        _assert_eq(by_user[302], get_message("relay_trial_ending", "en") % 2,
                   "nothing delivered yet: no recap, the text alone")

        # The ledger started on 2026-10-21: younger than the window, its count is
        # not the user's (a two-week trial read "1 episode"), unless the user is
        # younger still.
        conn = sqlite3.connect(path)
        conn.execute("DELETE FROM usage_events WHERE at < ?", (now - 30 * 86400,))
        conn.execute("UPDATE users SET created_at = datetime(?, 'unixepoch') WHERE telegramId = 301",
                     (now - 10 * 86400,))
        conn.commit()
        conn.close()
        _assert_eq(relay_remind.recap_counts(301, database=path), {'episodes': None, 'summaries': 1, 'shows': 2},
                   "a ledger younger than the window and the user: no episode count")
        _assert_eq(relay_remind.recap_text(301, "ru", database=path).split("\n"),
                   [get_message("planRecap", "ru"), "🎙 подкастов на автодоставке: 2", "📝 ИИ-пересказов: 1"],
                   "the recap goes without the episodes line")
        usage.record_deliveries([302], 'circle', 'https://a/0.mp3', database=path, at=now - 3600)
        _assert_eq(relay_remind.recap_text(302, "en", database=path), "",
                   "no count and no summary: no recap")
        usage.record_deliveries([999], 'rec', 'https://a/x.mp3', database=path, at=now - 5 * 86400)
        conn = sqlite3.connect(path)
        conn.execute("UPDATE users SET created_at = datetime(?, 'unixepoch') WHERE telegramId = 301",
                     (now - 2 * 86400,))
        conn.commit()
        conn.close()
        _assert_eq(relay_remind.recap_counts(301, database=path)['episodes'], 4,
                   "a user who joined after the ledger started: the count is whole")
    finally:
        os.remove(path)


def _local(year, month, day):
    import datetime
    return datetime.datetime(year, month, day, 12).timestamp()


def _trial_end(sent):
    """The loss line and the trial's offer, in D-3 and in the plan-off notice."""
    from unittest.mock import patch
    from app.i18n.messages import get_message
    from app.service import analytics_events
    from app.service.payment import plan_end
    from app.service.payment.offers import OFFER_SENT_FLAG, WINBACK_OFFER, offer_open
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    events = []

    def track(telegram_id, event, properties=None, database=None, **_kw):
        events.append((telegram_id, event, properties))
        return True
    try:
        db = SQLighter(path)
        try:
            _schema(db.connection)
            db.connection.executescript("""
                INSERT INTO tariffs (id, level, price, notify_count) VALUES (1, 1, 100, 100);
                CREATE TABLE channels (id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER,
                    channel_id INTEGER, notify INTEGER);
                CREATE TABLE payment_history (id INTEGER PRIMARY KEY, user_id INTEGER, service_type TEXT,
                    invoice_id TEXT, invoice_hash TEXT, status TEXT, amount INTEGER, datetime TEXT);
                INSERT INTO channels VALUES (21, 'TED Talks Daily'), (5, 'Darknet &amp; Diaries'),
                    (6, 'Lex <i>Fridman</i> & Co'), (7, 'Hard Fork'), (8, 'Huberman Lab');
            """)
            # 401: the welcome show and four of their own (newest last); 7 is muted
            db.connection.executemany(
                "INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) VALUES (?, ?, ?)",
                [(401, 21, 1), (401, 7, 0), (401, 8, 1), (401, 6, 1), (401, 5, 1),
                 (402, 21, 1), (403, 21, 1), (403, 6, 1), (404, 5, 1)])
            db.connection.commit()
            _add_user(db.connection, 401, 60, lang="ru")      # a Relay trial
            _add_user(db.connection, 402, 60, lang="en")      # paid once: no discount
            _add_user(db.connection, 403, 60, lang="en", tariff_id=1)  # a Bronze trial: Relay's terms are not its own
            _add_user(db.connection, 404, 60, lang="en")      # the weekly digest is off
            uid = db.connection.execute("SELECT id FROM users WHERE telegramId = 402").fetchone()[0]
            db.connection.execute("INSERT INTO payment_history (user_id, status, amount) VALUES (?, 'paid', 500)",
                                  (uid,))
            db.connection.commit()
        finally:
            db.close()
        SQLighter(path).close()  # the users columns the bot adds (digest, flags) now that the table exists
        conn = sqlite3.connect(path)
        conn.execute("UPDATE users SET nosub_digest_enabled = 0 WHERE telegramId = 404")
        conn.commit()
        conn.close()

        _assert_eq(plan_end.user_shows(401, database=path),
                   (["<b>Darknet &amp; Diaries</b>", "<b>Lex Fridman &amp; Co</b>"], 4),
                   "the user's own shows first, newest first, escaped; the welcome show counts last")
        _assert_eq(plan_end.shows_text(["<b>A</b>"], 1, "en"), "<b>A</b>", "one show")
        _assert_eq(plan_end.shows_text(["<b>A</b>", "<b>B</b>"], 2, "ru"), "<b>A</b> и <b>B</b>", "two shows")
        _assert_eq(plan_end.usd(350), "$3.50", "cents")
        _assert_eq(plan_end.usd(500), "$5", "a round price")
        _assert_eq(plan_end.date_text(_local(2026, 11, 8), "ru"), "8 ноября", "the day the plan ends, ru")
        _assert_eq(plan_end.date_text(_local(2026, 11, 8), "en"), "Nov 8", "and en")
        _assert_eq(plan_end.loss_text(999, "en", database=path), ("", 0), "no podcasts: no line")

        del sent[:]
        with patch.object(analytics_events, 'track', track):
            count = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(count, 4, "every plan that will expire is reminded")
        by_user = {row[0]: row for row in sent}
        text, markup = by_user[401][1], by_user[401][2]
        relay = get_message("relay_trial_ending", "ru") % 2
        date = plan_end.date_text(plan_end.ends_at(60), "ru")
        loss = ("🎙 С %s новые выпуски <b>Darknet &amp; Diaries</b>, <b>Lex Fridman &amp; Co</b> и ещё 2 "
                "будут приходить текстом раз в неделю, а не файлом." % date)
        offer = "🎁 Первый месяц Relay со скидкой 30%: $3.50 вместо $5."
        _assert_eq(text, relay + "\n\n" + loss + "\n\n" + offer,
                   "the Relay text as it is, first; then the shows that stop coming as files; then the offer")
        _assert_eq(markup[0][0], {"text": "⭐ Relay −30%: первый месяц за $3.50",
                                  "callback_data": {"tp": "bs_stars_pay", "o": WINBACK_OFFER, "s": "d3"}},
                   "the discounted month's invoice in one tap, first")
        _assert_eq([row[0]["callback_data"] for row in markup[1:3]],
                   [{"tp": "bs_stars", "s": "d3"}, {"tp": "bs_trfs", "s": "d3"}],
                   "the Stars page of every plan and change-plan still next to it, tagged for Amplitude")
        _assert_eq(markup[-1][0]["callback_data"], {"tp": "bs_stars_sub"}, "the Stars subscription stays last")
        _assert(offer_open(401, WINBACK_OFFER, database=path), "the offer is open: its invoice will be sold")
        _assert("🎁" not in by_user[402][1] and by_user[402][2][0][0]["callback_data"]["tp"] == "bs_stars",
                "a user who paid before renews at the price: no discount")
        _assert("🎁" not in by_user[403][1] and "<b>Lex Fridman &amp; Co</b> and <b>TED Talks Daily</b>" in by_user[403][1],
                "a Bronze plan: its shows are named, Relay's discount is not offered")
        _assert_eq(offer_open(403, WINBACK_OFFER, database=path), False, "and stays closed")
        _assert("of <b>Darknet &amp; Diaries</b> will stop arriving as files." in by_user[404][1]
                and "will come as a weekly" not in by_user[404][1],
                "the digest is off: the line promises no weekly text")
        reminders = {chat: props for chat, event, props in events if event == 'plan_reminder_sent'}
        _assert_eq(reminders[401], {'level': 3, 'days_left': 2, 'paid_before': False, 'offer': True, 'shows': 4},
                   "D-3 is counted with its offer")
        _assert_eq((reminders[402]['paid_before'], reminders[402]['offer']), (True, False), "a payer's without one")

        # the plan-off notice (needs the bot's requirements: balance_watcher sends through telebot)
        try:
            from app.jobs import balance_watcher
        except ModuleNotFoundError as e:
            print("skip plan-off notice (%s)" % e.name)
            return
        conn = sqlite3.connect(path)
        conn.execute("UPDATE users SET flags = json_remove(flags, '$.%s') WHERE telegramId = 401" % OFFER_SENT_FLAG)
        conn.commit()
        conn.close()
        npu = {'telegramId': 401, 'lang': 'en', 'tlevel': 3, 'tprice': 500, 'tid': 3, 'balance': 0}
        message, offered = balance_watcher.plan_off_message(npu, None, database=path)
        _assert(offered and message['text'].startswith(
                    get_message("tariff_cannot_be_prolonged_by_daemon", "en") + "\n\n🎙 New episodes of "
                    "<b>Darknet &amp; Diaries</b>, <b>Lex Fridman &amp; Co</b> and 2 more now come as a weekly "
                    "text reminder, not as files."),
                "plan-off: the Relay text as it is, then the shows that no longer come as files")
        _assert(message['text'].endswith("🎁 Your first month of Relay is 30% off: $3.50 instead of $5."),
                "and the trial's offer last")
        _assert_eq([row[0]["callback_data"] for row in message['reply_markup'][:3]],
                   [{"tp": "bs_stars_pay", "o": WINBACK_OFFER, "s": "po"}, {"tp": "bs_stars", "s": "po"},
                    {"tp": "bs_trfs", "s": "po"}], "the offer's invoice, the Stars page, change-plan")
        _assert(offer_open(401, WINBACK_OFFER, database=path), "the plan-off notice opens the offer too")
        npu = {'telegramId': 402, 'lang': 'en', 'tlevel': 3, 'tprice': 500, 'tid': 3, 'balance': 0}
        message, offered = balance_watcher.plan_off_message(npu, None, database=path)
        _assert(not offered and message['reply_markup'][0][0]["callback_data"] == {"tp": "bs_stars", "s": "po"},
                "a payer's plan-off: no discount, Stars first as before")
    finally:
        os.remove(path)


def main():
    _assert_eq(relay_remind.days_left_label(72), 3, "72h is 3 days")
    _assert_eq(relay_remind.days_left_label(25), 1, "25h floors to 1")
    _assert_eq(relay_remind.days_left_label(5), 1, "under a day is still 1")
    _assert_eq(
        relay_remind.should_send_d3(72, False), True, "first entry sends")
    _assert_eq(
        relay_remind.should_send_d3(72, True), False, "already sent skips")
    _assert_eq(
        relay_remind.should_send_d3(80, False), False, "outside window skips")
    _assert_eq(
        relay_remind.should_send_d3(0, False), False, "expired skips")

    sent = []

    def fake_sender(chat_id, messages, **_kwargs):
        sent.append((chat_id, messages[0]["text"], messages[0].get("reply_markup")))
        return True

    relay_remind._send = fake_sender

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        db = SQLighter(path)
        try:
            _schema(db.connection)
            _add_user(db.connection, 101, 50)
            _add_user(db.connection, 102, 200)
            _add_user(db.connection, 103, 10, deleted_at="2026-01-01")
            _add_user(db.connection, 104, 0)
            # balance covers the price (500): the tick renews it, "Relay ends
            # in 2 days, pay $5" would be false
            _add_user(db.connection, 105, 50, balance=31246)
            # short by a cent: will expire, gets the reminder
            _add_user(db.connection, 106, 60, balance=499)
        finally:
            db.close()

        first = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(first, 2, "in-window live users that will expire")
        _assert_eq([row[0] for row in sent], [101, 106], "reminded the in-window users")
        _assert_eq(105 in [row[0] for row in sent], False,
                   "balance covers the renewal: not told Relay ends")
        _assert("Relay" in sent[0][1] or "ends" in sent[0][1].lower()
                or "days" in sent[0][1].lower(),
                "D-3 copy is about Relay ending")
        markup = sent[0][2]
        nudge_types = [row[0]["callback_data"]["tp"] for row in markup[:2]]
        _assert_eq(nudge_types[0], "bs_stars", "D-3 still offers Stars")
        _assert_eq(nudge_types[1], "bs_trfs", "D-3 still offers change-plan")
        _assert("start%3D101" in markup[2][0]["url"],
                "D-3 offers to invite a friend with the user's own link")
        _assert_eq(markup[3][0]["callback_data"], {"tp": "bs_stars_sub"},
                   "and the plan by a Stars subscription below it")

        second = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(second, 0, "second hourly tick does not spam")

        relay_remind.clear_relay_d3_sent(101, database=path)
        third = relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq(third, 1, "renewal clears the flag")
        _assert_eq(sent[-1][0], 101, "and only that user is reminded again")

        # A Stars subscription renews the plan by itself: "pay or it ends" would be false.
        conn = sqlite3.connect(path)
        _add_user(conn, 107, 40)
        _add_user(conn, 108, 40)
        conn.execute("UPDATE users SET flags = json_object('stars_sub_until', ?) WHERE telegramId = 107",
                     (time.time() + 86400,))
        conn.execute("UPDATE users SET flags = json_object('stars_sub_until', ?) WHERE telegramId = 108",
                     (time.time() - 86400,))
        # a subscription that pays for this plan at its price (107 has neither noted: sold before)
        _add_user(conn, 109, 40)
        _add_user(conn, 110, 40)
        _add_user(conn, 111, 40)
        for telegram_id, plan, cents in ((109, 3, 500), (110, 1, 100), (111, 3, 300)):
            conn.execute("UPDATE users SET flags = json_object('stars_sub_until', ?, 'stars_sub_plan', ?, "
                         "'stars_sub_cents', ?) WHERE telegramId = ?",
                         (time.time() + 86400, plan, cents, telegram_id))
        conn.commit()
        conn.close()
        del sent[:]
        relay_remind.send_relay_d3_reminders(database=path)
        _assert_eq([row[0] for row in sent], [108, 110, 111],
                   "a running Stars subscription for this plan gets no D-3; one whose period is over, "
                   "one paying for another plan (Bronze's $1 on Relay) and one below today's price do")
    finally:
        os.remove(path)

    _plans(sent)
    _recap(sent)
    _trial_end(sent)
    print("all relay_remind checks passed")


if __name__ == "__main__":
    main()
