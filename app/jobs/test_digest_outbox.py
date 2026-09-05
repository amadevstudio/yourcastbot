# -*- coding: utf-8 -*-
"""digest_outbox queue. Temp file DB only — never production yourcast.db.

Run from the repo root: python app/jobs/test_digest_outbox.py
"""
import os
import sys
import tempfile
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.sender.outbox import OutboxRetryableError  # noqa: E402
from app.jobs import digest_outbox  # noqa: E402
from app.jobs.nosub_digest import should_send_nosub_digest  # noqa: E402
from db import runtime_kv  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _assert_true(got, label):
    if not got:
        raise AssertionError("%s: expected truthy, got %r" % (label, got))
    print("ok  %s" % label)


def _fresh(db_path):
    digest_outbox.clear_ready_for_tests()
    import db.sqliteAdapter as sqlite_adapter
    sqlite_adapter._digest_outbox_ready.clear()
    sqlite_adapter._runtime_kv_ready.clear()
    sqlite_adapter._send_outbox_ready.clear()
    sqlite_adapter._users_digest_ready.clear()
    sqlite_adapter._users_deleted_at_checked = False
    sqlite_adapter._channel_http_validators_checked = False
    runtime_kv._ready.clear()
    return db_path


def _claim_and_done(db_path, expected_uid):
    job = digest_outbox.claim(database=db_path)
    _assert_true(job is not None, "claim returned a job")
    _assert_eq(job["user_telegram_id"], expected_uid, "claimed user")
    digest_outbox.mark_done(
        job["user_telegram_id"], database=db_path, attempts=job["attempts"])
    return job


