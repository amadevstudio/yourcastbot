# -*- coding: utf-8 -*-
"""Indexes for user_channel_cs / user_tariff_cs lookups.

Without them /menu, /usersCount and get_next_channel_to_poll table-scan
every subscription row. That saturates disk for the whole process; it is
not how request isolation works (see UserGate + shared incoming queue).

CREATE INDEX IF NOT EXISTS on connect because deploy git-pulls and
restarts, it does not run migrations. The supervisor parent also builds
them before spawn so children do not compile indexes on the first request.
"""
from __future__ import annotations

import threading
import time

from db.connection import connect_sqlite
from lib.tools.logger import logger

HOT_INDEXES = (
    (
        "ucc_user_notify_idx",
        "user_channel_cs",
        "user_telegram_id, notify",
    ),
    (
        "ucc_channel_notify_idx",
        "user_channel_cs",
        "channel_id, notify",
    ),
    (
        "utc_uid_idx",
        "user_tariff_cs",
        "uid",
    ),
)

INDEX_BUILD_TIMEOUT_SECONDS = 180.0

_lock = threading.Lock()
_ready = set()


def _tables(connection):
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _index_names(connection):
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }


def ensure_hot_path_indexes(connection, database=None):
    key = database
    if key is not None and key in _ready:
        return
    with _lock:
        if key is not None and key in _ready:
            return
        try:
            tables = _tables(connection)
            existing = _index_names(connection)
            created = []
            t0 = time.time()
            for name, table, columns in HOT_INDEXES:
                if table not in tables:
                    continue
                if name in existing:
                    continue
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS %s ON %s (%s)"
                    % (name, table, columns))
                created.append(name)
            if created:
                analyzed = set()
                for name, table, _columns in HOT_INDEXES:
                    if name in created and table not in analyzed:
                        connection.execute("ANALYZE %s" % table)
                        analyzed.add(table)
                try:
                    connection.commit()
                except Exception:
                    pass
                logger.warn(
                    "Created sqlite indexes %s in %.1fs"
                    % (", ".join(created), time.time() - t0))
            # Missing tables (tests create schema after connect): retry later.
            if any(table not in tables for _n, table, _c in HOT_INDEXES):
                return
            if key is not None:
                _ready.add(key)
        except Exception as e:
            logger.err("Could not ensure hot path indexes:", e)


def build_hot_path_indexes(database=None, timeout_seconds=INDEX_BUILD_TIMEOUT_SECONDS):
    """Open a dedicated connection and create missing hot-path indexes."""
    from config import db_path

    path = db_path if database is None else database
    conn = connect_sqlite(path, timeout_seconds=timeout_seconds)
    try:
        ensure_hot_path_indexes(conn, path)
        try:
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()
