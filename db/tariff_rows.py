# -*- coding: utf-8 -*-
"""Every user has a tariff row; a user who never had one is "no tariff".

A user without a user_tariff_cs row (registered before the tariff system, or
created by SQLighter.get_user_by_tg's fallback) was in neither of
get_uccs_by_channel's two lists: not "paid", not "without a tariff". Their
channels were polled and skipped, the feed never fetched, nothing ever sent
(653 users, 1116 channels on 2026-10-09).

The row is the one the product writes when a plan is switched off
(subscribeUserToTariffByUid: tariff_id 0, balance 0, time_left 0,
notify_count 0). Deploy git-pulls and restarts, it does not run migrations:
the supervisor heals at start, like hot_indexes. Idempotent and cheap (one
anti-join); a user who has a row, whatever it says, is never touched.
"""
from __future__ import annotations

import sqlite3

from db.connection import connect_sqlite
from lib.tools.logger import logger


def ensure_tariff_rows(database=None) -> int:
    """Give every user without a tariff row the "no tariff" row; returns how many."""
    if database is None:
        from config import db_path as database
    connection = connect_sqlite(database)
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        if not {"users", "user_tariff_cs"} <= tables:
            return 0
        cursor = connection.execute(
            "INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) "
            "SELECT u.id, 0, 0, 0, 0 FROM users u "
            "WHERE NOT EXISTS (SELECT 1 FROM user_tariff_cs ut WHERE ut.uid = u.id)")
        connection.commit()
        given = cursor.rowcount or 0
    finally:
        connection.close()
    if given:
        logger.log("Users without a tariff row got 'no tariff':", given)
    return given


def running_plan_level(chat_id, database=None) -> int:
    """The level of the plan this Telegram chat has time left on, 0 without one
    (whatever its notify_count: that counts automatic deliveries only)."""
    if database is None:
        from config import db_path as database
    connection = connect_sqlite(database)
    try:
        row = connection.execute(
            "SELECT t.level FROM user_tariff_cs ut JOIN users u ON u.id = ut.uid "
            "JOIN tariffs t ON t.id = ut.tariff_id "
            "WHERE u.telegramId = ? AND ut.tariff_id > 0 AND ut.time_left > 0",
            (int(chat_id),)).fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def paid_for_days(chat_id, database=None) -> bool:
    """Money of this chat ever reached its balance: a payment, or a Patreon
    replenishment (those write no payment_history). Days without it (the
    welcome trial, referral days) were never paid for."""
    if ever_paid(chat_id, database):
        return True
    if database is None:
        from config import db_path as database
    connection = connect_sqlite(database)
    try:
        return connection.execute(
            "SELECT 1 FROM payment_service_user_data p JOIN users u ON u.id = p.user_id "
            "WHERE u.telegramId = ? AND p.last_replenishment IS NOT NULL LIMIT 1",
            (int(chat_id),)).fetchone() is not None
    except sqlite3.OperationalError:  # no Patreon table in this database
        return False
    finally:
        connection.close()


def ever_paid(chat_id, database=None) -> bool:
    """A payment of this Telegram chat went through, ever (payment_history keys users.id)."""
    if database is None:
        from config import db_path as database
    connection = connect_sqlite(database)
    try:
        return connection.execute(
            "SELECT 1 FROM payment_history p JOIN users u ON u.id = p.user_id "
            "WHERE u.telegramId = ? AND p.status = 'paid' LIMIT 1", (int(chat_id),)).fetchone() is not None
    finally:
        connection.close()