def test_enqueue_is_idempotent(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(1001, database=db_path)
    digest_outbox.enqueue(1001, database=db_path)
    digest_outbox.enqueue(1002, database=db_path)
    _assert_eq(digest_outbox.pending_count(database=db_path), 2, "two distinct users")
    first = digest_outbox.claim(database=db_path)
    second = digest_outbox.claim(database=db_path)
    third = digest_outbox.claim(database=db_path)
    got = sorted([
        first["user_telegram_id"], second["user_telegram_id"]])
    _assert_eq(got, [1001, 1002], "claimed both users")
    _assert_eq(third, None, "queue empty")
    digest_outbox.mark_done(
        first["user_telegram_id"], database=db_path,
        attempts=first["attempts"])
    digest_outbox.mark_done(
        second["user_telegram_id"], database=db_path,
        attempts=second["attempts"])
    _assert_eq(digest_outbox.pending_count(database=db_path), 0, "count after drain")
    _assert_eq(
        digest_outbox.get_row(1001, database=db_path)["status"],
        "done", "done row kept")


def test_enqueue_requeues_done(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(1101, database=db_path)
    _claim_and_done(db_path, 1101)
    _assert_eq(digest_outbox.pending_count(database=db_path), 0, "drained")
    digest_outbox.enqueue(1101, database=db_path)
    _assert_eq(digest_outbox.pending_count(database=db_path), 1, "requeued")
    row = digest_outbox.get_row(1101, database=db_path)
    _assert_eq(row["status"], "pending", "done became pending")
    _assert_eq(row["attempts"], 0, "attempts reset")


def test_enqueue_does_not_reset_leased(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(1201, database=db_path)
    job = digest_outbox.claim(database=db_path)
    digest_outbox.enqueue(1201, database=db_path)
    row = digest_outbox.get_row(1201, database=db_path)
    _assert_eq(row["status"], "leased", "still leased")
    _assert_eq(row["attempts"], job["attempts"], "attempts unchanged")


def test_migrate_from_kv_json_array(db_path):
    _fresh(db_path)
    runtime_kv.set_kv(
        digest_outbox.KV_FLAG_KEY, "[3001, 3001, 3002]", database=db_path)
    moved = digest_outbox.migrate_from_kv(database=db_path)
    _assert_eq(moved, 3, "three enqueue calls including duplicate")
    _assert_eq(digest_outbox.pending_count(database=db_path), 2, "dup collapsed")
    _assert_eq(
        runtime_kv.get_kv(digest_outbox.KV_FLAG_KEY, database=db_path),
        None, "kv key removed")


def test_deleted_user_is_not_due():
    _assert_eq(
        should_send_nosub_digest({
            "telegramId": 1,
            "deleted_at": "2026-09-04 18:00:00",
            "nosub_digest_enabled": 1,
            "nosub_digest_sent_at": None,
        }),
        False,
        "deleted user skipped")


def test_storage_flag_enqueues(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(4004, database=db_path)
    _assert_eq(digest_outbox.pending_count(database=db_path), 1, "flagged")


def test_sqlighter_creates_digest_outbox(db_path):
    _fresh(db_path)
    db = SQLighter(db_path)
    try:
        names = [
            row[0] for row in db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        _assert_true("digest_outbox" in names, "table exists")
        columns = [
            row[1] for row in db.connection.execute(
                "PRAGMA table_info(digest_outbox)").fetchall()]
        for required in (
                "user_telegram_id", "created_at", "status", "attempts",
                "leased_until", "available_at"):
            _assert_true(required in columns, "column %s" % required)
    finally:
        db.close()


def test_old_two_column_table_gains_lease(db_path):
    _fresh(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE digest_outbox ("
        "user_telegram_id INTEGER PRIMARY KEY, "
        "created_at TEXT NOT NULL)")
    conn.execute(
        "INSERT INTO digest_outbox (user_telegram_id, created_at) "
        "VALUES (5005, '2026-01-01 00:00:00')")
    conn.commit()
    conn.close()
    job = digest_outbox.claim(database=db_path)
    _assert_eq(job["user_telegram_id"], 5005, "legacy row claimable")
    row = digest_outbox.get_row(5005, database=db_path)
    _assert_eq(row["status"], "leased", "legacy row leased")


def test_parallel_ensure_on_legacy_table(db_path):
    _fresh(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE digest_outbox ("
        "user_telegram_id INTEGER PRIMARY KEY, "
        "created_at TEXT NOT NULL)")
    conn.commit()
    conn.close()
    errors = []

    def worker():
        try:
            digest_outbox.clear_ready_for_tests()
            digest_outbox.enqueue(5100 + threading.get_ident() % 100,
                                  database=db_path)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        if thread.is_alive():
            raise AssertionError("ensure thread did not finish")
    _assert_eq(errors, [], "parallel ensure does not raise")
    _assert_true(
        digest_outbox.pending_count(database=db_path) >= 1,
        "legacy table accepted enqueues")


def test_crash_after_lease_reclaim(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(6006, database=db_path)
    job = digest_outbox.claim(database=db_path)
    _assert_eq(job["user_telegram_id"], 6006, "claimed")
    skipped = digest_outbox.reclaim(database=db_path, force=False)
    _assert_eq(skipped, 0, "unexpired in-flight not reclaimed")
    digest_outbox.clear_in_flight()
    db = SQLighter(db_path)
    try:
        db.cursor.execute(
            "UPDATE digest_outbox SET leased_until = ? "
            "WHERE user_telegram_id = ?",
            ("2000-01-01T00:00:00Z", 6006))
        db.connection.commit()
    finally:
        db.close()
    n = digest_outbox.reclaim(database=db_path, force=False)
    _assert_true(n >= 1, "expired lease reclaimed")
    row = digest_outbox.get_row(6006, database=db_path)
    _assert_eq(row["status"], "pending", "back to pending")
    claimed = digest_outbox.claim(database=db_path)
    _assert_eq(claimed["user_telegram_id"], 6006, "claimable after reclaim")


def test_fail_or_retry_uses_telegram_retry_after(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(7007, database=db_path)
    job = digest_outbox.claim(database=db_path)
    before = digest_outbox.now_iso()
    outcome = digest_outbox.fail_or_retry(
        7007,
        error=OutboxRetryableError(
            RuntimeError("Too Many Requests: retry after 37")),
        database=db_path, attempts=job["attempts"])
    _assert_eq(outcome, "pending", "429 goes back to pending")
    row = digest_outbox.get_row(7007, database=db_path)
    _assert_eq(row["status"], "pending", "row is pending")
    _assert_true(row["available_at"] > before, "available_at in the future")
    _assert_eq(
        digest_outbox.claim(database=db_path), None,
        "not claimable before retry-after")


def test_claim_is_exclusive(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(8008, database=db_path)
    results = [None, None]
    barrier = threading.Barrier(2)

    def worker(index):
        barrier.wait(timeout=5)
        results[index] = digest_outbox.claim(database=db_path)

    threads = [
        threading.Thread(target=worker, args=(0,)),
        threading.Thread(target=worker, args=(1,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        if thread.is_alive():
            raise AssertionError("claim thread did not finish")
    got = [item for item in results if item is not None]
    _assert_eq(len(got), 1, "exactly one claim wins")


def test_purge_old_leaves_live_rows(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(9001, database=db_path)
    digest_outbox.enqueue(9002, database=db_path)
    first = digest_outbox.claim(database=db_path)
    digest_outbox.mark_done(
        first["user_telegram_id"], database=db_path,
        attempts=first["attempts"])
    db = SQLighter(db_path)
    try:
        db.cursor.execute(
            "UPDATE digest_outbox SET created_at = ? "
            "WHERE user_telegram_id = ?",
            ("2000-01-01T00:00:00Z", first["user_telegram_id"]))
        db.cursor.execute(
            "UPDATE digest_outbox SET created_at = ? "
            "WHERE user_telegram_id = ?",
            ("2000-01-01T00:00:00Z", 9002))
        db.connection.commit()
    finally:
        db.close()
    counts = digest_outbox.purge_old(database=db_path)
    _assert_eq(counts["done"], 1, "old done deleted")
    _assert_eq(
        digest_outbox.get_row(first["user_telegram_id"], database=db_path),
        None, "done gone")
    _assert_eq(
        digest_outbox.get_row(9002, database=db_path)["status"],
        "pending", "ancient pending kept")


def test_clean_old_outbox_purges_digest(db_path):
    _fresh(db_path)
    from app.jobs import clean_old_data
    digest_outbox.enqueue(9101, database=db_path)
    job = digest_outbox.claim(database=db_path)
    digest_outbox.mark_done(
        9101, database=db_path, attempts=job["attempts"])
    db = SQLighter(db_path)
    try:
        db.cursor.execute(
            "UPDATE digest_outbox SET created_at = ? "
            "WHERE user_telegram_id = ?",
            ("2000-01-01T00:00:00Z", 9101))
        db.connection.commit()
    finally:
        db.close()
    clean_old_data.clean_old_outbox(database=db_path)
    _assert_eq(
        digest_outbox.get_row(9101, database=db_path), None,
        "daily job removed old digest done")


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_digest_outbox_")
    cases = (
        test_enqueue_is_idempotent,
        test_enqueue_requeues_done,
        test_enqueue_does_not_reset_leased,
        test_migrate_from_kv_json_array,
        test_storage_flag_enqueues,
        test_sqlighter_creates_digest_outbox,
        test_old_two_column_table_gains_lease,
        test_parallel_ensure_on_legacy_table,
        test_crash_after_lease_reclaim,
        test_fail_or_retry_uses_telegram_retry_after,
        test_claim_is_exclusive,
        test_purge_old_leaves_live_rows,
        test_clean_old_outbox_purges_digest,
    )
    print("-- test_deleted_user_is_not_due")
    test_deleted_user_is_not_due()
    for index, case in enumerate(cases):
        path = os.path.join(tmpdir, "case_%d.db" % index)
        if os.path.abspath(path) == os.path.abspath(os.path.join(
                _ROOT, "db", "yourcast.db")):
            raise AssertionError("refusing to use production yourcast.db")
        print("-- %s" % case.__name__)
        case(path)
    print("all digest_outbox checks passed")


if __name__ == "__main__":
    main()
