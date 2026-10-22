# -*- coding: utf-8 -*-
"""A plan by a Telegram Stars subscription: Telegram charges the same invoice every 30 days.

The invoice is a link (createInvoiceLink with subscription_period: sendInvoice
has no subscriptions). Each charge, the first and every renewal, arrives as a
successful payment of the same payload with a charge id of its own and is
credited like any Stars payment; the hourly tick renews the plan from the
balance, so the tariff clock does not know about subscriptions.

users.flags keeps when the paid period ends (FLAG_UNTIL, Telegram's
subscription_until_date) and the first charge's id (FLAG_CHARGE, what
editUserStarSubscription takes). While a subscription runs, a second one is not
sold (Telegram would charge both) and the D-3 reminder ("pay or it ends") is
not sent: the next charge renews the plan. A cancel or a failed renewal is not
reported to this bot (Telethon has no such update): no charge comes and the
plan ends at the tick as any plan does.

No telebot here: the D-3 job and the tests import it.
"""
import sqlite3
import time

from config import db_path
from db.connection import connect_sqlite

PERIOD_SECONDS = 2592000  # the only period Telegram accepts (30 days)
# A plan a subscription charge turns on ends this long after the next charge is
# due: the renewal is credited before the tick could switch the plan off.
GRACE_HOURS = 24
FLAG_UNTIL = 'stars_sub_until'
FLAG_CHARGE = 'stars_sub_charge'
FLAG_NONCE = 'stars_sub_nonce'  # the payload's 'p': a renewal carries the same one
OFFER_CALLBACK = 'bs_stars_sub'


def offer_row(language_code) -> list:
    """The button that opens the subscription offer (starsPaymentModule.send_subscription_offer)."""
    from app.i18n.messages import get_message
    return [{'text': get_message('starsSubButton', language_code), 'callback_data': {'tp': OFFER_CALLBACK}}]


def until(telegram_id, database=None, now=None):
    """When the running Stars subscription's paid period ends (unix), None if none runs.
    A read that fails is "none": it only shows a button or lets a D-3 reminder
    go, never fails a page."""
    try:
        connection = connect_sqlite(db_path if database is None else database)
        try:
            row = connection.execute(
                "SELECT json_extract(COALESCE(flags, '{}'), '$.%s') FROM users WHERE telegramId = ?" % FLAG_UNTIL,
                (int(telegram_id),)).fetchone()
        finally:
            connection.close()
        stamp = time.time() if now is None else now
        value = float(row[0]) if row and row[0] is not None else None
    except (sqlite3.Error, TypeError, ValueError):
        return None
    return value if value is not None and value > stamp else None


def active(telegram_id, database=None, now=None) -> bool:
    """The user's Stars subscription has a paid period running."""
    return until(telegram_id, database, now) is not None


def second_subscription(telegram_id, nonce, database=None, now=None) -> bool:
    """A payment of another subscription while one runs (Telegram would charge both).
    A renewal of the running one carries its payload, so its nonce: never refused,
    whether or not Telegram asks the pre-checkout for renewals. A failed read is "no"."""
    if not active(telegram_id, database, now):
        return False
    try:
        connection = connect_sqlite(db_path if database is None else database)
        try:
            row = connection.execute(
                "SELECT json_extract(COALESCE(flags, '{}'), '$.%s') FROM users WHERE telegramId = ?" % FLAG_NONCE,
                (int(telegram_id),)).fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, TypeError, ValueError):
        return False
    return bool(row and row[0] is not None and str(row[0]) != str(nonce))


def note_charge(telegram_id, until, nonce, charge_id=None, database=None) -> None:
    """A subscription charge came: the paid period now ends at `until` (unix); `nonce`
    is its payload's; charge_id (the first charge) is what editUserStarSubscription takes."""
    connection = connect_sqlite(db_path if database is None else database)
    try:
        with connection:
            if charge_id:
                connection.execute(
                    "UPDATE users SET flags = json_set(COALESCE(flags, '{}'), '$.%s', ?, '$.%s', ?, '$.%s', ?) "
                    "WHERE telegramId = ?" % (FLAG_UNTIL, FLAG_NONCE, FLAG_CHARGE),
                    (int(until), str(nonce), str(charge_id), int(telegram_id)))
            else:
                connection.execute(
                    "UPDATE users SET flags = json_set(COALESCE(flags, '{}'), '$.%s', ?, '$.%s', ?) "
                    "WHERE telegramId = ?" % (FLAG_UNTIL, FLAG_NONCE),
                    (int(until), str(nonce), int(telegram_id)))
    finally:
        connection.close()
