# -*- coding: utf-8 -*-
"""A plan given for something other than money: a grant (kind 'channels': Bronze while the chat is
subscribed to the owner's channels, app/service/plan/channels.py).

A grant puts its plan on the chat's user_tariff_cs row (the tariff of its level, HOLD_HOURS left, the
tariff's deliveries), so delivery, the updater's lists and every "plan running" check see a plan as
they always did. What makes it a grant is the row here, `ended_at` NULL, one per user:

- what it gives is its profile (app/service/plan/features.py, `grant:<kind>`), not its level's: no AI;
- money never renews it: the tick leaves holders alone (NOT_HELD_SQL), D-3 and plan-off too;
- anything bought, given or switched to replaces it: the payment, the change-plan page, a referral
  award, the survey's week end it first (`end`), then write their own plan, as for a chat with none;
  a write of the row that changes its plan or days ends it too (SQLighter.subscribeUserToTariffByUid);
- its check (app/jobs/plan_grants.py) holds it (`hold`: the days back to HOLD_HOURS, the deliveries
  renewed every tariff_period) or ends it with the plan it replaced back, no days (`end`, restore).
  A check that stops leaves the grant to run out on the clock: the next one that runs holds it again.

`hold` and `end` change the row only while the grant holds it (same tariff, grant not ended), in one
transaction: a payment that replaced the grant between a check's read and its write is never undone.
Prod SQLite is 3.31: no RETURNING; writes take BEGIN IMMEDIATE.
Lock: python db/test_plan_grants.py
"""
import sqlite3
import time

from config import db_path, tariff_period
from db.connection import connect_sqlite

HOLD_HOURS = 7 * 24
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS plan_grants ("
    " id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, tariff_id INTEGER NOT NULL,"
    " prev_tariff_id INTEGER NOT NULL DEFAULT 0, started_at REAL NOT NULL, checked_at REAL,"
    " period_started_at REAL NOT NULL, ended_at REAL, end_reason TEXT)",
    "CREATE UNIQUE INDEX IF NOT EXISTS plan_grants_active ON plan_grants(user_id) WHERE ended_at IS NULL",
)
# SQL: the users.id in `%s` holds no grant (the tick, D-3, plan-off)
NOT_HELD_SQL = "NOT EXISTS (SELECT 1 FROM plan_grants g WHERE g.user_id = %s AND g.ended_at IS NULL)"

STARTED, HELD, BUSY, UNKNOWN = 'started', 'held', 'busy', 'unknown'


def ensure_table(connection) -> None:
    for statement in SCHEMA:
        connection.execute(statement)


def _connect(database):
    connection = connect_sqlite(db_path if database is None else database)
    ensure_table(connection)
    connection.commit()
    return connection


def active(execute, user_id):
    """(id, kind, tariff_id, prev_tariff_id, period_started_at) of the user's grant, None without one."""
    try:
        return execute(
            "SELECT id, kind, tariff_id, prev_tariff_id, period_started_at FROM plan_grants "
            "WHERE user_id = ? AND ended_at IS NULL", (int(user_id),)).fetchone()
    except sqlite3.OperationalError:  # no table yet: nobody holds a grant
        return None


def active_kind(chat_id, database=None):
    """The kind of grant that holds this Telegram chat's plan now, None when its plan is not a grant's."""
    connection = connect_sqlite(db_path if database is None else database)
    try:
        row = connection.execute(
            "SELECT g.kind FROM plan_grants g JOIN users u ON u.id = g.user_id "
            "JOIN user_tariff_cs ut ON ut.uid = g.user_id "
            "WHERE u.telegramId = ? AND g.ended_at IS NULL AND ut.tariff_id = g.tariff_id",
            (int(chat_id),)).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


def end(execute, user_id, reason, now=None, restore=False) -> bool:
    """Inside the caller's transaction: the user's grant ends and its plan stops (no days, no
    deliveries); `restore`: the plan it replaced comes back on the row, with no days. False: none held."""
    grant = active(execute, user_id)
    if grant is None:
        return False
    grant_id, _kind, tariff_id, prev_tariff_id, _period = grant
    execute("UPDATE plan_grants SET ended_at = ?, end_reason = ? WHERE id = ?",
            (time.time() if now is None else now, str(reason), grant_id))
    execute("UPDATE user_tariff_cs SET tariff_id = ?, time_left = 0, notify_count = 0 "
            "WHERE uid = ? AND tariff_id = ?",
            (int(prev_tariff_id or 0) if restore else tariff_id, int(user_id), tariff_id))
    return True


