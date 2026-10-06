# -*- coding: utf-8 -*-
"""Menu states and the Telegram cache live in SQLite, not gdbm. Temp files only.

The shelves never gave space back (30 MB of data in 975 MB of files) and
could be compacted only with the bot stopped.

Run from the repo root: python app/repository/storage/test_sqlite_storage.py
"""
import datetime
import json
import os
import shelve
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.repository.storage import storage as storage_module  # noqa: E402
from app.repository.storage import telegram_cache  # noqa: E402
from app.repository.storage.shelve_migration import migrate_shelves_to_sqlite  # noqa: E402
from db import runtime_kv  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def test_menu_states(db):
    storage_module.storage = storage_module._FsmStore(database=db)
    s = storage_module
    _assert_eq(s.get_user_states(7), None, "no states at start")
    s.add_user_state(7, "menu")
    s.add_user_state(7, "podcast")
    _assert_eq(s.get_user_states(7), ["menu", "podcast"], "states stack")
    _assert_eq(s.get_user_prev_curr_states(7), ("menu", "podcast"), "prev and current")
    s.set_user_state_data(7, "recs", {"p": 2, "search": "news"})
    _assert_eq(s.get_user_state_data(7, "recs"), {"p": 2, "search": "news"}, "state data")
    s.del_user_curr_state(7)
    _assert_eq(s.get_user_curr_state(7), "menu", "pop current state")
    _assert_eq(runtime_kv.get_kv("fsm:7_states", database=db), '["menu"]',
               "stored in bot_runtime_kv")
    s.clear_user_storage(7)
    _assert_eq(s.get_user_states(7), None, "clear removes states")
    _assert_eq(s.get_user_state_data(7, "recs"), None, "clear removes data")

    os.environ["YOURCAST_ROLE"] = "updater"
    try:
        s.storage["7_states"]
    except RuntimeError:
        print("ok  updater may not touch menu states")
    else:
        raise AssertionError("updater read a menu state")
    finally:
        del os.environ["YOURCAST_ROLE"]


def test_cache_expiry(db):
    now = 1_000_000.0
    telegram_cache._save("audio:a", "FILE_A", now + 60, now=now, database=db)
    telegram_cache._save("strCache:q", [{"title": "x"}], now + 5, now=now, database=db)
    _assert_eq(telegram_cache._get("audio:a", now=now + 1, database=db), "FILE_A", "file id")
    _assert_eq(telegram_cache._get("strCache:q", now=now + 1, database=db),
               [{"title": "x"}], "json value round trip")
    _assert_eq(telegram_cache._get("strCache:q", now=now + 6, database=db), None, "expired")
    telegram_cache._save("strCache:old", "x", now + 1, now=now, database=db)
    telegram_cache._save("img:b", "FILE_B", now + 60, now=now + 10, database=db)
    conn = telegram_cache._connect(db)
    left = [r[0] for r in conn.execute("SELECT key FROM telegram_cache ORDER BY key")]
    conn.close()
    _assert_eq(left, ["audio:a", "img:b"], "a save drops entries nobody read again")


def test_migration(db, tmp):
    fsm_path = os.path.join(tmp, "shelve.db")
    cache_path = os.path.join(tmp, "shelve_telegram_cache.db")
    now = datetime.datetime(2026, 10, 6, 12, 0).timestamp()
    with shelve.open(fsm_path) as old:
        old["11_states"] = json.dumps(["menu", "recs"])
        old["-100500_states_data"] = json.dumps({"recs": {"p": 3}})
        old["12_states"] = json.dumps(["menu"])
        old["11_resend_flag"] = True           # moved to sqlite long ago
        old["users:tg:11:message_structures"] = "[]"
    with shelve.open(cache_path) as old:
        old["audio:https://cdn/x.mp3"] = json.dumps(
            {"t": "FILE_X", "exp": str(datetime.datetime(2026, 11, 1))})
        old["strCache:gone"] = json.dumps(
            {"t": "old", "exp": str(datetime.datetime(2026, 10, 1))})
    runtime_kv.set_kv("fsm:12_states", '["menu", "subs"]', database=db)

    _assert_eq(migrate_shelves_to_sqlite(fsm_path, cache_path, database=db, now=now),
               True, "first start moves the shelves")
    _assert_eq(runtime_kv.get_kv("fsm:11_states", database=db), '["menu", "recs"]',
               "menu state moved")
    _assert_eq(runtime_kv.get_kv("fsm:-100500_states_data", database=db),
               '{"recs": {"p": 3}}', "group chat state data moved")
    _assert_eq(runtime_kv.get_kv("fsm:12_states", database=db), '["menu", "subs"]',
               "a newer sqlite state is not overwritten")
    _assert_eq(runtime_kv.get_kv("fsm:11_resend_flag", database=db), None,
               "leftover keys are not copied")
    _assert_eq(telegram_cache._get("audio:https://cdn/x.mp3", now=now, database=db),
               "FILE_X", "live cache entry moved")
    _assert_eq(telegram_cache._get("strCache:gone", now=now, database=db), None,
               "expired cache entry dropped")
    _assert_eq(migrate_shelves_to_sqlite(fsm_path, cache_path, database=db, now=now),
               False, "later starts do nothing")

    missing = os.path.join(tmp, "nothing.db")
    db2 = os.path.join(tmp, "fresh.sqlite")
    _assert_eq(migrate_shelves_to_sqlite(missing, missing, database=db2, now=now),
               True, "no shelves (fresh install) still marks the move done")


def main():
    tmp = tempfile.mkdtemp(prefix="yourcast_sqlite_storage_")
    test_menu_states(os.path.join(tmp, "fsm.sqlite"))
    test_cache_expiry(os.path.join(tmp, "cache.sqlite"))
    test_migration(os.path.join(tmp, "migrate.sqlite"), tmp)
    print("all sqlite storage checks passed")


if __name__ == "__main__":
    main()
