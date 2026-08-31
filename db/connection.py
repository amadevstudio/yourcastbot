# -*- coding: utf-8 -*-
"""Shared SQLite connection helper.

Every production connection should go through connect_sqlite() so WAL,
busy_timeout, and synchronous=NORMAL are applied consistently.

New migrations and scripts that open the bot DB should import this helper
rather than calling sqlite3.connect() directly.

WAL is not enabled for :memory: / mode=memory URIs.
PRAGMA foreign_keys is not set: the existing schema has no FOREIGN KEY
constraints.
"""
import sqlite3

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_BUSY_TIMEOUT_MS = int(DEFAULT_TIMEOUT_SECONDS * 1000)


def _is_memory_database(database: str) -> bool:
    name = str(database).strip().lower()
    if name == ":memory:":
        return True
    if name.startswith("file:") and (":memory:" in name or "mode=memory" in name):
        return True
    return False


def connect_sqlite(
        database: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> sqlite3.Connection:
    # timeout= on connect IS busy_timeout, in seconds
    conn = sqlite3.connect(database, timeout=timeout_seconds)
    busy_timeout_ms = int(round(timeout_seconds * 1000))
    if not _is_memory_database(database):
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=%d" % busy_timeout_ms)
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
