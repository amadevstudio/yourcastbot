# -*- coding: utf-8 -*-
"""/usersCount's newcomers, languages and money (db/admin_counts.py): who came in a day, a week and a
month, the biggest languages and the rest, the last 30 days' payments by method with the packs
among them and the refunds, the balances; the creator's account in none.

Temporary databases only, made-up ids. Run from the repo root: python db/test_admin_counts.py
"""
import datetime
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db import admin_counts  # noqa: E402

CREATOR = 9000
NOW = datetime.datetime(2026, 11, 20, 12, 0, 0).timestamp()


def _utc(days_ago):
    return datetime.datetime.fromtimestamp(NOW - days_ago * 86400, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _local(days_ago):
    return str(datetime.datetime.fromtimestamp(NOW - days_ago * 86400))


def _db(path, created_at=True, charged=True):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, telegramId INTEGER, lang TEXT, deleted_at TEXT%s)"
              % (", created_at TEXT" if created_at else ""))
    c.execute("CREATE TABLE user_tariff_cs (id INTEGER PRIMARY KEY, uid INTEGER, tariff_id INTEGER, "
              "balance INTEGER, notify_count INTEGER, time_left INTEGER)")
    c.execute("CREATE TABLE payment_history (user_id INTEGER, service_type TEXT, invoice_id TEXT, status TEXT, "
              "amount INTEGER, datetime TEXT%s)" % (", charged INTEGER" if charged else ""))
    return c


def test_counts():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'a.db')
        c = _db(path)
        users = [
            # id, telegramId, lang, deleted, joined days ago
            (1, 7001, 'en', None, 0.5),
            (2, 7002, 'en', None, 3),
            (3, 7003, 'fa', '2026-11-19', 3),   # came this week, blocked since: a newcomer, not live
            (4, 7004, 'fa', None, 20),
            (5, 7005, 'ES', None, 40),
            (6, 7006, None, None, None),        # before created_at: no newcomer, no language
            (7, 7007, 'None', None, None),
            (8, 7008, 'de', None, None),
            (9, 7009, 'he', None, None),
            (10, 7010, 'pt-br', None, None),
            (11, 7011, 'ru', None, None),
            (12, CREATOR, 'ru', None, 0.1),     # the creator: a newcomer by date, in no other count
        ]
        for uid, tg, lang, deleted, joined in users:
            c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                      (uid, tg, lang, deleted, _utc(joined) if joined is not None else None))
        c.executemany("INSERT INTO payment_history VALUES (?, ?, ?, ?, ?, ?, ?)", [
            (1, 'telegramStars', 'a', 'paid', 600, _local(2), 500),        # a bundle: credited 6, charged 5
            (2, 'telegramStarsPack', 'b', 'paid', 65, _local(1), 65),
            (4, 'cryptoBot', 'c', 'paid', 100, _local(10), None),          # before `charged`: the amount
            (5, 'telegramStars', 'd', 'refunded', 500, _local(5), 500),
            (5, 'telegramStars', 'e', 'paid', 500, _local(31), 500),       # older than 30 days
            (12, 'cryptoBot', 'f', 'paid', 100, _local(1), 100),           # the creator's test
            (4, 'patreon', '2026-11', 'credited', 0, _local(3), None),     # a pledge of nothing
        ])
        c.executemany("INSERT INTO user_tariff_cs (uid, tariff_id, balance, notify_count, time_left) "
                      "VALUES (?, 3, ?, -1, 0)", [(1, 250), (1, 50), (2, -500), (3, 900), (4, 100000), (12, 7000)])
        c.commit()
        c.close()

        got = admin_counts.counts(path, CREATOR, now=NOW)
        assert got['new'] == (2, 4, 5), got['new']
        assert got['languages'] == [('en', 2), ('de', 1), ('es', 1), ('fa', 1), ('he', 1), ('pt-br', 1)], \
            got['languages']
        assert got['other_languages'] == 3, got['other_languages']  # ru, none, 'None'
        print("ok  newcomers by day, week, month (blocked since too); languages, the rest; the creator in none")

        money = got['money']
        assert money == {'payments': 3, 'cents': 665, 'methods': [('⭐', 2), ('CryptoBot', 1)], 'packs': 1,
                         'pack_cents': 65, 'refunded': 1, 'balance_cents': 100300, 'balance_users': 2}, money
        print("ok  30 days' payments charged, by method, packs among them, refunds; live balances")

        assert admin_counts.format_money(money) == (
            "💰 <b>За 30 дней</b>: 3 платежа на $6.65 (⭐ 2, CryptoBot 1)\n"
            "Пакеты 1 на $0.65 · возвращено 1 · на балансах $1 003.00 у 2"), admin_counts.format_money(money)
        quiet = dict(money, payments=0, cents=0, methods=[], packs=0, pack_cents=0, refunded=0,
                     balance_cents=0, balance_users=0)
        assert admin_counts.format_money(quiet) == "💰 <b>За 30 дней</b>: платежей нет\nПакеты 0"
        words = [admin_counts.format_money(dict(money, payments=n)).split(" на ")[0].split(": ")[1]
                 for n in (1, 2, 5, 11, 21, 112)]
        assert words == ["1 платёж", "2 платежа", "5 платежей", "11 платежей", "21 платёж", "112 платежей"], words
        print("ok  the money block: payments in the header; packs, refunds and balances in one line")


def test_old_schema():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'a.db')
        c = _db(path, created_at=False, charged=False)
        c.execute("INSERT INTO users VALUES (1, 7001, 'en', NULL)")
        c.execute("INSERT INTO payment_history VALUES (1, 'robokassa', 'x', 'paid', 300, ?)", (_local(1),))
        c.commit()
        c.close()
        got = admin_counts.counts(path, CREATOR, now=NOW)
        assert got['new'] is None and got['languages'] == [('en', 1)], got
        assert got['money']['cents'] == 300 and got['money']['methods'] == [('Robokassa', 1)], got
        sqlite3.connect(path).execute("DROP TABLE payment_history").connection.commit()
        assert admin_counts.counts(path, CREATOR, now=NOW)['money']['payments'] == 0
        print("ok  no created_at, no charged, no payments yet")


if __name__ == '__main__':
    test_counts()
    test_old_schema()
