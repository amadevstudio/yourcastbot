# -*- coding: utf-8 -*-
"""Who brings money and who costs it: the admin economics page.

Per chat over a period: deliveries (clicks, automatic), MB we downloaded,
AI spend (db/usage.py), revenue (payment_history). The server's monthly
bill is a fixed cost spread over the chats that used the bot, by load:
one delivery is one unit, LOAD_MB_PER_UNIT downloaded MB another.

Revenue is what a payment charged (db/payments.py: a discounted Stars bundle
or offer credits more than it charged; rows from before the column read as
the balance they credited), the creator's own test payments left out, times the
share of it that reaches us (config.payout_share: Stars come through Fragment in TON).

AI by plan (`ai_plans`): what the APIs charged per hour of audio, per summary and
per question, read from what was made; the month a plan's AI could cost at most
at those rates (every hour of its quota new audio, a summary per hour, every
question of every day; the paid model for its hours only), capped by the plan's AI budget (quota.budget: a share of
what its price brings), next to its price and to what its chats used.
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Optional

import config
from app.admin_web.dbutil import connect
from app.service.ai import quota
from db import payments, tariff_rows, usage

LOAD_MB_PER_UNIT = 50
# plans are sold by Stars first: a plan's price reaches us at their share
STARS = 'telegramStars'
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
    share = ' '.join("WHEN '%s' THEN %r" % (service, float(part)) for service, part in config.payout_share.items())
    reaching = "(%s) * CASE p.service_type %s ELSE 1.0 END" % (payments.revenue_sql(conn), share) if share \
        else payments.revenue_sql(conn)
    rows = conn.execute(
        "SELECT u.telegramId tg, SUM(%s) cents FROM payment_history p " % reaching +
        "JOIN users u ON u.id = p.user_id "
        "WHERE p.status = 'paid' AND p.datetime >= ? AND p.datetime < ? AND u.telegramId != ? "
        "GROUP BY u.telegramId", (start, end, int(config.creatorId))).fetchall()
    return {int(r['tg']): (r['cents'] or 0) / 100.0 for r in rows}


def _has_table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _rate(row) -> dict[str, Any]:
    return {'usd': None if row[0] is None else round(row[0], 5), 'n': int(row[1] or 0)}


def _rates(conn) -> dict[str, dict]:
    """What the APIs charged, from everything made: per hour of audio by transcript source,
    per summary (the model call alone), per question. {'usd': None, 'n': 0} where nothing was."""
    none = {'usd': None, 'n': 0}
    rates = {'whisper': dict(none), 'speakers': dict(none), 'summary': dict(none), 'question': dict(none)}
    if _has_table(conn, 'ai_transcripts'):
        for row in conn.execute("SELECT source, SUM(cost_usd) / (SUM(seconds) / 3600.0), COUNT(*) "
                                "FROM ai_transcripts WHERE cost_usd > 0 AND seconds > 0 GROUP BY source"):
            if row[0] in rates:
                rates[row[0]] = _rate((row[1], row[2]))
    if _has_table(conn, 'ai_summaries') and _has_table(conn, 'ai_transcripts'):
        # a summary's cost includes the transcript made for it (within the same request): take that off;
        # a transcript made after the summary (made again with speakers) leaves the summary unknown
        rates['summary'] = _rate(conn.execute(
            "SELECT AVG(cost), COUNT(*) FROM (SELECT CASE "
            "WHEN t.cost_usd = 0 OR s.created_at - t.created_at > 120 THEN s.cost_usd "
            "WHEN s.created_at >= t.created_at THEN s.cost_usd - t.cost_usd END cost "
            "FROM ai_summaries s JOIN ai_transcripts t ON t.ref = s.ref WHERE s.cost_usd > 0) "
            "WHERE cost > 0").fetchone())
    if _has_table(conn, 'usage_events'):
        rates['question'] = _rate(conn.execute(
            "SELECT AVG(cost_usd), COUNT(*) FROM usage_events WHERE kind = 'ask' AND cost_usd > 0").fetchone())
    return rates


def _worst(hours: float, rates: dict, questions: int, paid_hours: float = 0.0) -> Optional[float]:
    """The most a month of the plan's AI could cost: every hour new audio (`paid_hours` of it by the
    paid model, the rest Whisper), a summary per hour, every question of the 30 days (`questions`). None while a rate
    it needs is unknown."""
    if rates['whisper']['usd'] is None or (paid_hours and rates['speakers']['usd'] is None):
        return None
    paid_hours = min(paid_hours, hours)
    return (paid_hours * (rates['speakers']['usd'] or 0.0) + (hours - paid_hours) * rates['whisper']['usd']
            + hours * (rates['summary']['usd'] or 0.0)
            + questions * (rates['question']['usd'] or 0.0))


def _hours_used(conn, since: float, until: float) -> dict[int, float]:
    """{chat id: hours of audio charged to its quota} for requests done in [since, until)."""
    if not _has_table(conn, 'ai_requests'):
        return {}
    return {int(r[0]): (r[1] or 0) / 3600.0 for r in conn.execute(
        "SELECT chat_id, SUM(seconds) FROM ai_requests WHERE status = 'done' AND created_at >= ? "
        "AND created_at < ? GROUP BY chat_id", (since, until))}


def _running(conn, database) -> dict[int, tuple[bool, int]]:
    """{telegram id: (paid for, plan level)} for chats with a plan running, paid for as the AI quota
    reads it (tariff_rows.paid_for_days: a Patreon credit too, the creator's own payments too)."""
    rows = conn.execute(
        "SELECT DISTINCT u.telegramId, t.level FROM users u JOIN user_tariff_cs ut ON ut.uid = u.id "
        "JOIN tariffs t ON t.id = ut.tariff_id WHERE ut.tariff_id > 0 AND ut.time_left > 0").fetchall()
    return {int(tg): (tariff_rows.paid_for_days(tg, database), int(level)) for tg, level in rows if tg}


def ai_plans(conn, database, since: float, until: float, spent: dict) -> dict[str, Any]:
    """Per plan level (paid for) and for plans nobody paid for: price, hours of AI a month, the worst
    month with Whisper and with the paid model, and what its chats did in the period (`spent`: AI
    dollars by telegram id)."""
    rates = _rates(conn)
    paid_model = config.ai_paid_transcribe_model or None
    prices = {int(r[0]): (r[1] or 0) / 100.0 for r in conn.execute(
        "SELECT level, MIN(price) FROM tariffs WHERE level > 0 GROUP BY level")}
    hours_used = _hours_used(conn, since, until)
    running = _running(conn, database)

    def capped(value, cap):
        return value if value is None or cap is None else min(value, cap)

    def plan(key, level, price, hours, questions, paid, paid_hours=0.0):
        month = min(questions * quota.QUOTA_DAYS, quota.month_questions(level, not paid) or questions * quota.QUOTA_DAYS)
        net = price * config.payout_share.get(STARS, 1.0)
        cap = net * config.ai_budget_share if paid else None
        chats = [tg for tg, (paid_for, lvl) in running.items() if paid_for == paid and (not paid or lvl == level)]
        used = [hours_used.get(tg, 0.0) for tg in chats]
        return {'key': key, 'level': level, 'price_usd': price, 'net_usd': net, 'cap_usd': cap, 'hours': hours,
                'questions_per_day': questions, 'questions_per_month': month,
                'paid_hours': paid_hours if paid and paid_model else 0.0,
                'worst_whisper_usd': capped(_worst(hours, rates, month), cap),
                'worst_paid_usd': capped(_worst(hours, rates, month, paid_hours), cap)
                if paid and paid_model else None,
                'chats': len(chats), 'ai_chats': sum(1 for h in used if h > 0),
                'hours_used': sum(used), 'max_hours': max(used, default=0.0),
                'ai_usd': sum(spent.get(tg, 0.0) for tg in chats)}

    plans = [plan(str(level), level, price, float(config.ai_summary_hours_per_month.get(level, 0)),
                  config.ai_questions_per_day.get(level, 0), True,
                  float(config.ai_paid_transcribe_hours_per_month.get(level, 0)))
             for level, price in sorted(prices.items())]
    plans.append(plan('trial', None, 0.0, float(config.ai_summary_trial_hours), quota.TRIAL_QUESTIONS_PER_DAY, False))
    return {'rates': rates, 'paid_model': paid_model, 'plans': [_rounded(p) for p in plans]}


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
    conn = connect(database)
    try:
        ai = ai_plans(conn, database, since, until, {row['tg']: row['ai_usd'] for row in users})
    finally:
        conn.close()
    return {
        'days': days,
        'server_usd_month': float(server),
        'payout_share': {service: float(part) for service, part in config.payout_share.items()},
        'load_mb_per_unit': LOAD_MB_PER_UNIT,
        'totals': _rounded(totals),
        'segments': [{'segment': name, **_rounded(by_segment[name])} for name in SEGMENTS],
        'users': [_rounded(row) for row in users[:TOP_USERS]],
        'ai': ai,
    }
