# -*- coding: utf-8 -*-
"""A Stars payment taken back: by the bot (refundStarPayment) or by the buyer's
chargeback at Apple, Google or their bank, which Telegram deducts from the
bot's balance (Bot API, StarTransaction).

The payment's row turns `refunded` (not `paid`: revenue, payers, "ever paid"
and the paid AI models stop counting it) and what it credited leaves the
balance. Money still on the balance pays it back; money the tick already
turned into days does not exist any more, so the plan gives back the hours it
bought at the running plan's price, as many as the debt needs and the plan
has. What the hours do not cover stays as a balance below zero: the next
payment pays it first, and the tick does not renew a plan the balance does not
cover. A plan left with no hours is off at once (time_left 0 reads as "no
plan" everywhere; the tick's plan-off notice does not come, the refund notice
says it).

Once per payment: the row's status is checked and changed in one transaction,
so the service message and the daily check of the bot's transactions can both
see the same refund. The inviter's referral days stay. A grant's days (db/plan_grants.py) were
never bought: a refund takes none of them.
Lock: python app/service/payment/test_stars_refund.py
"""
from config import db_path, tariff_period
from db import plan_grants
from db.connection import connect_sqlite

STARS_SERVICE_TYPE = 'telegramStars'  # starsPaymentModule.STARS_SERVICE_TYPE (no telebot here)
REFUNDED = 'refunded'


def apply_refund(charge_id, database=None, period=tariff_period):
    """The payment with this Telegram charge id is taken back. None when there
    is no such paid Stars payment (unknown, or taken back before); else a dict:
    user_id, amount (cents off the balance), hours (taken off the plan),
    time_left, balance (after), tariff_id."""
    connection = connect_sqlite(db_path if database is None else database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        payment = connection.execute(
            "SELECT user_id, amount FROM payment_history "
            "WHERE service_type = ? AND invoice_id = ? AND status = 'paid'",
            (STARS_SERVICE_TYPE, str(charge_id))).fetchone()
        if payment is None:
            connection.commit()
            return None
        user_id, amount = int(payment[0]), int(payment[1] or 0)
        connection.execute(
            "UPDATE payment_history SET status = ? WHERE service_type = ? AND invoice_id = ?",
            (REFUNDED, STARS_SERVICE_TYPE, str(charge_id)))

        row = connection.execute(
            "SELECT utc.tariff_id, utc.balance, utc.time_left, t.price FROM user_tariff_cs utc "
            "LEFT JOIN tariffs t ON t.id = utc.tariff_id WHERE utc.uid = ?", (user_id,)).fetchone()
        if row is None:  # a payment always writes the row; nothing to take it from
            connection.commit()
            return {'user_id': user_id, 'amount': amount, 'hours': 0,
                    'time_left': 0, 'balance': 0, 'tariff_id': 0}
        tariff_id, balance, time_left = int(row[0] or 0), int(row[1] or 0) - amount, int(row[2] or 0)
        price = int(row[3] or 0)
        hours = 0
        if balance < 0 and tariff_id > 0 and price > 0 and time_left > 0 \
                and plan_grants.active(connection.execute, user_id) is None:
            hours = min(time_left, (-balance * period + price - 1) // price)
            balance = min(0, balance + hours * price // period)
            time_left -= hours
        connection.execute(
            "UPDATE user_tariff_cs SET balance = ?, time_left = ? WHERE uid = ?",
            (balance, time_left, user_id))
        connection.commit()
        return {'user_id': user_id, 'amount': amount, 'hours': hours,
                'time_left': time_left, 'balance': balance, 'tariff_id': tariff_id}
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def paid_charge_ids(database=None) -> set:
    """Charge ids of the Stars payments that still count as paid."""
    connection = connect_sqlite(db_path if database is None else database)
    try:
        return {str(row[0]) for row in connection.execute(
            "SELECT invoice_id FROM payment_history WHERE service_type = ? AND status = 'paid'",
            (STARS_SERVICE_TYPE,))}
    finally:
        connection.close()
