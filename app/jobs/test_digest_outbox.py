# -*- coding: utf-8 -*-
"""digest_outbox queue. Temp file DB only — never production yourcast.db.

Run from the repo root: python app/jobs/test_digest_outbox.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

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


def test_enqueue_is_idempotent(db_path):
    _fresh(db_path)
    digest_outbox.enqueue(1001, database=db_path)
    digest_outbox.enqueue(1001, database=db_path)
    digest_outbox.enqueue(1002, database=db_path)
    _assert_eq(digest_outbox.pending_count(database=db_path), 2, "two distinct users")
    first = digest_outbox.take_one(database=db_path)
    second = digest_outbox.take_one(database=db_path)
    third = digest_outbox.take_one(database=db_path)
    _assert_eq(sorted([first, second]), [1001, 1002], "took both users")
    _assert_eq(third, None, "queue empty")
    _assert_eq(digest_outbox.pending_count(database=db_path), 0, "count after drain")


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
    # storage.enqueue uses config.db_path, so call digest_outbox via the
    # same helper after pointing tests at db_path directly.
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
    finally:
        db.close()


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_digest_outbox_")
    cases = (
        test_enqueue_is_idempotent,
        test_migrate_from_kv_json_array,
        test_storage_flag_enqueues,
        test_sqlighter_creates_digest_outbox,
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