def _transaction(database, work):
    connection = _connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        result = work(connection.execute)
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def start(chat_id, kind, level, now=None, database=None) -> str:
    """Give this Telegram chat the plan of `level` as a grant of `kind`: STARTED; HELD when it holds
    one already (held again); BUSY when another plan runs (the grant is for a chat without one);
    UNKNOWN without such a user or tariff. The balance stays as it is."""
    now = time.time() if now is None else now

    def work(execute):
        user = execute("SELECT id FROM users WHERE telegramId = ?", (int(chat_id),)).fetchone()
        tariff = execute("SELECT id, notify_count FROM tariffs WHERE level = ? ORDER BY id LIMIT 1",
                         (int(level),)).fetchone()
        if user is None or tariff is None:
            return UNKNOWN
        user_id = int(user[0])
        if active(execute, user_id) is not None and _hold(execute, user_id, now):
            return HELD
        row =execute("SELECT tariff_id, time_left FROM user_tariff_cs WHERE uid = ?", (user_id,)).fetchone()
        if row is not None and int(row[0] or 0) > 0 and int(row[1] or 0) > 0:
            return BUSY
        execute("INSERT INTO plan_grants (user_id, kind, tariff_id, prev_tariff_id, started_at, checked_at,"
                " period_started_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, str(kind), int(tariff[0]), int(row[0] or 0) if row else 0, now, now, now))
        if row is None:
            execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, time_left, notify_count) "
                    "VALUES (?, ?, 0, ?, ?)", (user_id, int(tariff[0]), HOLD_HOURS, int(tariff[1])))
        else:
            execute("UPDATE user_tariff_cs SET tariff_id = ?, time_left = ?, notify_count = ? WHERE uid = ?",
                    (int(tariff[0]), HOLD_HOURS, int(tariff[1]), user_id))
        return STARTED

    return _transaction(database, work)


def _hold(execute, user_id, now) -> bool:
    grant = active(execute, user_id)
    if grant is None:
        return False
    grant_id, _kind, tariff_id, _prev, period_started_at = grant
    held = execute("UPDATE user_tariff_cs SET time_left = MAX(time_left, ?) WHERE uid = ? AND tariff_id = ?",
                   (HOLD_HOURS, int(user_id), tariff_id)).rowcount
    if not held:  # its plan is not on the row any more: something else replaced it
        execute("UPDATE plan_grants SET ended_at = ?, end_reason = 'replaced' WHERE id = ?", (now, grant_id))
        return False
    if now - float(period_started_at or 0) >= tariff_period * 3600:
        # a new period: the plan's deliveries again, as the tick gives a renewed plan
        execute("UPDATE user_tariff_cs SET notify_count = "
                "(SELECT notify_count FROM tariffs WHERE id = ?) WHERE uid = ?", (tariff_id, int(user_id)))
        execute("UPDATE plan_grants SET period_started_at = ? WHERE id = ?", (now, grant_id))
    execute("UPDATE plan_grants SET checked_at = ? WHERE id = ?", (now, grant_id))
    return True


def hold(user_id, now=None, database=None) -> bool:
    """The check found the chat entitled: its grant runs on (HOLD_HOURS ahead). False: none held."""
    return _transaction(database, lambda execute: _hold(execute, user_id, time.time() if now is None else now))


def end_now(user_id, reason, restore=True, now=None, database=None) -> bool:
    """`end` in a transaction of its own: the check found the chat no longer entitled."""
    return _transaction(database, lambda execute: end(execute, user_id, reason, now, restore))


def end_for_chat(chat_id, reason, restore=True, now=None, database=None) -> bool:
    """`end_now` by Telegram id: the change-plan page replaced or turned off the grant's plan."""
    def work(execute):
        user = execute("SELECT id FROM users WHERE telegramId = ?", (int(chat_id),)).fetchone()
        return user is not None and end(execute, user[0], reason, now, restore)

    return _transaction(database, work)


def holders(kind, database=None) -> list:
    """[{user_id, telegram_id, lang, checked_at}] of the grants of `kind` running, the least recently
    checked first. Deleted users are left out: the tick freezes their days, nobody gets anything."""
    connection = _connect(database)
    try:
        rows = connection.execute(
            "SELECT g.user_id, u.telegramId, u.lang, g.checked_at FROM plan_grants g "
            "JOIN users u ON u.id = g.user_id WHERE g.kind = ? AND g.ended_at IS NULL "
            "AND u.deleted_at IS NULL ORDER BY COALESCE(g.checked_at, 0)", (str(kind),)).fetchall()
    finally:
        connection.close()
    return [{'user_id': int(r[0]), 'telegram_id': int(r[1]), 'lang': r[2] or 'en', 'checked_at': r[3]}
            for r in rows]


def counts(kind, since, database=None) -> dict:
    """{running, started, ended} of the grants of `kind`: now, and since `since` (admin)."""
    connection = _connect(database)
    try:
        row = connection.execute(
            "SELECT SUM(ended_at IS NULL), SUM(started_at >= ?), SUM(ended_at >= ?) FROM plan_grants "
            "WHERE kind = ?", (since, since, str(kind))).fetchone()
    finally:
        connection.close()
    return {'running': int(row[0] or 0), 'started': int(row[1] or 0), 'ended': int(row[2] or 0)}
