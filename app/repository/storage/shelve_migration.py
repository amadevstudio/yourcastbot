# -*- coding: utf-8 -*-
"""One-time move of the last gdbm shelves into SQLite.

Runs in the supervisor before any child starts, while nothing holds the
gdbm files. Copies menu states (<chat>_states, <chat>_states_data) into
bot_runtime_kv and live telegram_cache entries into their table; other
shelve keys are leftovers already moved to bot_runtime_kv earlier. A
failure leaves the flag unset, so the next start tries again; the bot runs
either way (lost menu states only send users back to the menu).
"""
import datetime
import json
import os
import re
import shelve
import time

from app.repository.storage import telegram_cache
from app.repository.storage.storage import FSM_KEY_PREFIX
from config import db_path, shelve_name, telegram_cache_shelve_name
from db import runtime_kv
from db.connection import connect_sqlite
from lib.tools.logger import logger

DONE_FLAG = "shelve_migrated_v1"
_FSM_KEY = re.compile(r"^-?\d+_(states|states_data)$")


def _open_shelve(path):
    # A missing shelve has nothing to move; shelve.open(flag="r") would raise
    if not any(os.path.exists(path + suffix) for suffix in ("", ".db", ".dat")):
        return None
    return shelve.open(path, flag="r")


def _fsm_rows(path):
    db = _open_shelve(path)
    if db is None:
        return []
    try:
        rows = []
        for key in db.keys():
            if _FSM_KEY.match(key):
                rows.append((FSM_KEY_PREFIX + key, str(db[key])))
        return rows
    finally:
        db.close()


def _cache_entries(path):
    db = _open_shelve(path)
    if db is None:
        return []
    try:
        entries = []
        for key in db.keys():
            try:
                item = json.loads(db[key])
                expires = datetime.datetime.fromisoformat(item["exp"]).timestamp()
            except (ValueError, KeyError, TypeError):
                continue
            entries.append((key, item["t"], expires))
        return entries
    finally:
        db.close()


def migrate_shelves_to_sqlite(
        fsm_path=None, cache_path=None, database=None, now=None) -> bool:
    """Returns True when it moved data on this call."""
    if runtime_kv.get_kv(DONE_FLAG, database=database) == "1":
        return False
    fsm_path = shelve_name if fsm_path is None else fsm_path
    cache_path = telegram_cache_shelve_name if cache_path is None else cache_path
    now = time.time() if now is None else now
    try:
        rows = _fsm_rows(fsm_path)
        conn = connect_sqlite(db_path if database is None else database)
        conn.isolation_level = None
        try:
            runtime_kv.ensure_table(conn)
            conn.execute("BEGIN IMMEDIATE")
            # OR IGNORE: a state written to SQLite already is newer than the shelve's
            conn.executemany(
                "INSERT OR IGNORE INTO bot_runtime_kv (key, value) VALUES (?, ?)", rows)
            conn.execute("COMMIT")
        finally:
            conn.close()
        cached = telegram_cache.import_entries(
            _cache_entries(cache_path), now=now, database=database)
        runtime_kv.set_kv(DONE_FLAG, "1", database=database)
        logger.log("Moved shelves to sqlite: %d menu states, %d cache entries"
                   % (len(rows), cached))
        return True
    except Exception as e:
        logger.err("Shelve to sqlite move failed, will retry on next start:", e)
        return False
