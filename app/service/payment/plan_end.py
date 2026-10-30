# -*- coding: utf-8 -*-
"""What the end of a plan says under the plan's own text (D-3 and the plan-off
notice): the user's podcasts that stop arriving as files, and, at the end of a
trial, the first month of Relay at the win-back discount.

The plan's text stays as it is (Relay's is tuned copy): these are lines under
it. A trial whose plan ends is mostly a chat that stopped reading (27 trials
ended in October 2026, 3 tapped anything in the week after): the discount used
to wait for the first win-back message a week later, when they were gone.

The offer is the win-back one (offers.WINBACK_OFFER, once per user): sent here,
it opens (offers.mark_offer_sent) and the win-back messages repeat it. Only a
Relay trial nobody paid for gets it: a payer renews at the price, and Bronze or
Silver cannot buy Relay's terms while they run.
Locks: python app/jobs/test_relay_remind.py, python app/jobs/test_winback.py.
"""
import datetime
import time

from app.i18n.messages import get_message
from app.service.payment.offers import (
    WINBACK_OFFER, WINBACK_OFFER_FLAG, charged_cents, mark_offer_sent)
from app.service.payment.storefront import RELAY_INVOICE_CALLBACK, SHOWCASE_TARIFF_LEVEL
from config import db_path, winback_offer_discount
from db.connection import connect_sqlite
from lib.markup import telegram_html
from lib.tools.logger import logger

WELCOME_CHANNEL_ID = 21  # the show welcomeModule subscribes every newcomer to
NAMED_SHOWS = 2
NAME_CHARS = 48  # a show name longer than this is cut, the line stays readable


def usd(cents) -> str:
    """$5, $3.50."""
    cents = int(cents)
    return "$%d" % (cents // 100) if cents % 100 == 0 else "$%.2f" % (cents / 100.0)


def _name(raw) -> str:
    name = telegram_html.plain_text(raw).strip()
    if len(name) > NAME_CHARS:
        name = name[:NAME_CHARS - 1].rstrip() + "…"
    return "<b>%s</b>" % telegram_html.escape(name) if name else ""


def user_shows(telegram_id, database=None):
    """([names of up to NAMED_SHOWS podcasts on auto-delivery, as HTML], how many there are).
    The user's own come first, the newest subscription first; the welcome show last."""
    connection = connect_sqlite(db_path if database is None else database)
    try:
        rows = connection.execute(
            "SELECT c.name FROM user_channel_cs s JOIN channels c ON c.id = s.channel_id "
            "WHERE s.user_telegram_id = ? AND s.notify = 1 "
            "ORDER BY s.channel_id = ?, s.id DESC", (int(telegram_id), WELCOME_CHANNEL_ID)).fetchall()
    finally:
        connection.close()
    names = [name for name in (_name(row[0]) for row in rows) if name]
    return names[:NAMED_SHOWS], len(rows)


def shows_text(names, total, language_code) -> str:
    """"A", "A and B", "A, B and 3 more"."""
    if not names:
        return ""
    if total > len(names):
        return get_message("planLossShowsMore", language_code).format(
            shows=", ".join(names), n=total - len(names))
    if len(names) == 2:
        return get_message("planLossShowsTwo", language_code).format(a=names[0], b=names[1])
    return names[0]


def date_text(stamp, language_code) -> str:
    """'8 ноября', 'Nov 8': the day the plan ends."""
    day = datetime.datetime.fromtimestamp(stamp)
    month = get_message("planLossMonths", language_code).split(",")[day.month - 1].strip()
    return get_message("planLossDate", language_code).format(d=day.day, m=month)


def digest_on(telegram_id, database=None) -> bool:
    """The weekly digest goes to this chat (the "text once a week" the line promises)."""
    connection = connect_sqlite(db_path if database is None else database)
    try:
        row = connection.execute("SELECT nosub_digest_enabled FROM users WHERE telegramId = ?",
                                 (int(telegram_id),)).fetchone()
    finally:
        connection.close()
    return row is None or row[0] is None or bool(row[0])


def loss_text(telegram_id, language_code, ends_at=None, database=None):
    """(line, podcasts on auto-delivery): the user's podcasts that stop coming as files,
    on ends_at (D-3), or now (the plan is off) when it is None. ('', 0) without podcasts
    on auto-delivery or when they cannot be read: never fails the notice."""
    try:
        names, total = user_shows(telegram_id, database)
        shows = shows_text(names, total, language_code)
        if not shows:
            return "", total
        key = "planLossAt" if ends_at is not None else "planLossNow"
        if not digest_on(telegram_id, database):
            key += "Muted"
        date = date_text(ends_at, language_code) if ends_at is not None else ""
        return get_message(key, language_code).format(shows=shows, date=date), total
    except Exception as e:
        logger.warn("plan end loss line:", telegram_id, type(e).__name__, e)
        return "", 0


def trial_offer_due(telegram_id, level, database=None) -> bool:
    """A Relay trial nobody paid for that has not spent the offer."""
    if int(level or 0) != SHOWCASE_TARIFF_LEVEL or not winback_offer_discount:
        return False
    from db.sqliteAdapter import SQLighter
    from db.tariff_rows import paid_for_days
    database = db_path if database is None else database
    if paid_for_days(telegram_id, database):
        return False
    db = SQLighter(database)
    try:
        return not db.get_user_flag(telegram_id, WINBACK_OFFER_FLAG)
    finally:
        db.close()


def trial_offer(telegram_id, level, price_cents, language_code, source, database=None, now=None):
    """(line, invoice row) of the first month at the discount for a trial's end, the
    offer opened; ('', None) when it is not for this user or cannot be read."""
    try:
        if not trial_offer_due(telegram_id, level, database):
            return "", None
        mark_offer_sent(telegram_id, now=now, database=database)
    except Exception as e:
        logger.warn("plan end offer:", telegram_id, type(e).__name__, e)
        return "", None
    price = usd(charged_cents(price_cents, winback_offer_discount))
    line = get_message("trialOfferLine", language_code).format(
        discount=winback_offer_discount, price=price, full=usd(price_cents))
    row = [{"text": get_message("trialOfferButton", language_code).format(
                discount=winback_offer_discount, price=price),
            "callback_data": dict(RELAY_INVOICE_CALLBACK, o=WINBACK_OFFER, s=source)}]
    return line, row


def ends_at(time_left_hours, now=None) -> float:
    """When a plan with time_left hours ends (the tick takes an hour a run)."""
    return (time.time() if now is None else now) + int(time_left_hours or 0) * 3600
