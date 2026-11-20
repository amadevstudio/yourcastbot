# -*- coding: utf-8 -*-
"""Packs of episodes by click, sold for Stars at the free limit (app/service/record/free_limit.py).

A pack is a payment, not a plan: its row in payment_history (service_type SERVICE_TYPE, status
'paid', amount = charged = its price in cents) makes it revenue, a payer and a refundable charge
like any Stars payment, and its episodes are a row here keyed by the charge id, written in the same
transaction (once: the charge id is the payment's key). It is never "paid for" a plan
(tariff_rows.ever_paid leaves SERVICE_TYPE out): $0.65 must not open a paid plan's AI hours, the
better models, the half-days refund or a referral award.

The episodes do not expire and nothing counts them down: what is left is what the packs still paid
(a refund turns the payment's status, and its episodes go) minus the episodes used. A use is a row
per episode (ref = usage.episode_ref of the link), written when its click is queued, and counts
while it is fresh (USE_GRACE_SECONDS: between the row and the queue), waiting in the outbox, or
delivered within DELIVERED_WITHIN_SECONDS after it (usage_events 'rec'). A click that failed counts
for nothing: its episode comes back by itself, with no refund to forget or to do twice, and the same
episode fetched free a week later is the week's, not the pack's. The same episode again is free.
The free week does not count the episodes a pack pays for (free_limit asks counting_refs): a pack is
on top of the week.
Lock: python db/test_click_packs.py
"""
import datetime
import threading
import time

from config import db_path
from db import payments, usage
from db.connection import connect_sqlite

SERVICE_TYPE = 'telegramStarsPack'
USE_GRACE_SECONDS = 600
DELIVERED_WITHIN_SECONDS = 24 * 3600  # a pack's click delivered later than this was another click

_ready = set()
_lock = threading.Lock()
SCHEMA = '''
CREATE TABLE IF NOT EXISTS click_packs (
    charge_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, episodes INTEGER NOT NULL, at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS click_pack_uses (
    user_id INTEGER NOT NULL, ref TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY (user_id, ref)
);
'''


def connect(database=None):
    database = db_path if database is None else database
    connection = connect_sqlite(database)
    with _lock:
        if database not in _ready or database == ':memory:':
            connection.executescript(SCHEMA)
            usage.connect(database).close()  # usage_events, which the uses are read against
            _ready.add(database)
    return connection


def credit(telegram_id, charge_id, episodes, cents, invoice_hash='', now=None, database=None) -> bool:
    """The pack's payment and its episodes, once per charge id. False: credited before, or no such
    user (nothing written)."""
    now = time.time() if now is None else now
    connection = connect(database)
    try:
        payments.ensure_charged_column(connection)  # outside the transaction: the ALTER commits
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute("SELECT id FROM users WHERE telegramId = ?", (int(telegram_id),)).fetchone()
        if user is None:
            connection.rollback()
            return False
        if connection.execute("SELECT 1 FROM payment_history WHERE service_type = ? AND invoice_id = ? LIMIT 1",
                              (SERVICE_TYPE, str(charge_id))).fetchone() is not None:
            connection.commit()
            return False  # credited before: the charge id is the payment's
        written = connection.execute(
            "INSERT OR IGNORE INTO payment_history "
            "(user_id, service_type, invoice_id, invoice_hash, status, amount, datetime, charged) "
            "VALUES (?, ?, ?, ?, 'paid', ?, ?, ?)",
            (int(user[0]), SERVICE_TYPE, str(charge_id), str(invoice_hash), int(cents),
             str(datetime.datetime.fromtimestamp(now)), int(cents))).rowcount
        if written:
            connection.execute("INSERT OR IGNORE INTO click_packs (charge_id, user_id, episodes, at) VALUES (?, ?, ?, ?)",
                               (str(charge_id), int(telegram_id), int(episodes), now))
        connection.commit()
        return bool(written)
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _bought(connection, telegram_id) -> int:
    """Episodes of the chat's packs whose payment still counts (a refund takes its pack away)."""
    if connection.execute("SELECT 1 FROM click_packs WHERE user_id = ? LIMIT 1", (int(telegram_id),)).fetchone() is None:
        return 0  # most chats: no pack, no join
    row = connection.execute(
        "SELECT COALESCE(SUM(k.episodes), 0) FROM click_packs k JOIN payment_history p "
        "ON p.service_type = ? AND p.invoice_id = k.charge_id AND p.status = 'paid' WHERE k.user_id = ?",
        (SERVICE_TYPE, int(telegram_id))).fetchone()
    return int(row[0] or 0)


def _counting(connection, telegram_id, open_refs, now) -> set:
    """The refs of the uses that count: fresh, waiting, or delivered soon after the use."""
    counted = set()
    for ref, at in connection.execute("SELECT ref, at FROM click_pack_uses WHERE user_id = ?", (int(telegram_id),)):
        if at > now - USE_GRACE_SECONDS or ref in open_refs or connection.execute(
                "SELECT 1 FROM usage_events WHERE user_id = ? AND kind = 'rec' AND ref = ? AND at >= ? AND at <= ? "
                "LIMIT 1", (usage.chat_key(telegram_id), ref, at, at + DELIVERED_WITHIN_SECONDS)).fetchone():
            counted.add(ref)
    return counted


def _open_refs(open_links) -> set:
    return {usage.episode_ref(link) for link in open_links}


def left(telegram_id, open_links=(), now=None, database=None) -> int:
    """Episodes the chat's packs still have."""
    now = time.time() if now is None else now
    connection = connect(database)
    try:
        return max(0, _bought(connection, telegram_id) - len(_counting(connection, telegram_id, _open_refs(open_links), now)))
    finally:
        connection.close()


def counting_refs(telegram_id, open_links=(), now=None, database=None) -> set:
    """The episodes the chat's packs pay for: the free window does not count them."""
    now = time.time() if now is None else now
    connection = connect(database)
    try:
        if connection.execute("SELECT 1 FROM click_pack_uses WHERE user_id = ? LIMIT 1",
                              (int(telegram_id),)).fetchone() is None:
            return set()
        return _counting(connection, telegram_id, _open_refs(open_links), now)
    finally:
        connection.close()


def use(telegram_id, link, open_links=(), now=None, database=None) -> bool:
    """This click goes on the chat's packs: True when it may be queued (an episode the pack already
    counts is free; else one episode is taken while one is left), False when there is none left.
    One transaction: two taps never take the last episode twice."""
    now = time.time() if now is None else now
    ref = usage.episode_ref(link)
    connection = connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        counted = _counting(connection, telegram_id, _open_refs(open_links), now)
        if ref in counted:
            connection.commit()
            return True
        if _bought(connection, telegram_id) - len(counted) <= 0:
            connection.commit()
            return False
        # a use that failed before is the same row, counting again from now
        connection.execute("INSERT OR REPLACE INTO click_pack_uses (user_id, ref, at) VALUES (?, ?, ?)",
                           (int(telegram_id), ref, now))
        connection.commit()
        return True
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def episodes_of(charge_id, database=None) -> int:
    """The episodes the pack of this charge brought, 0 when it is no pack."""
    connection = connect(database)
    try:
        row = connection.execute("SELECT episodes FROM click_packs WHERE charge_id = ?", (str(charge_id),)).fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()
