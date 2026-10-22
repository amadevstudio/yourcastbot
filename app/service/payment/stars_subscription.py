# -*- coding: utf-8 -*-
"""A plan by a Telegram Stars subscription: Telegram charges the same invoice every 30 days.

The invoice is a link (createInvoiceLink with subscription_period: sendInvoice
has no subscriptions). Each charge, the first and every renewal, arrives as a
successful payment of the same payload with a charge id of its own and is
credited like any Stars payment; the hourly tick renews the plan from the
balance, so the tariff clock does not know about subscriptions.

users.flags keeps when the paid period ends (FLAG_UNTIL, Telegram's
subscription_until_date), the first charge's id (FLAG_CHARGE, what
editUserStarSubscription takes), and the plan and price a charge brings
(FLAG_PLAN, FLAG_CENTS). While a subscription runs, a second one is not sold
(Telegram would charge both), and the D-3 reminder ("pay or it ends") is not
sent when the charge pays for the plan that ends (`covers`): the next charge
renews it. A plan changed on the change-plan page is no longer the one the
charges pay for: the bot cancels the subscription (`cancel`, the paid period
runs to its end) and offers one for the new plan. A cancel by the user or a
failed renewal is not reported to this bot (Telethon has no such update): no
charge comes and the plan ends at the tick as any plan does.

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
FLAG_PLAN = 'stars_sub_plan'  # the plan a charge pays for (payload 'v')
FLAG_CENTS = 'stars_sub_cents'  # what a charge credits (payload 'b')
FLAGS = (FLAG_UNTIL, FLAG_CHARGE, FLAG_NONCE, FLAG_PLAN, FLAG_CENTS)
OFFER_CALLBACK = 'bs_stars_sub'


def offer_row(language_code) -> list:
    """The button that opens the subscription offer (starsPaymentModule.send_subscription_offer)."""
    from app.i18n.messages import get_message
    return [{'text': get_message('starsSubButton', language_code), 'callback_data': {'tp': OFFER_CALLBACK}}]


def _flags(telegram_id, database=None) -> dict:
    """The subscription's flags of the user ({} when none or the read fails)."""
    try:
        connection = connect_sqlite(db_path if database is None else database)
        try:
            row = connection.execute(
                "SELECT %s FROM users WHERE telegramId = ?" % ", ".join(
                    "json_extract(COALESCE(flags, '{}'), '$.%s')" % key for key in FLAGS),
                (int(telegram_id),)).fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, TypeError, ValueError):
        return {}
    return {key: value for key, value in zip(FLAGS, row or ()) if value is not None}


def running(telegram_id, database=None, now=None) -> dict:
    """The running subscription's flags (FLAG_* keys), {} if none runs."""
    flags = _flags(telegram_id, database)
    try:
        ends = float(flags.get(FLAG_UNTIL))
    except (TypeError, ValueError):
        return {}
    return flags if ends > (time.time() if now is None else now) else {}


def until(telegram_id, database=None, now=None):
    """When the running Stars subscription's paid period ends (unix), None if none runs.
    A read that fails is "none": it only shows a button or lets a D-3 reminder
    go, never fails a page."""
    flags = running(telegram_id, database, now)
    return float(flags[FLAG_UNTIL]) if flags else None


def active(telegram_id, database=None, now=None) -> bool:
    """The user's Stars subscription has a paid period running."""
    return until(telegram_id, database, now) is not None


def covers(telegram_id, plan_id, price, database=None, now=None) -> bool:
    """A running subscription whose charge pays for this plan at this price: the next
    charge renews it. Another plan (changed since, the cancel failed) or a price
    raised past the charge is not covered: the user hears the plan ends. A
    subscription noted before the plan was kept covers (it was sold for that plan)."""
    flags = running(telegram_id, database, now)
    if not flags:
        return False
    try:
        if FLAG_PLAN in flags and int(flags[FLAG_PLAN]) != int(plan_id):
            return False
        return FLAG_CENTS not in flags or int(flags[FLAG_CENTS]) >= int(price)
    except (TypeError, ValueError):
        return False


def second_subscription(telegram_id, nonce, database=None, now=None) -> bool:
    """A payment of another subscription while one runs (Telegram would charge both).
    A renewal of the running one carries its payload, so its nonce: never refused,
    whether or not Telegram asks the pre-checkout for renewals. A failed read is "no"."""
    flags = running(telegram_id, database, now)
    return bool(flags) and FLAG_NONCE in flags and str(flags[FLAG_NONCE]) != str(nonce)


def note_charge(telegram_id, until, nonce, charge_id=None, plan_id=None, cents=None, database=None) -> None:
    """A subscription charge came: the paid period now ends at `until` (unix); `nonce`
    is its payload's; charge_id (the first charge) is what editUserStarSubscription
    takes; plan_id and cents what the charge pays for."""
    values = {FLAG_UNTIL: int(until), FLAG_NONCE: str(nonce)}
    if charge_id:
        values[FLAG_CHARGE] = str(charge_id)
    if plan_id:
        values[FLAG_PLAN] = int(plan_id)
    if cents is not None:
        values[FLAG_CENTS] = int(cents)
    connection = connect_sqlite(db_path if database is None else database)
    try:
        with connection:
            connection.execute(
                "UPDATE users SET flags = json_set(COALESCE(flags, '{}'), %s) WHERE telegramId = ?"
                % ", ".join("'$.%s', ?" % key for key in values),
                (*values.values(), int(telegram_id)))
    finally:
        connection.close()


def forget(telegram_id, database=None) -> None:
    """The subscription is canceled: no flag of it stays, a new one can be sold."""
    connection = connect_sqlite(db_path if database is None else database)
    try:
        with connection:
            connection.execute(
                "UPDATE users SET flags = json_remove(COALESCE(flags, '{}'), %s) WHERE telegramId = ?"
                % ", ".join("'$.%s'" % key for key in FLAGS), (int(telegram_id),))
    finally:
        connection.close()


def cancel_for_plan_change(telegram_id, new_plan_id, edit_subscription, database=None):
    """The user's plan changed to new_plan_id: a running subscription that pays for
    another plan is canceled (edit_subscription(user_id, charge_id), the Bot API's
    editUserStarSubscription with is_canceled; the paid period runs to its end) and
    forgotten. Returns the canceled subscription's plan id, None when there was
    nothing to cancel; raises when the cancel failed (the flags stay: the charges
    still come, `covers` lets the D-3 reminder go)."""
    flags = running(telegram_id, database)
    if not flags:
        return None
    try:
        if FLAG_PLAN in flags and int(flags[FLAG_PLAN]) == int(new_plan_id):
            return None
    except (TypeError, ValueError):
        pass
    if FLAG_CHARGE not in flags:
        raise ValueError("no charge id to cancel the subscription by")
    edit_subscription(int(telegram_id), str(flags[FLAG_CHARGE]))
    forget(telegram_id, database)
    return int(flags[FLAG_PLAN]) if FLAG_PLAN in flags else 0
