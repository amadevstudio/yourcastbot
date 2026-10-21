# -*- coding: utf-8 -*-
"""Who brings money and who costs it: the admin economics page.

Per chat over a period: deliveries (clicks, automatic), MB we downloaded,
AI spend (db/usage.py), revenue (payment_history). The server's monthly
bill is a fixed cost spread over the chats that used the bot, by load:
one delivery is one unit, LOAD_MB_PER_UNIT downloaded MB another.

Revenue is the balance a payment credited (cents), the creator's own test
payments left out. A discounted Stars bundle credits more than it charged,
so revenue from bundles reads a little high.
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Optional

import config
from app.admin_web.dbutil import connect
from db import usage

LOAD_MB_PER_UNIT = 50
SEGMENTS = ('paid', 'trial', 'free')
TOP_USERS = 500


def _load(row) -> float:
    return row['rec'] + row['circle'] + row['mb'] / LOAD_MB_PER_UNIT


def _segments(conn) -> dict[int, tuple[str, int]]:
    """{telegram id: (segment, tariff level)} for users with a running plan.

    paid: a running plan and a payment at any time; trial: a running plan
    nobody paid for (the welcome or referral days). Everyone else is free.
    The creator's own test payments are not payments, as in _revenue.
    """
    rows = conn.execute(
        "SELECT u.telegramId tg, t.level level, u.telegramId != ? AND "
        "EXISTS(SELECT 1 FROM payment_history p WHERE p.user_id = u.id AND p.status = 'paid') paid "
        "FROM users u JOIN user_tariff_cs utc ON utc.uid = u.id "
        "JOIN tariffs t ON t.id = utc.tariff_id "
        "WHERE utc.tariff_id > 0 AND utc.time_left > 0", (int(config.creatorId),)).fetchall()
    return {int(r['tg']): ('paid' if r['paid'] else 'trial', int(r['level'])) for r in rows}


def _channel_owners(conn) -> dict:
    """A Telegram channel's deliveries count toward the user who added it (tg_channels.user_id
    is a Telegram id). A channel is kept by its id or, added by link, its @name."""
    return {usage.chat_key(r['tg_id']): int(r['user_id'])
            for r in conn.execute("SELECT tg_id, user_id FROM tg_channels")}


def _revenue(conn, since: float, until: float) -> dict[int, float]:
    fmt = '%Y-%m-%d %H:%M:%S'
    start = datetime.datetime.fromtimestamp(since).strftime(fmt)
    end = datetime.datetime.fromtimestamp(until).strftime(fmt)
    rows = conn.execute(
        "SELECT u.telegramId tg, SUM(p.amount) cents FROM payment_history p "
        "JOIN users u ON u.id = p.user_id "
        "WHERE p.status = 'paid' AND p.datetime >= ? AND p.datetime < ? AND u.telegramId != ? "
        "GROUP BY u.telegramId", (start, end, int(config.creatorId))).fetchall()
    return {int(r['tg']): (r['cents'] or 0) / 100.0 for r in rows}


def _empty() -> dict[str, Any]:
    return {'users': 0, 'rec': 0, 'circle': 0, 'ai': 0, 'mb': 0.0,
            'ai_usd': 0.0, 'revenue_usd': 0.0, 'fixed_usd': 0.0, 'margin_usd': 0.0}


def _add(total: dict, row: dict) -> None:
    total['users'] += 1
    for key in ('rec', 'circle', 'ai', 'mb', 'ai_usd', 'revenue_usd', 'fixed_usd', 'margin_usd'):
        total[key] += row[key]


def _rounded(row: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}


def economics(days: int = 30, database: Optional[str] = None, now: Optional[float] = None,
              server_usd_month: Optional[float] = None) -> dict[str, Any]:
    days = max(1, min(int(days), 365))
    until = time.time() if now is None else now
    since = until - days * 86400
    server = config.server_usd_month if server_usd_month is None else server_usd_month
    fixed_total = float(server) * days / 30.0

    conn = connect(database)
    try:
        segments = _segments(conn)
        owners = _channel_owners(conn)
        revenue = _revenue(conn, since, until)
    finally:
        conn.close()

    rows: dict = {}
    for chat_id, used in usage.per_user(since, until, database=database).items():
        tg = owners.get(usage.chat_key(chat_id), chat_id)
        row = rows.setdefault(tg, {'rec': 0, 'circle': 0, 'ai': 0, 'mb': 0.0, 'ai_usd': 0.0})
        for key in row:
            row[key] += used[key]
    for tg in revenue:
        rows.setdefault(tg, {'rec': 0, 'circle': 0, 'ai': 0, 'mb': 0.0, 'ai_usd': 0.0})

    total_load = sum(_load(row) for row in rows.values())
    users = []
    for tg, row in rows.items():
        segment, level = segments.get(tg, ('free', 0))
        fixed = fixed_total * _load(row) / total_load if total_load else 0.0
        income = revenue.get(tg, 0.0)
        users.append({'tg': tg, 'segment': segment, 'level': level, **row,
                      'revenue_usd': income, 'fixed_usd': fixed,
                      'margin_usd': income - row['ai_usd'] - fixed})

    totals = _empty()
    by_segment = {name: _empty() for name in SEGMENTS}
    for row in users:
        _add(totals, row)
        _add(by_segment[row['segment']], row)
    # the bill is paid whether or not anybody used the bot
    unallocated = fixed_total - totals['fixed_usd']
    totals['fixed_usd'] = fixed_total
    totals['margin_usd'] -= unallocated

    users.sort(key=lambda row: (row['margin_usd'], -_load(row)))
    return {
        'days': days,
        'server_usd_month': float(server),
        'load_mb_per_unit': LOAD_MB_PER_UNIT,
        'totals': _rounded(totals),
        'segments': [{'segment': name, **_rounded(by_segment[name])} for name in SEGMENTS],
        'users': [_rounded(row) for row in users[:TOP_USERS]],
    }
