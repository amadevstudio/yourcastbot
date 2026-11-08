# -*- coding: utf-8 -*-
"""Prices that credit more than they charge: prepaid months of every plan and
Relay's win-back offer (one month at a discount, once per user). Every pay method
sells them through purchase.py (Stars, CryptoBot).

The balance is credited at full price (price * months) and the hourly tick
renews month by month from it, as from any top-up. Only the charge is
discounted, so nothing else (renewal, D-3, plan change) knows about offers;
payment_history keeps what was charged beside it (`charged`), for revenue.

The win-back offer opens when it is first sent: the end of a trial (D-3 or
the plan-off notice, users.flags[OFFER_SENT_FLAG]) or the first win-back
message. A plan's terms (its months; the offer is Relay's) are billed while that
plan or none runs, never while another one does (the balance would renew that
plan instead), checked again at the pre-checkout.

The balance holds a bundle's months at full price, so a plan left before they
are used would take the discount with it (Relay's months renewing Bronze at $1).
Leaving it takes back the discount on the months still on the balance
(`bundle_discount_back`): what stays is what was paid for them.
"""
import datetime

from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL
from app.service.plan import entitlements
from config import db_path, prepay_bundles, tariff_period, winback_offer_discount

# the page of every plan's prepaid months (starsPaymentModule.open_bundles_page)
BUNDLES_CALLBACK = "bs_long"
# its `pay` for CryptoBot's invoices (cryptoBotPaymentModule); none: Stars
BUNDLES_CRYPTO = "c"
# the payload's "o" for the win-back offer; its single use is users.flags[WINBACK_OFFER_FLAG]
WINBACK_OFFER = "wb"
WINBACK_OFFER_FLAG = "winback_offer_used"
# when the end of a trial offered it (app/service/payment/plan_end.py)
OFFER_SENT_FLAG = "winback_offer_sent"


def bundle_discount(months) -> int | None:
    """% off for `months` of the showcase plan: 0 for one month, None if not sold."""
    months = int(months)
    if months == 1:
        return 0
    return dict(prepay_bundles).get(months)


def longest_bundle():
    """(months, % off) of the longest prepaid bundle, the one the /subscription page shows."""
    return max(prepay_bundles)


def prepaid_months_sold(current_level, plan_running, plan_level=SHOWCASE_TARIFF_LEVEL) -> bool:
    """A plan's prepaid months go to that plan running or to a user with no plan
    running (the payment turns the plan on). Another running plan would renew
    itself from that balance: its owner changes plan first."""
    return not plan_running or int(current_level or 0) == int(plan_level)


def plan_terms_open(telegram_id, plan_id=0, database=None) -> bool:
    """May this user pay for the prepaid months of the plan an invoice names (or Relay's
    offer) now? No plan named (an invoice from before `v`) is Relay. The plan running is
    read now, not when the invoice was sent: a user who switched to Bronze in between
    would get Relay's discounted month credited to Bronze. A grant's plan is no plan
    here: what is bought replaces it (db/plan_grants.py)."""
    from db.connection import connect_sqlite
    database = db_path if database is None else database
    plan_level = SHOWCASE_TARIFF_LEVEL
    if plan_id:
        connection = connect_sqlite(database)
        try:
            row = connection.execute("SELECT level FROM tariffs WHERE id = ?", (int(plan_id),)).fetchone()
        finally:
            connection.close()
        plan_level = int(row[0]) if row else SHOWCASE_TARIFF_LEVEL
    level = entitlements.of(telegram_id, database).purchase_level
    return prepaid_months_sold(level, level > 0, plan_level)


def bundle_months(amount, charged) -> int | None:
    """The months of a bundle that credited `amount` and charged `charged`, None for
    any other payment (a plain one, the win-back month, terms no longer sold)."""
    for months, discount in prepay_bundles:
        if months > 1 and int(amount) % months == 0 and charged_cents(amount, discount) == int(charged):
            return months
    return None


