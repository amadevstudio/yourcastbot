# -*- coding: utf-8 -*-
"""Every user is paid or free: a user with no tariff row is "no tariff". Temp DB only.

653 users had no user_tariff_cs row (registered before the tariff system, or
created by get_user_by_tg's fallback). `NULL != 0` is not true, so they were in
neither of get_uccs_by_channel's two lists: their channels were polled and
skipped, the feed never fetched, nothing ever sent (1116 channels). Two layers:
the free list is the exact, NULL-safe complement of the paid one, and the
supervisor gives every user without a row the "no tariff" row at start.
Run from the repo root: python db/test_tariff_rows.py
"""
import ast
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.admin_web import diag  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402
from db.tariff_rows import ensure_tariff_rows  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


PAID, EXPIRED, NO_ROW, NULL_COUNT, BLOCKED_NO_ROW = 9001, 9002, 9003, 9004, 9005


def _fixture():
    path = os.path.join(tempfile.mkdtemp(prefix="yourcast_tariff_rows_"), "t.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER UNIQUE, lang TEXT,
            deleted_at TEXT, nosub_digest_sent_at TEXT, created_at TEXT);
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER, notify_count INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER NOT NULL, tariff_id INTEGER NOT NULL,
            balance INTEGER, notify_count INTEGER, time_left INTEGER);
        CREATE TABLE user_channel_cs (id INTEGER PRIMARY KEY, user_telegram_id INTEGER,
            channel_id INTEGER, last_guid TEXT, last_date TEXT, notify INTEGER);
        INSERT INTO tariffs VALUES (3, 3, 500, -1);
        INSERT INTO users (id, telegramId) VALUES (1, 9001), (2, 9002), (3, 9003), (4, 9004), (5, 9005);
        UPDATE users SET deleted_at = '2026-10-01 10:00:00' WHERE id = 5;
        INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) VALUES
            (1, 3, 500, -1, 400),
            (2, 3, 500, -1, 0),
            (4, 3, 500, NULL, 400);
        INSERT INTO user_channel_cs (user_telegram_id, channel_id, notify) VALUES
            (9001, 7, 1), (9002, 7, 1), (9003, 7, 1), (9004, 7, 1), (9005, 7, 1);
    """)
    conn.commit()
    conn.close()
    return path


def _lists(path, channel=7):
    db = SQLighter(path)
    try:
        paid = {r['user_telegram_id'] for r in db.get_uccs_by_channel(
            channel, have_subscription=True, notifications_enabled=True)}
        free = {r['user_telegram_id'] for r in db.get_uccs_by_channel(
            channel, have_subscription=False, notifications_enabled=True)}
    finally:
        db.close()
    return paid, free


def test_free_list_is_the_complement():
    path = _fixture()
    paid, free = _lists(path)
    _assert_eq(paid, {PAID}, "paid: only the one with a live tariff")
    _assert_eq(free, {EXPIRED, NO_ROW, NULL_COUNT}, "free: expired, no row at all, a NULL in the row")
    _assert_eq(paid & free, set(), "nobody is in both lists")
    _assert_eq(paid | free, {PAID, EXPIRED, NO_ROW, NULL_COUNT},
               "every live listener is in exactly one list (the blocked one is in neither, as before)")


def test_heal():
    path = _fixture()
    _assert_eq(ensure_tariff_rows(path), 2, "the two users with no row get one (the blocked one too)")
    conn = sqlite3.connect(path)
    try:
        rows = {r[0]: r[1:] for r in conn.execute(
            "SELECT u.telegramId, ut.tariff_id, ut.balance, ut.notify_count, ut.time_left "
            "FROM users u JOIN user_tariff_cs ut ON ut.uid = u.id")}
    finally:
        conn.close()
    _assert_eq(rows[NO_ROW], (0, 0, 0, 0), "the row is 'no tariff': id 0, no balance, no days, no notifies")
    _assert_eq(rows[BLOCKED_NO_ROW], (0, 0, 0, 0), "every user has one")
    _assert_eq(rows[PAID], (3, 500, -1, 400), "a paid user is not touched")
    _assert_eq(rows[EXPIRED], (3, 500, -1, 0), "an expired one is not touched")
    _assert_eq(rows[NULL_COUNT], (3, 500, None, 400), "a row with a NULL is not touched either")
    _assert_eq(ensure_tariff_rows(path), 0, "idempotent: the second start gives nobody anything")

    paid, free = _lists(path)
    _assert_eq((paid, free), ({PAID}, {EXPIRED, NO_ROW, NULL_COUNT}), "the lists are the same after the heal")

    db = SQLighter(path)
    try:
        _assert_eq(db.is_user_have_bot_subscription(NO_ROW), False, "no tariff: not a subscriber")
        _assert_eq([r['telegramId'] for r in db.get_users_nearing_expiry(72)], [],
                   "and never told a plan is ending (tariff_id 0 joins no plan)")
    finally:
        db.close()

    ro = diag.connect_ro(path)
    try:
        text = diag.as_text(diag.orphan_listeners, ro)
    finally:
        ro.close()
    _assert_eq("no usable tariff row: 1 users" in text, True,
               "the diagnostics see only the user whose row has a NULL (the free list takes him)")


def test_nothing_to_heal_on_a_bare_database():
    path = os.path.join(tempfile.mkdtemp(prefix="yourcast_tariff_rows_"), "empty.db")
    sqlite3.connect(path).close()
    _assert_eq(ensure_tariff_rows(path), 0, "a database without the tables: nothing, no error")


def test_supervisor_heals_at_start():
    tree = ast.parse(open(os.path.join(_ROOT, "main.py"), encoding="utf-8").read())
    main = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")
    tries = [n for n in ast.walk(main) if isinstance(n, ast.Try) and "ensure_tariff_rows" in ast.dump(n)]
    _assert_eq(len(tries), 1, "main() heals the tariff rows before the supervisor starts, in a try")
    run = [n.lineno for n in ast.walk(main) if isinstance(n, ast.Call) and ast.unparse(n.func) == "run_supervisor"]
    _assert_eq(tries[0].lineno < run[0], True, "and before the children are spawned")


def main():
    for case in (test_free_list_is_the_complement, test_heal,
                 test_nothing_to_heal_on_a_bare_database, test_supervisor_heals_at_start):
        print("-- %s" % case.__name__)
        case()
    print("all tariff rows checks passed")


if __name__ == "__main__":
    main()
