"""Win-back schedule: users whose Relay stopped, and how many of its messages they got.

A row is made when a plan stops (never for the backlog of old expiries), so
the job only ever writes to people who left since it exists. Claiming a
message moves the stage first: a retry or a second worker cannot send it
twice; a flood wait gives the stage back.
"""
import sqlite3
import threading
import time

from config import db_path
from db.connection import connect_sqlite

_ready = set()
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS winback (
    user_telegram_id INTEGER PRIMARY KEY,
    ended_at REAL NOT NULL,
    stage INTEGER NOT NULL DEFAULT 0
);
"""


def connect(database=None):
    database = db_path if database is None else database
    conn = connect_sqlite(database)
    conn.row_factory = sqlite3.Row
    with _lock:
        if database not in _ready or database == ':memory:':
            conn.executescript(SCHEMA)
            _ready.add(database)
    return conn


def start(telegram_id, now=None, database=None):
    """The plan stopped now: a new schedule from the first message."""
    conn = connect(database)
    try:
        with conn:
            conn.execute(
                "INSERT INTO winback (user_telegram_id, ended_at, stage) VALUES (?, ?, 0) "
                "ON CONFLICT(user_telegram_id) DO UPDATE SET ended_at=excluded.ended_at, stage=0",
                (int(telegram_id), time.time() if now is None else now))
    finally:
        conn.close()


def due(after_seconds, now=None, database=None):
    """[(telegram_id, stage)] whose next message is due; after_seconds[i] is stage i's delay."""
    stamp = time.time() if now is None else now
    conn = connect(database)
    try:
        found = []
        for stage, delay in enumerate(after_seconds):
            found += [(r['user_telegram_id'], stage) for r in conn.execute(
                "SELECT user_telegram_id FROM winback WHERE stage = ? AND ended_at <= ? "
                "ORDER BY ended_at", (stage, stamp - delay))]
        return found
    finally:
        conn.close()


def claim(telegram_id, stage, database=None) -> bool:
    """Take message `stage` for sending: True for one caller only."""
    conn = connect(database)
    try:
        with conn:
            return conn.execute(
                "UPDATE winback SET stage = stage + 1 WHERE user_telegram_id = ? AND stage = ?",
                (int(telegram_id), int(stage))).rowcount == 1
    finally:
        conn.close()


def give_back(telegram_id, stage, database=None):
    """A flood wait: message `stage` goes out on a later run."""
    conn = connect(database)
    try:
        with conn:
            conn.execute(
                "UPDATE winback SET stage = ? WHERE user_telegram_id = ? AND stage = ?",
                (int(stage), int(telegram_id), int(stage) + 1))
    finally:
        conn.close()


def messages_sent(telegram_id, database=None):
    """How many win-back messages the current schedule sent, None without one."""
    conn = connect(database)
    try:
        row = conn.execute("SELECT stage FROM winback WHERE user_telegram_id = ?",
                           (int(telegram_id),)).fetchone()
        return None if row is None else int(row['stage'])
    finally:
        conn.close()


def forget(telegram_id, database=None):
    """Back on a plan or gone. A finished schedule stays: it keeps the offer open."""
    conn = connect(database)
    try:
        with conn:
            conn.execute("DELETE FROM winback WHERE user_telegram_id = ?", (int(telegram_id),))
    finally:
        conn.close()
