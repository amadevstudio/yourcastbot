# -*- coding: utf-8 -*-
"""Reusable smoke check for connect_sqlite (WAL + busy_timeout + concurrent access).

Uses a temporary file DB only — never opens production databases.
Run from the repo root: python db/test_connection.py
"""
import os
import sqlite3
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.connection import connect_sqlite  # noqa: E402


def _pragma(conn, name):
    row = conn.execute("PRAGMA %s" % name).fetchone()
    return row[0]


def _assert_pragmas(conn, label):
    journal_mode = str(_pragma(conn, "journal_mode"))
    busy_timeout = int(_pragma(conn, "busy_timeout"))
    synchronous = int(_pragma(conn, "synchronous"))
    print("%s: journal_mode=%s busy_timeout=%s synchronous=%s" % (
        label, journal_mode, busy_timeout, synchronous))
    if journal_mode.lower() != "wal":
        raise AssertionError("%s: expected journal_mode=wal, got %r" % (label, journal_mode))
    if busy_timeout != 30000:
        raise AssertionError("%s: expected busy_timeout=30000, got %r" % (label, busy_timeout))
    if synchronous != 1:  # NORMAL
        raise AssertionError("%s: expected synchronous=NORMAL (1), got %r" % (label, synchronous))


def _writer(db_path, stop, errors, stats):
    conn = connect_sqlite(db_path)
    try:
        while not stop.is_set():
            conn.execute("INSERT INTO t (v) VALUES (?)", (1,))
            conn.commit()
            stats["writes"] += 1
    except Exception as exc:
        errors.append(exc)
    finally:
        conn.close()


def _reader(db_path, stop, errors, stats):
    conn = connect_sqlite(db_path)
    try:
        while not stop.is_set():
            conn.execute("SELECT COUNT(*) FROM t").fetchone()
            stats["reads"] += 1
    except Exception as exc:
        errors.append(exc)
    finally:
        conn.close()


def _is_locked(exc):
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    return "database is locked" in str(exc).lower()


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_wal_")
    db_path = os.path.join(tmpdir, "smoke.db")
    conns = []
    try:
        for i in range(3):
            conn = connect_sqlite(db_path)
            conns.append(conn)
            _assert_pragmas(conn, "conn[%d]" % i)

        conns[0].execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
        conns[0].commit()

        errors = []
        stats = {"writes": 0, "reads": 0}
        stop = threading.Event()
        threads = [threading.Thread(target=_writer, args=(db_path, stop, errors, stats))]
        for _ in range(4):
            threads.append(threading.Thread(target=_reader, args=(db_path, stop, errors, stats)))
        for thread in threads:
            thread.start()
        time.sleep(2.0)
        stop.set()
        for thread in threads:
            thread.join(timeout=10)
            if thread.is_alive():
                raise AssertionError("thread did not finish after stop")

        locked = [exc for exc in errors if _is_locked(exc)]
        if locked:
            raise AssertionError("database is locked: %r" % locked)
        if errors:
            raise AssertionError("unexpected errors: %r" % errors)
        if stats["writes"] < 1 or stats["reads"] < 1:
            raise AssertionError("no work done: %r" % stats)
        print("concurrent: writes=%d reads=%d errors=0" % (stats["writes"], stats["reads"]))
        print("OK")
    finally:
        for conn in conns:
            try:
                conn.close()
            except Exception:
                pass
        for name in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, name))
        os.rmdir(tmpdir)


if __name__ == "__main__":
    main()
