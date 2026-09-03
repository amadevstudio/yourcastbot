# -*- coding: utf-8 -*-
"""bot_runtime_kv + updater cursor in sqlite, not gdbm.

Uses a temporary file DB only — never opens production databases.
Run from the repo root: python db/test_runtime_kv.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db import runtime_kv  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def test_round_trip(db_path):
    runtime_kv.set_kv("last_channel_id", "42", database=db_path)
    _assert_eq(
        runtime_kv.get_kv("last_channel_id", database=db_path),
        "42", "stored last_channel_id")
    runtime_kv.delete_kv("last_channel_id", database=db_path)
    _assert_eq(
        runtime_kv.get_kv("last_channel_id", database=db_path),
        None, "deleted key is gone")


def test_sqlighter_creates_table(db_path):
    db = SQLighter(db_path)
    try:
        names = [
            row[0] for row in db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        if "bot_runtime_kv" not in names:
            raise AssertionError("missing bot_runtime_kv")
        print("ok  SQLighter creates bot_runtime_kv")
    finally:
        db.close()


def test_incr_kv(db_path):
    runtime_kv._ready.clear()
    _assert_eq(runtime_kv.incr_kv("fail_1", database=db_path), 1, "first incr")
    _assert_eq(runtime_kv.incr_kv("fail_1", database=db_path), 2, "second incr")
    _assert_eq(
        runtime_kv.get_kv("fail_1", database=db_path), "2", "stored incr")


def test_thonbot_rejected_for_updater_role():
    os.environ["YOURCAST_ROLE"] = "updater"
    try:
        from agent import bot_telethon
        try:
            bot_telethon.get_thonbot()
            raise AssertionError("updater must not open file Telethon session")
        except RuntimeError as e:
            if "bot-only" not in str(e):
                raise
            print("ok  updater cannot open file Telethon session")
    finally:
        os.environ.pop("YOURCAST_ROLE", None)


def test_uploader_session_reads_file_without_client(tmpdir):
    import agent.bot_telethon as m
    path = os.path.join(tmpdir, "yourcastbot_uploader.session")
    with open(path, "w") as fh:
        fh.write("TESTSESSIONSTRING\n")
    old_path = m.uploader_session
    old_cached = m._uploader_session_string
    m.uploader_session = path
    m._uploader_session_string = None
    try:
        got = m.get_uploader_session_string()
        _assert_eq(got, "TESTSESSIONSTRING", "string session from disk")
    finally:
        m.uploader_session = old_path
        m._uploader_session_string = old_cached


def test_migrate_from_shelve(tmpdir, db_path):
    import shelve
    shelve_path = os.path.join(tmpdir, "shelve_src")
    db = shelve.open(shelve_path)
    try:
        db["last_channel_id"] = "17"
        db["last_channel_restarted"] = "1"
    finally:
        db.close()
    copied = runtime_kv.migrate_updater_state_from_shelve(
        shelve_path=shelve_path, database=db_path)
    _assert_eq(copied, True, "migrated from shelve")
    _assert_eq(
        runtime_kv.get_kv("last_channel_id", database=db_path),
        "17", "migrated cursor")
    copied_again = runtime_kv.migrate_updater_state_from_shelve(
        shelve_path=shelve_path, database=db_path)
    _assert_eq(copied_again, False, "second migrate is a no-op")


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_runtime_kv_")
    cases = (
        test_round_trip,
        test_sqlighter_creates_table,
        test_incr_kv,
    )
    for index, case in enumerate(cases):
        path = os.path.join(tmpdir, "case_%d.db" % index)
        print("-- %s" % case.__name__)
        case(path)
    print("-- test_migrate_from_shelve")
    test_migrate_from_shelve(
        tmpdir, os.path.join(tmpdir, "migrate.db"))
    print("-- test_shelve_rejected_for_updater_role")
    os.environ["YOURCAST_ROLE"] = "updater"
    try:
        import app.repository.storage.storage as storage_mod
        try:
            storage_mod._get_shelve()
            raise AssertionError("updater must not open FSM shelve")
        except RuntimeError as e:
            if "bot process" not in str(e):
                raise
            print("ok  updater cannot open FSM shelve")
    finally:
        os.environ.pop("YOURCAST_ROLE", None)
    print("-- test_thonbot_rejected_for_updater_role")
    test_thonbot_rejected_for_updater_role()
    print("-- test_uploader_session_reads_file_without_client")
    test_uploader_session_reads_file_without_client(tmpdir)
    print("all runtime_kv checks passed")


if __name__ == "__main__":
    main()
