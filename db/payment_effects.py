"""What a payment sets off once it is credited: one row per payment and effect.

The rows are written in the transaction that credits the payment
(db/sqliteAdapter.applyPaymentReplenishmentOnce for Stars, CryptoBot and
Robokassa; db/patreon.credit_month), and run by the jobs role
(app/jobs/payment_effects.py). So:

- no money credited, no effect; a payment credited once (a retried or
  replayed webhook writes nothing) sets its effects off once
  (UNIQUE(payment, effect));
- an effect runs at least once, never inside the payment's transaction: a
  failing effect never fails or undoes a payment. It must be idempotent; a
  failure is tried again after RETRY_SECONDS times its attempts, and after
  MAX_ATTEMPTS it is 'failed' (and the creator hears of it).

A transactional outbox, not a full saga: the effects are perks, nothing to
compensate. What a perk needs (a plan running) is checked where it is used.

`payment` names what set the row off: 'ph:<payment_history rowid>', or
'backfill:<users.id>' for chats that paid before the effect existed.

Prod SQLite is 3.31: no RETURNING, claims use BEGIN IMMEDIATE.
"""
import sqlite3
import time

from config import db_path
from db.connection import connect_sqlite

PAID_MODELS = 'paid_models'  # better AI models (app/service/ai/paid_models.py)
EFFECTS = (PAID_MODELS,)  # every payment sets these off; each has a handler in app/jobs/payment_effects.py
LEASE_SECONDS = 5 * 60
RETRY_SECONDS = 10 * 60
MAX_ATTEMPTS = 5

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS payment_effects ("
    " id INTEGER PRIMARY KEY, payment TEXT NOT NULL, user_id INTEGER NOT NULL, effect TEXT NOT NULL,"
    " status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, due_at REAL NOT NULL,"
    " created_at REAL NOT NULL, done_at REAL, error TEXT, UNIQUE (payment, effect))",
    "CREATE INDEX IF NOT EXISTS payment_effects_due ON payment_effects(status, due_at)",
)


def ensure_table(connection) -> None:
    """Before the payment's transaction begins: DDL inside it would end it."""
    for sql in SCHEMA:
        connection.execute(sql)


def payment_key(payment_rowid) -> str:
    return 'ph:%d' % int(payment_rowid)


def queue(execute, user_id, payment, now=None) -> None:
    """In the crediting transaction: `execute` is its cursor's or connection's execute."""
    now = time.time() if now is None else now
    for effect in EFFECTS:
        execute("INSERT OR IGNORE INTO payment_effects (payment, user_id, effect, status, due_at, created_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?)", (str(payment), int(user_id), effect, now, now))


def _connect(database):
    connection = connect_sqlite(db_path if database is None else database)
    connection.row_factory = sqlite3.Row
    connection.isolation_level = None
    ensure_table(connection)
    return connection


def backfill(effect, user_ids, database=None, now=None) -> int:
    """Rows for chats that paid before `effect` existed; once per chat (the key); how many are new."""
    now = time.time() if now is None else now
    connection = _connect(database)
    try:
        added = 0
        for user_id in user_ids:
            added += connection.execute(
                "INSERT OR IGNORE INTO payment_effects (payment, user_id, effect, status, due_at, created_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?)",
                ('backfill:%d' % int(user_id), int(user_id), effect, now, now)).rowcount
        return added
    finally:
        connection.close()


def claim(database=None, now=None):
    """The oldest effect that is due (pending, or a lease that ran out: its worker died), leased; or None."""
    now = time.time() if now is None else now
    connection = _connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM payment_effects WHERE status IN ('pending', 'leased') AND due_at <= ? "
            "ORDER BY id LIMIT 1", (now,)).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return None
        connection.execute("UPDATE payment_effects SET status = 'leased', attempts = attempts + 1, due_at = ? "
                           "WHERE id = ?", (now + LEASE_SECONDS, row['id']))
        connection.execute("COMMIT")
        return dict(row, attempts=row['attempts'] + 1, status='leased')
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def finish(row, error=None, database=None, now=None) -> str:
    """Done, or tried again later, or failed after MAX_ATTEMPTS; the row's status."""
    now = time.time() if now is None else now
    if error is None:
        status, due_at = 'done', now
    elif row['attempts'] >= MAX_ATTEMPTS:
        status, due_at = 'failed', now
    else:
        status, due_at = 'pending', now + RETRY_SECONDS * row['attempts']
    connection = _connect(database)
    try:
        connection.execute("UPDATE payment_effects SET status = ?, due_at = ?, done_at = ?, error = ? WHERE id = ?",
                           (status, due_at, now if status == 'done' else None,
                            None if error is None else str(error)[:500], row['id']))
    finally:
        connection.close()
    return status
