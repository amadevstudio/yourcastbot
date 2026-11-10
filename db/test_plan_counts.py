# -*- coding: utf-8 -*-
"""/usersCount's plans: per level paid / trial / a grant's, the grants' holders, no plan.

Temporary databases only, made-up ids. Run from the repo root: python db/test_plan_counts.py
"""
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db import plan_counts  # noqa: E402
from app.controller.builders.adminModule import format_plan_lines  # noqa: E402

CREATOR = 9000


def _db(path, grants=True, payments=True, flags=True):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, deleted_at TEXT%s)"
              % (", flags TEXT" if flags else ""))
    c.executescript("""
        CREATE TABLE tariffs (id INTEGER PRIMARY KEY, level INTEGER, price INTEGER);
        CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER,
            balance INTEGER, notify_count INTEGER, time_left INTEGER);
        INSERT INTO tariffs VALUES (1, 1, 100), (2, 2, 200), (3, 3, 500);
    """)
    if payments:
        c.executescript("""
            CREATE TABLE payment_history (user_id INTEGER, status TEXT, amount INTEGER);
            CREATE TABLE payment_service_user_data (user_id INTEGER, last_replenishment TEXT);
        """)
    if grants:
        c.execute("CREATE TABLE plan_grants (id INTEGER PRIMARY KEY, user_id INTEGER, kind TEXT, "
                  "tariff_id INTEGER, started_at REAL, ended_at REAL)")
    return c


def test_counts():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'p.db')
        c = _db(path)
        users = [
            # id, telegramId, deleted, tariff, time_left
            (1, 7001, None, 3, 100),   # Relay paid by Stars
            (2, 7002, None, 3, 100),   # Relay trial
            (3, 7003, None, 3, 100),   # Relay paid by Patreon
            (4, 7004, None, 1, 100),   # Bronze by the channels grant
            (5, 7005, None, 1, 0),     # Bronze run out: no plan
            (6, 7006, None, 0, 0),     # no plan
            (7, 7007, '2026-01-01', 3, 100),  # blocked: nowhere
            (8, CREATOR, None, 3, 100),       # the creator's test payment is not paid
            (9, 7009, None, 2, 50),    # Silver with two rows: once
            (10, 7010, None, 1, 100),  # Bronze, an ended grant, paid since
        ]
        for uid, tg, deleted, tariff, left in users:
            c.execute("INSERT INTO users (id, telegramId, deleted_at) VALUES (?, ?, ?)", (uid, tg, deleted))
            c.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) "
                      "VALUES (?, ?, 0, -1, ?)", (uid, tariff, left))
        c.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) "
                  "VALUES (9, 2, 0, -1, 50)")
        c.executemany("INSERT INTO payment_history VALUES (?, ?, 500)",
                      [(1, 'paid'), (2, 'refunded'), (8, 'paid'), (10, 'paid')])
        c.execute("INSERT INTO payment_service_user_data VALUES (3, '2026-10-01')")
        # the survey's week: 7002's trial; 7001 paid after it, so paid
        c.execute("""UPDATE users SET flags = '{"why_reward": 1}' WHERE id IN (1, 2)""")
        c.execute("INSERT INTO plan_grants (user_id, kind, tariff_id, started_at) VALUES (4, 'channels', 1, 1)")
        c.execute("INSERT INTO plan_grants (user_id, kind, tariff_id, started_at, ended_at) "
                  "VALUES (10, 'channels', 1, 1, 2)")
        c.commit()
        c.close()

        got = plan_counts.running(path, CREATOR)
        assert got['levels'] == {
            1: {'paid': 1, 'trial': 0, 'survey': 0, 'granted': 1},
            2: {'paid': 0, 'trial': 1, 'survey': 0, 'granted': 0},
            3: {'paid': 2, 'trial': 2, 'survey': 1, 'granted': 0},
        }, got
        assert got['holders'] == [(7004, 'channels')], got
        assert got['no_plan'] == 2, got  # 7005, 7006
        text = format_plan_lines(got)
        for line in ("Bronze: 1 / 0 / 1", "Silver: 0 / 1 / 0", "Relay: 2 / 2 / 0 (из них неделя за опрос: 1)",
                     "Бесплатный тариф за подписку на каналы: 1", "Кто: 7004", "Без тарифа: 2"):
            assert line in text, (line, text)
        print("ok  plans per level, grant holders, no plan")


def test_old_schema():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'p.db')
        c = _db(path, grants=False, payments=False, flags=False)
        c.execute("INSERT INTO users (id, telegramId) VALUES (1, 7001)")
        c.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) "
                  "VALUES (1, 3, 0, -1, 10)")
        c.commit()
        c.close()
        got = plan_counts.running(path, CREATOR)
        assert got == {'levels': {3: {'paid': 0, 'trial': 1, 'survey': 0, 'granted': 0}},
                       'holders': [], 'no_plan': 0}, got
        print("ok  no grants, payments or flags yet")


def test_many_holders():
    text = format_plan_lines({'levels': {1: {'paid': 0, 'trial': 0, 'granted': 25}},
                              'holders': [(7100 + i, 'channels') for i in range(25)], 'no_plan': 0})
    assert "и ещё 5" in text and "7119" in text and "7120" not in text, text
    print("ok  holders past the first 20 are a count")


if __name__ == '__main__':
    test_counts()
    test_old_schema()
    test_many_holders()
