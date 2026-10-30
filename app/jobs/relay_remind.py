# -*- coding: utf-8 -*-
"""Once-per-period Relay reminder when time_left first enters 72 hours.

Runs from the existing hourly balance_watcher. Does not touch payment apply.
Under the plan's text: the user's podcasts that stop coming as files on that
day (plan_end.loss_text), what the plan brought (recap_text): what stops is
easier to weigh when it is counted, and for a Relay trial the first month at
the win-back discount (plan_end.trial_offer), its invoice above the usual rows.
"""
import sqlite3
import time

from app.i18n.messages import get_message
from app.service import analytics_events
from app.service.payment import plan_end
from app.service.payment.referral import invite_row
# relay_nudge_markup is imported from here by the digest and the balance watcher
from app.service.payment.storefront import plan_ending_text, relay_nudge_markup  # noqa: F401
from app.service.payment import stars_subscription
from config import db_path
from db import ai, runtime_kv, usage
from db.connection import connect_sqlite
from db.sqliteAdapter import SQLighter
from lib.tools.logger import logger

RELAY_D3_HOURS = 72
RECAP_DAYS = 30  # one plan period: a trial (14 days) fits in it


def d3_kv_key(telegram_id) -> str:
    return "relay_d3_sent_" + str(telegram_id)


def days_left_label(time_left_hours) -> int:
    hours = int(time_left_hours or 0)
    if hours <= 0:
        return 0
    return max(1, hours // 24)


def should_send_d3(time_left_hours, already_sent) -> bool:
    hours = int(time_left_hours or 0)
    if hours <= 0 or hours > RELAY_D3_HOURS:
        return False
    return not bool(already_sent)


def d3_already_sent(telegram_id, database=None) -> bool:
    value = runtime_kv.get_kv(d3_kv_key(telegram_id), database=database)
    return value is not None and value != ""


def mark_d3_sent(telegram_id, database=None):
    runtime_kv.set_kv(d3_kv_key(telegram_id), "1", database=database)


def clear_relay_d3_sent(telegram_id, database=None):
    if telegram_id is None:
        return
    runtime_kv.delete_kv(d3_kv_key(telegram_id), database=database)


def _ledger_covers(connection, telegram_id, since) -> bool:
    """The usage ledger started on 2026-10-21; deliveries before it were never
    counted. Its count is the user's only when it covers the window, or the
    user's whole time with the bot: a two-week trial would read "1 episode"."""
    first = connection.execute("SELECT MIN(at) FROM usage_events").fetchone()[0]
    if first is None or first <= since:
        return True
    try:
        joined = connection.execute(
            "SELECT CAST(strftime('%s', created_at) AS REAL) FROM users WHERE telegramId = ?",
            (int(telegram_id),)).fetchone()
    except sqlite3.OperationalError:  # a database without users.created_at
        return False
    return bool(joined and joined[0] is not None and first <= joined[0])


def recap_counts(telegram_id, database=None, now=None) -> dict:
    """In the last RECAP_DAYS: episodes delivered (clicks and automatic, the usage ledger;
    None when the ledger is younger than that and than the user), summaries received
    (done, cached ones too), and podcasts on auto-delivery now."""
    since = (time.time() if now is None else now) - RECAP_DAYS * 86400
    database = db_path if database is None else database
    usage.connect(database).close()
    ai.connect(database).close()
    connection = connect_sqlite(database)
    try:
        episodes = None
        if _ledger_covers(connection, telegram_id, since):
            episodes = int(connection.execute(
                "SELECT COUNT(*) FROM usage_events WHERE user_id = ? AND kind IN ('rec', 'circle') AND at >= ?",
                (int(telegram_id), since)).fetchone()[0])
        summaries = connection.execute(
            "SELECT COUNT(*) FROM ai_requests WHERE chat_id = ? AND status = 'done' AND created_at >= ?",
            (int(telegram_id), since)).fetchone()[0]
        shows = connection.execute(
            "SELECT COUNT(*) FROM user_channel_cs WHERE user_telegram_id = ? AND notify = 1",
            (int(telegram_id),)).fetchone()[0]
    finally:
        connection.close()
    return {'episodes': episodes, 'summaries': int(summaries), 'shows': int(shows)}


def recap_text(telegram_id, lang, database=None, now=None) -> str:
    """The recap under the D-3 text, '' when the plan brought nothing yet (or nothing the
    ledger can count: no number at all beats a number too small). Never fails the reminder."""
    try:
        counts = recap_counts(telegram_id, database, now)
    except Exception as e:
        logger.warn("relay_d3 recap:", telegram_id, type(e).__name__, e)
        return ''
    if not counts['episodes'] and not counts['summaries']:
        return ''
    lines = [get_message('planRecap', lang)]
    for key, message in (('episodes', 'planRecapEpisodes'), ('shows', 'planRecapShows'),
                         ('summaries', 'planRecapSummaries')):
        if counts[key]:
            lines.append(get_message(message, lang).format(n=counts[key]))
    return '\n'.join(lines)


def _send(chat_id, messages):
    from lib.telegram.general.message_master import outer_sender
    return outer_sender(chat_id, messages)


def send_relay_d3_reminders(database=None):
    db_file = db_path if database is None else database
    db = SQLighter(db_file)
    try:
        users = db.get_users_nearing_expiry(RELAY_D3_HOURS)
    finally:
        db.close()

    sent = 0
    for user in users:
        telegram_id = user["telegramId"]
        if not telegram_id:
            continue
        if not should_send_d3(
                user["time_left"], d3_already_sent(telegram_id, database=db_file)):
            continue
        if stars_subscription.covers(telegram_id, user["tariff_id"], user["price"], database=db_file):
            continue  # the subscription's next charge renews the plan: nothing to pay by hand
        lang = user["lang"] if user["lang"] else "en"
        days = days_left_label(user["time_left"])
        text = plan_ending_text(user["level"], days, lang)
        loss, shows = plan_end.loss_text(
            telegram_id, lang, ends_at=plan_end.ends_at(user["time_left"]), database=db_file)
        recap = recap_text(telegram_id, lang, database=db_file)
        offer, offer_row = plan_end.trial_offer(
            telegram_id, user["level"], user["price"], lang, analytics_events.REMINDER_SOURCE, database=db_file)
        for part in (loss, recap, offer):
            if part:
                text += "\n\n" + part
        # a friend's sign-up adds days: the cheapest way to keep the plan
        markup = relay_nudge_markup(lang, extra_row=invite_row(telegram_id, lang),
                                    source=analytics_events.REMINDER_SOURCE)
        # the user's own plan by a Stars subscription: below Stars, change-plan and the invite
        markup.append(stars_subscription.offer_row(lang))
        if offer_row:
            # the discounted month in one tap; the Stars page of every plan stays next to it
            markup.insert(0, offer_row)
        try:
            _send(telegram_id, [{
                "type": "text",
                "text": text,
                "reply_markup": markup,
            }])
        except Exception as e:
            logger.err("relay_d3:", telegram_id, e)
            continue
        mark_d3_sent(telegram_id, database=db_file)
        analytics_events.plan_reminder_sent(
            telegram_id, user["level"], days, bool(offer_row), shows, database=db_file)
        sent += 1
    return sent
