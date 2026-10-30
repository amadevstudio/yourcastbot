# -*- coding: utf-8 -*-
"""How the product is used: the admin page "Product".

Over a period: the newcomers' funnel (came, subscribed to a show of their
own, got an episode, asked for a summary, paid, blocked the bot), plans and
payments, AI summaries and questions, the digest; and the newcomers by
week; the share of newcomers who paid in their first 30 days. Money per
user is the economics page; behaviour in the bot (taps,
the digest's clicks) is Amplitude's.

Every new user is subscribed to the welcome show (welcomeModule), so
"subscribed" counts a show other than that one. Deliveries and questions
come from the usage ledger (db/usage.py): before it there are none. The
creator's own test payments are not payments, as on the economics page.
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Optional

import config
from app.admin_web.dbutil import connect
from app.service.payment.plan_end import WELCOME_CHANNEL_ID  # the show every newcomer gets
from db import ai, payments, usage

ENDING_HOURS = 72  # a trial "ends soon": the D-3 reminder's window
MAX_WEEKS = 13
PAY_DAYS = 30  # "paid within the first N days": the share of newcomers that pay
_FMT = '%Y-%m-%d %H:%M:%S'


def _stamp(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime(_FMT)


_PAID = ("EXISTS(SELECT 1 FROM payment_history p WHERE p.user_id = u.id "
         "AND p.status = 'paid' AND u.telegramId != :creator)")
_OWN_SUB = ("EXISTS(SELECT 1 FROM user_channel_cs s WHERE s.user_telegram_id = u.telegramId "
            "AND s.channel_id != :welcome)")
_GOT_EPISODE = ("EXISTS(SELECT 1 FROM usage_events e WHERE e.user_id = u.telegramId "
                "AND e.kind IN ('rec', 'circle'))")
_ASKED_SUMMARY = "EXISTS(SELECT 1 FROM ai_requests r WHERE r.chat_id = u.telegramId)"


def _newcomers(conn, params) -> tuple[dict, list]:
    rows = conn.execute(
        "SELECT u.created_at, u.deleted_at IS NOT NULL blocked, %s own_sub, %s got_episode, "
        "%s asked_summary, %s paid FROM users u WHERE u.created_at >= :since AND u.created_at < :until"
        % (_OWN_SUB, _GOT_EPISODE, _ASKED_SUMMARY, _PAID), params).fetchall()
    keys = ('own_sub', 'got_episode', 'asked_summary', 'paid', 'blocked')
    total = {'new': len(rows), **{key: 0 for key in keys}}
    weeks: dict = {}
    for row in rows:
        try:
            created = datetime.datetime.strptime(str(row['created_at'])[:19], _FMT)
        except ValueError:
            continue
        week = weeks.setdefault(created.date() - datetime.timedelta(days=created.weekday()),
                                {'new': 0, **{key: 0 for key in keys}})
        week['new'] += 1
        for key in keys:
            total[key] += int(bool(row[key]))
            week[key] += int(bool(row[key]))
    ordered = [{'week': day.isoformat(), **weeks[day]} for day in sorted(weeks, reverse=True)]
    return total, ordered[:MAX_WEEKS]


def _paid_first_days(conn, params) -> dict:
    """Newcomers of the period whose first PAY_DAYS are over, and who paid in them: all of
    them, and those who subscribed to a show of their own. A share over a fixed window does
    not move when a trial starts later or ends sooner; "paid" over the period would."""
    row = conn.execute(
        "SELECT COUNT(*) matured, COALESCE(SUM(paid), 0) paid, COALESCE(SUM(own_sub), 0) own_sub, "
        "COALESCE(SUM(own_sub AND paid), 0) own_sub_paid FROM (SELECT %s own_sub, "
        "EXISTS(SELECT 1 FROM payment_history p WHERE p.user_id = u.id AND p.status = 'paid' "
        "AND u.telegramId != :creator AND p.datetime < datetime(u.created_at, :window)) paid "
        "FROM users u WHERE u.created_at >= :since AND u.created_at < :matured)" % _OWN_SUB,
        {**params, 'window': '+%d days' % PAY_DAYS}).fetchone()
    return {'days': PAY_DAYS, **{key: int(row[key]) for key in ('matured', 'paid', 'own_sub', 'own_sub_paid')}}


def _plans(conn, params) -> dict:
    row = conn.execute(
        "SELECT COALESCE(SUM(%s), 0) paid, COALESCE(SUM(NOT %s), 0) trial, "
        "COALESCE(SUM(NOT %s AND utc.time_left <= :ending AND COALESCE(utc.balance, 0) < t.price), 0) "
        "trial_ending FROM users u JOIN user_tariff_cs utc ON utc.uid = u.id "
        "JOIN tariffs t ON t.id = utc.tariff_id "
        "WHERE utc.tariff_id > 0 AND utc.time_left > 0 AND u.deleted_at IS NULL"
        % (_PAID, _PAID, _PAID), params).fetchone()
    return {key: int(row[key]) for key in ('paid', 'trial', 'trial_ending')}


def _payments(conn, params) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) payments, COUNT(DISTINCT p.user_id) payers, COALESCE(SUM(%s), 0) cents, "
        % payments.revenue_sql(conn) +
        "COUNT(DISTINCT CASE WHEN NOT EXISTS(SELECT 1 FROM payment_history o WHERE o.user_id = p.user_id "
        "AND o.status = 'paid' AND o.datetime < :since) THEN p.user_id END) first_time "
        "FROM payment_history p JOIN users u ON u.id = p.user_id "
        "WHERE p.status = 'paid' AND p.datetime >= :since AND p.datetime < :until "
        "AND u.telegramId != :creator", params).fetchone()
    return {'payments': int(row['payments']), 'payers': int(row['payers']),
            'first_time': int(row['first_time']), 'revenue_usd': round(row['cents'] / 100.0, 2)}


def _ai(conn, since: float, until: float) -> dict:
    row = conn.execute(
        "SELECT COALESCE(SUM(auto = 0), 0) taps, COALESCE(SUM(auto = 1), 0) auto, "
        "COALESCE(SUM(status = 'done'), 0) done, COALESCE(SUM(status = 'failed'), 0) failed, "
        "COUNT(DISTINCT chat_id) chats FROM ai_requests WHERE created_at >= ? AND created_at < ?",
        (since, until)).fetchone()
    asked = conn.execute(
        "SELECT COUNT(*) questions, COUNT(DISTINCT user_id) chats, COALESCE(SUM(cost_usd), 0) usd "
        "FROM usage_events WHERE kind = 'ask' AND at >= ? AND at < ?", (since, until)).fetchone()
    spend = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM usage_events "
                         "WHERE kind IN ('ai', 'ask') AND at >= ? AND at < ?", (since, until)).fetchone()[0]
    auto_on = conn.execute(
        "SELECT COUNT(*) FROM users WHERE deleted_at IS NULL "
        "AND json_extract(COALESCE(flags, '{}'), '$.auto_summary')").fetchone()[0]
    return {'summary_taps': int(row['taps']), 'summary_auto': int(row['auto']),
            'summary_done': int(row['done']), 'summary_failed': int(row['failed']),
            'summary_chats': int(row['chats']), 'questions': int(asked['questions']),
            'question_chats': int(asked['chats']), 'auto_on': int(auto_on),
            'ai_usd': round(float(spend), 4)}


def _activity(conn, since: float, until: float) -> dict:
    row = conn.execute(
        "SELECT COUNT(DISTINCT CASE WHEN kind = 'rec' THEN user_id END) clickers, "
        "COALESCE(SUM(kind = 'rec'), 0) clicks, COALESCE(SUM(kind = 'circle'), 0) automatic, "
        "COUNT(DISTINCT CASE WHEN kind IN ('rec', 'circle') THEN user_id END) listeners "
        "FROM usage_events WHERE at >= ? AND at < ?", (since, until)).fetchone()
    return {key: int(row[key]) for key in ('clickers', 'clicks', 'automatic', 'listeners')}


def _digest(conn, now: float) -> dict:
    row = conn.execute(
        "SELECT COALESCE(SUM(nosub_digest_sent_at >= :week), 0) last_week, "
        "COALESCE(SUM(nosub_digest_enabled = 0), 0) muted FROM users WHERE deleted_at IS NULL",
        {'week': _stamp(now - 7 * 86400)}).fetchone()
    return {'last_week': int(row['last_week']), 'muted': int(row['muted'])}


def product(days: int = 30, database: Optional[str] = None, now: Optional[float] = None) -> dict[str, Any]:
    days = max(1, min(int(days), 365))
    until = time.time() if now is None else now
    since = until - days * 86400
    usage.connect(database).close()  # the ledger and the AI queue exist even before their first row
    ai.connect(database).close()
    params = {'since': _stamp(since), 'until': _stamp(until), 'creator': int(config.creatorId),
              'matured': _stamp(until - PAY_DAYS * 86400),
              'welcome': WELCOME_CHANNEL_ID, 'ending': ENDING_HOURS}
    conn = connect(database)
    try:
        newcomers, weeks = _newcomers(conn, params)
        return {
            'days': days,
            'newcomers': newcomers,
            'weeks': weeks,
            'plans': _plans(conn, params),
            'payments': _payments(conn, params),
            'paid_first_days': _paid_first_days(conn, params),
            'ai': _ai(conn, since, until),
            'activity': _activity(conn, since, until),
            'digest': _digest(conn, until),
            'ledger_since': _ledger_since(conn),
        }
    finally:
        conn.close()


def _ledger_since(conn) -> Optional[str]:
    first = conn.execute("SELECT MIN(at) FROM usage_events").fetchone()[0]
    return _stamp(first) if first else None