def bundle_discount_back(telegram_id, price, balance, now=None, database=None) -> tuple[int, list]:
    """(cents, settle): the discount on the prepaid months still on the balance, taken
    back when the plan they renew is left; `settle` for settle_bundles, every bundle
    looked at (a bundle is settled once, whatever it gave back).

    A bundle that turned its plan on spent its first month at once; the tick renews
    a month at each period's last hour, so after h hours (h + 1) // period more are
    spent. Bought while the plan ran, its months start later: counted as earlier,
    less is taken, never more. Never more months than the balance holds at today's
    price: the newest bundle's months are the last to be spent. A month's discount
    is the bundle's discount over its months, rounded down."""
    from db import payments
    from db.connection import connect_sqlite
    now = datetime.datetime.now() if now is None else now  # payment_history.datetime is the server's local time
    connection = connect_sqlite(db_path if database is None else database)
    try:
        if not payments.has_charged(connection):
            return 0, []
        settled = "p.bundle_back IS NULL" if payments.has_column(connection, 'bundle_back') else "1"
        rows = connection.execute(
            "SELECT p.rowid, p.amount, p.charged, p.datetime FROM payment_history p "
            # every pay method's bundles (purchase.py): Stars, CryptoBot
            "JOIN users u ON u.id = p.user_id WHERE u.telegramId = ? "
            "AND p.status = 'paid' AND p.charged < p.amount AND " + settled + " ORDER BY p.datetime DESC",
            (int(telegram_id),)).fetchall()
    finally:
        connection.close()
    room = max(0, int(balance)) // int(price) if int(price or 0) > 0 else 0
    period = datetime.timedelta(hours=tariff_period)
    total, settle = 0, []
    for rowid, amount, charged, paid_at in rows:
        months = bundle_months(amount, charged)
        try:
            at = datetime.datetime.fromisoformat(str(paid_at))
        except ValueError:
            months = None
        if months is None:
            continue
        spent = 1 + max(0, (now - at + datetime.timedelta(hours=1)) // period)
        left = min(max(0, months - spent), room)
        room -= left
        cents = left * (int(amount) - int(charged)) // months
        total += cents
        settle.append((rowid, cents))
    return total, settle


def settle_bundles(settle, database=None) -> None:
    """The bundles bundle_discount_back looked at are settled with what they gave back:
    another switch takes nothing, a refund takes the rest. Before the switch is written:
    a switch that then fails has taken nothing and settled, never the other way round."""
    if not settle:
        return
    from db import payments
    from db.connection import connect_sqlite
    connection = connect_sqlite(db_path if database is None else database)
    try:
        payments.ensure_bundle_back_column(connection)
        with connection:
            connection.executemany(
                "UPDATE payment_history SET bundle_back = ? WHERE rowid = ? AND bundle_back IS NULL",
                [(int(cents), int(rowid)) for rowid, cents in settle])
    finally:
        connection.close()


def offer_discount(months, offer="") -> int | None:
    """% off for `months` bought under `offer` ("" or WINBACK_OFFER), None if not sold."""
    if offer == WINBACK_OFFER:
        return winback_offer_discount if int(months) == 1 else None
    if offer:
        return None
    return bundle_discount(months)


def charged_cents(credit_cents, discount) -> int:
    """`credit_cents` with `discount` % off, rounded up to a cent."""
    return -(-int(credit_cents) * (100 - int(discount)) // 100)


def offer_open(telegram_id, offer, database=None) -> bool:
    """May this user buy under `offer` now? A plain purchase always may.

    The win-back offer: the user was sent it (a callback can be forged, the
    flag and the schedule cannot) and has not spent it. Asked before Telegram
    takes the money, never after: a payment that went through is credited as sold.
    """
    if not offer:
        return True
    if offer != WINBACK_OFFER:
        return False
    from db import winback
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path if database is None else database)
    try:
        if db.get_user_flag(telegram_id, WINBACK_OFFER_FLAG):
            return False
        if db.get_user_flag(telegram_id, OFFER_SENT_FLAG):
            return True
    finally:
        db.close()
    return bool(winback.messages_sent(telegram_id, database=database))


def mark_offer_sent(telegram_id, now=None, database=None):
    """The end of a trial offers the first month: open it before the message goes
    (a message that failed opens an offer nobody saw, which costs nothing)."""
    import time
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path if database is None else database)
    try:
        db.set_user_flag(telegram_id, OFFER_SENT_FLAG, int(time.time() if now is None else now))
    finally:
        db.close()
