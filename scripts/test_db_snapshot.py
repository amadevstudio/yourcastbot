# -*- coding: utf-8 -*-
"""The nightly backup archives a consistent copy of the live database.

Run from the repo root: python scripts/test_db_snapshot.py
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from db_snapshot import SnapshotError, snapshot  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _raises(exc, fn, label):
    try:
        fn()
    except exc as e:
        print("ok  %s (%s)" % (label, e))
        return e
    raise AssertionError("%s: %s not raised" % (label, exc.__name__))


def _live_db(path):
    """As the bot opens it: WAL, synchronous=NORMAL."""
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("CREATE TABLE IF NOT EXISTS pay (id INTEGER PRIMARY KEY, batch INT, amount INT)")
    conn.commit()
    return conn


def test_wal_only_changes_are_in_the_copy(tmp):
    src = os.path.join(tmp, "wal.db")
    conn = _live_db(src)
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.executemany("INSERT INTO pay (batch, amount) VALUES (?, ?)", [(1, 5)] * 100)
    conn.commit()
    _assert(os.path.getsize(src + "-wal") > 0, "rows sit in -wal, not yet in the main file")

    dst = os.path.join(tmp, "copy.db")
    snapshot(src, dst)
    conn.close()
    _assert(not os.path.exists(dst + "-wal"), "the copy is one self-contained file")
    copy = sqlite3.connect(dst)
    _assert(copy.execute("SELECT COUNT(*) FROM pay").fetchone()[0] == 100,
            "the copy has the rows that were only in -wal")
    _assert(copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete",
            "the copy is not in WAL mode")
    copy.close()


def test_copy_under_writes_is_consistent(tmp):
    """Every transaction writes a +1 and a -1: a torn copy breaks the zero sum."""
    src = os.path.join(tmp, "busy.db")
    conn = _live_db(src)
    conn.executemany("INSERT INTO pay (batch, amount) VALUES (?, ?)",
                     [(b, s) for b in range(20000) for s in (1, -1)])
    conn.commit()
    stop = threading.Event()

    def writer():
        batch = 100000
        while not stop.is_set():
            with conn:
                conn.execute("INSERT INTO pay (batch, amount) VALUES (?, 1)", (batch,))
                conn.execute("INSERT INTO pay (batch, amount) VALUES (?, -1)", (batch,))
            batch += 1

    t = threading.Thread(target=writer)
    t.start()
    try:
        for i in range(5):
            dst = os.path.join(tmp, "busy_copy_%d.db" % i)
            snapshot(src, dst)
            copy = sqlite3.connect(dst)
            rows, total = copy.execute("SELECT COUNT(*), SUM(amount) FROM pay").fetchone()
            copy.close()
            _assert(rows % 2 == 0 and total == 0 and rows >= 40000,
                    "copy %d taken during writes is whole (%d rows, sum 0)" % (i, rows))
    finally:
        stop.set()
        t.join()
        conn.close()


def test_missing_source_is_an_error_not_an_empty_db(tmp):
    src = os.path.join(tmp, "nope.db")
    _raises(SnapshotError, lambda: snapshot(src, os.path.join(tmp, "nope_copy.db")),
            "a missing database is an error")
    _assert(not os.path.exists(src), "the missing source is not created")


def test_broken_copy_is_refused_by_the_cli(tmp):
    src = os.path.join(tmp, "broken.db")
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("CREATE INDEX t_v ON t (v)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [("x" * 200,)] * 2000)
    conn.commit()
    conn.close()
    with open(src, "r+b") as f:  # garbage over pages in the middle of the file
        f.seek(os.path.getsize(src) // 2)
        f.write(b"\xff" * 8192)

    dst = os.path.join(tmp, "broken_copy.db")
    script = os.path.join(_HERE, "db_snapshot.py")
    r = subprocess.run([sys.executable, script, src, dst], capture_output=True, text=True)
    _assert(r.returncode == 1, "the CLI exits 1 on a broken copy (%s)" % r.stderr.strip()[:80])
    _assert(not os.path.exists(dst), "a broken copy is not left for tar")

    good = os.path.join(tmp, "wal.db")
    r = subprocess.run([sys.executable, script, good, dst], capture_output=True, text=True)
    _assert(r.returncode == 0 and "integrity ok" in r.stdout, "the CLI exits 0 on a good copy")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_wal_only_changes_are_in_the_copy(tmp)
        test_copy_under_writes_is_consistent(tmp)
        test_missing_source_is_an_error_not_an_empty_db(tmp)
        test_broken_copy_is_refused_by_the_cli(tmp)
    print("all db_snapshot tests passed")


if __name__ == "__main__":
    main()
