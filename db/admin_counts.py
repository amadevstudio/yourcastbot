# -*- coding: utf-8 -*-
"""What /usersCount adds to the plans and the circle: newcomers, languages, the last 30 days' money.

- Newcomers: rows by `users.created_at` (UTC, `datetime('now')`) in the last day, week and month,
  blocked since or not: who came. Rows from before the column have none and are in no count.
- Languages: the live chats' `users.lang` (the Telegram client's code), the biggest few and the
  rest; none or an empty one is the rest.
- Money: `payment_history` rows paid in the last 30 days (`datetime`, written in the server's local
  time) by pay method, what they charged (`payments.revenue_sql`), the packs of episodes among them
  (db/click_packs.py), payments of the period refunded since, and what the live chats hold on their
  balances. The creator's account is in none of them: its payments are tests.
Read-only; a table or column the database does not have yet counts as nothing.
Lock: python db/test_admin_counts.py
"""
import datetime
import time

from db import payments
from db.connection import connect_sqlite

LANGUAGES_SHOWN = 6
PACK = 'telegramStarsPack'
METHODS = {'telegramStars': '⭐', PACK: '⭐', 'cryptoBot': 'CryptoBot', 'robokassa': 'Robokassa',
           'patreon': 'Patreon'}


def _has(connection, table) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def _columns(connection, table) -> set:
    return {row[1] for row in connection.execute("PRAGMA table_info(%s)" % table)}


def counts(database, creator_id, now=None) -> dict:
    """{'new': (day, week, month) or None, 'languages': [(code, n)], 'other_languages': n,
    'money': {'payments', 'cents', 'methods': [(label, n)], 'packs', 'pack_cents', 'refunded',
    'balance_cents', 'balance_users'}}."""
    now = time.time() if now is None else now
    connection = connect_sqlite(database)
    try:
        return {**_newcomers(connection, now), **_languages(connection, creator_id),
                'money': _money(connection, creator_id, now)}
    finally:
        connection.close()


def _newcomers(connection, now) -> dict:
    if 'created_at' not in _columns(connection, 'users'):
        return {'new': None}
    since = [datetime.datetime.fromtimestamp(now - days * 86400, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
             for days in (1, 7, 30)]
    row = connection.execute(
        "SELECT SUM(created_at >= ?), SUM(created_at >= ?), COUNT(*) FROM users WHERE created_at >= ?",
        (since[0], since[1], since[2])).fetchone()
    return {'new': tuple(int(n or 0) for n in row)}


def _languages(connection, creator_id) -> dict:
    by_code = {}
    for lang, n in connection.execute(
            "SELECT lang, COUNT(*) FROM users WHERE deleted_at IS NULL AND telegramId != ? GROUP BY lang",
            (int(creator_id),)):
        code = (lang or '').strip().lower()
        code = '' if code == 'none' else code
        by_code[code] = by_code.get(code, 0) + int(n)
    known = sorted(((code, n) for code, n in by_code.items() if code), key=lambda item: (-item[1], item[0]))
    shown = known[:LANGUAGES_SHOWN]
    return {'languages': shown, 'other_languages': sum(by_code.values()) - sum(n for _, n in shown)}


def _money(connection, creator_id, now) -> dict:
    money = {'payments': 0, 'cents': 0, 'methods': [], 'packs': 0, 'pack_cents': 0, 'refunded': 0,
             'balance_cents': 0, 'balance_users': 0}
    if _has(connection, 'payment_history'):
        since = str(datetime.datetime.fromtimestamp(now - 30 * 86400))
        methods = {}
        for service, status, n, cents in connection.execute(
                "SELECT p.service_type, p.status, COUNT(*), SUM(%s) FROM payment_history p "
                "JOIN users u ON u.id = p.user_id WHERE p.datetime >= ? AND u.telegramId != ? "
                "AND p.status IN ('paid', 'refunded') GROUP BY 1, 2" % payments.revenue_sql(connection),
                (since, int(creator_id))):
            n, cents = int(n), int(cents or 0)
            if status == 'refunded':
                money['refunded'] += n
                continue
            money['payments'] += n
            money['cents'] += cents
            label = METHODS.get(service, service)
            methods[label] = methods.get(label, 0) + n
            if service == PACK:
                money['packs'] += n
                money['pack_cents'] += cents
        money['methods'] = sorted(methods.items(), key=lambda item: (-item[1], item[0]))
    if _has(connection, 'user_tariff_cs'):
        cents, users = connection.execute(
            "SELECT SUM(t.balance), COUNT(DISTINCT u.id) FROM user_tariff_cs t JOIN users u ON u.id = t.uid "
            "WHERE t.balance > 0 AND u.deleted_at IS NULL AND u.telegramId != ?", (int(creator_id),)).fetchone()
        money['balance_cents'], money['balance_users'] = int(cents or 0), int(users or 0)
    return money


def dollars(cents) -> str:
    """$1 225.50: a space between thousands."""
    return '$' + '{:,.2f}'.format(cents / 100.0).replace(',', ' ')


def format_money(money: dict) -> str:
    """The /usersCount money block (HTML)."""
    lines = ["💰 <b>За 30 дней</b>"]
    if money['payments']:
        methods = ", ".join("%s %d" % (label, n) for label, n in money['methods'])
        lines.append("Платежи: %d на %s (%s)" % (money['payments'], dollars(money['cents']), methods))
    else:
        lines.append("Платежей нет")
    lines.append("Пакеты выпусков: %d%s" % (
        money['packs'], " на %s" % dollars(money['pack_cents']) if money['packs'] else ""))
    if money['refunded']:
        lines.append("Возвращено: %d" % money['refunded'])
    if money['balance_users']:
        lines.append("На балансах: %s у %d" % (dollars(money['balance_cents']), money['balance_users']))
    return "\n".join(lines)
