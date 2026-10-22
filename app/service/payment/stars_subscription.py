# -*- coding: utf-8 -*-
"""Relay by a Telegram Stars subscription: Telegram charges the same invoice every 30 days.

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
OFFER_CALLBACK = 'bs_stars_sub'


def offer_row(language_code) -> list:
    """The button that opens the subscription offer (starsPaymentModule.send_subscription_offer)."""
    from app.i18n.messages import get_message
    return [{'text': get_message('starsSubButton', language_code), 'callback_data': {'tp': OFFER_CALLBACK}}]


def active(telegram_id, database=None, now=None) -> bool:
    """The user's Stars subscription has a paid period running. A read that fails is
    "no": it only hides a button or lets a D-3 reminder go, never fails a page."""
    try:
        connection = connect_sqlite(db_path if database is None else database)
        try:
            row = connection.execute(
                "SELECT json_extract(COALESCE(flags, '{}'), '$.%s') FROM users WHERE telegramId = ?" % FLAG_UNTIL,
                (int(telegram_id),)).fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, TypeError, ValueError):
        return False
    stamp = time.time() if now is None else now
    try:
        return bool(row and row[0] is not None and float(row[0]) > stamp)
    except (TypeError, ValueError):
        return False


def note_charge(telegram_id, until, charge_id=None, database=None) -> None:
    """A subscription charge came: the paid period now ends at `until` (unix)."""
    connection = connect_sqlite(db_path if database is None else database)
    try:
        with connection:
            if charge_id:
                connection.execute(
                    "UPDATE users SET flags = json_set(COALESCE(flags, '{}'), '$.%s', ?, '$.%s', ?) "
                    "WHERE telegramId = ?" % (FLAG_UNTIL, FLAG_CHARGE),
                    (int(until), str(charge_id), int(telegram_id)))
            else:
                connection.execute(
                    "UPDATE users SET flags = json_set(COALESCE(flags, '{}'), '$.%s', ?) "
                    "WHERE telegramId = ?" % FLAG_UNTIL, (int(until), int(telegram_id)))
    finally:
        connection.close()
