# -*- coding: utf-8 -*-
"""Who is on which plan now, for /usersCount: per level, paid for, a trial (nobody paid; of them the
survey's week, `users.flags` `why_reward`) or a grant's (db/plan_grants.py), and the live chats with no
plan.

Paid for is `tariff_rows.paid_for_days`: a payment (not the creator's tests) or a Patreon
replenishment. A user with two live tariff rows counts once, at the higher level. Read-only; a table
the database does not have yet counts as empty.
Lock: python db/test_plan_counts.py
"""
from db.connection import connect_sqlite

PLAN_NAMES = {1: 'Bronze', 2: 'Silver', 3: 'Relay'}
GRANT_NAMES = {'channels': 'за подписку на каналы'}
HOLDERS_SHOWN = 20


def format_lines(plans: dict) -> str:
    """Plans now, per level: paid / trial (the survey's weeks among them) / a grant's; the grants'
    holders; no plan."""
    lines = ["Тарифы сейчас (оплачен / триал / бесплатно):"]
    for level, counts in sorted(plans['levels'].items()):
        survey = " (из них неделя за опрос: %d)" % counts['survey'] if counts.get('survey') else ""
        lines.append("%s: %d / %d / %d%s" % (
            PLAN_NAMES.get(level, "уровень %d" % level),
            counts['paid'], counts['trial'], counts['granted'], survey))
    holders = plans['holders']
    kinds = {}
    for _, kind in holders:
        kinds[kind] = kinds.get(kind, 0) + 1
    for kind, count in sorted(kinds.items()):
        lines.append("Бесплатный тариф %s: %d" % (GRANT_NAMES.get(kind, kind), count))
    if holders:
        shown = ", ".join(str(telegram_id) for telegram_id, _ in holders[:HOLDERS_SHOWN])
        more = len(holders) - HOLDERS_SHOWN
        lines.append("Кто: " + shown + (" и ещё %d" % more if more > 0 else ""))
    lines.append("Без тарифа: %d" % plans['no_plan'])
    return "\n".join(lines)


def _has(connection, table) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def running(database, creator_id) -> dict:
    """{'levels': {level: {'paid', 'trial', 'survey', 'granted'}}, 'holders': [(telegram_id, kind)],
    'no_plan': n}; `survey` is among `trial`."""
    connection = connect_sqlite(database)
    try:
        paid = []
        if _has(connection, 'payment_history'):
            paid.append("EXISTS(SELECT 1 FROM payment_history p WHERE p.user_id = u.id "
                        "AND p.status = 'paid' AND u.telegramId != :creator)")
        if _has(connection, 'payment_service_user_data'):
            paid.append("EXISTS(SELECT 1 FROM payment_service_user_data s WHERE s.user_id = u.id "
                        "AND s.last_replenishment IS NOT NULL)")
        grants = _has(connection, 'plan_grants')
        held = ("EXISTS(SELECT 1 FROM plan_grants g WHERE g.user_id = u.id AND g.ended_at IS NULL "
                "AND g.tariff_id = utc.tariff_id)" if grants else "0")
        has_flags = any(row[1] == 'flags' for row in connection.execute("PRAGMA table_info(users)"))
        survey = ("json_extract(COALESCE(u.flags, '{}'), '$.why_reward') IS NOT NULL" if has_flags else "0")
        rows = connection.execute(
            "SELECT level, COUNT(*), SUM(held), SUM(NOT held AND paid), SUM(NOT held AND NOT paid AND survey) "
            "FROM (SELECT u.id, MAX(t.level) level, MAX(%s) held, MAX(%s) paid, MAX(%s) survey "
            "FROM users u JOIN user_tariff_cs utc ON utc.uid = u.id JOIN tariffs t ON t.id = utc.tariff_id "
            "WHERE u.deleted_at IS NULL AND utc.tariff_id > 0 AND utc.time_left > 0 GROUP BY u.id) "
            "GROUP BY level ORDER BY level" % (held, " OR ".join(paid) or "0", survey),
            {'creator': int(creator_id)}).fetchall()
        levels = {int(level): {'paid': int(paid_n), 'trial': int(total - held_n - paid_n),
                               'survey': int(survey_n), 'granted': int(held_n)}
                  for level, total, held_n, paid_n, survey_n in rows}
        holders = []
        if grants:
            holders = [(row[0], row[1]) for row in connection.execute(
                "SELECT u.telegramId, g.kind FROM plan_grants g JOIN users u ON u.id = g.user_id "
                "JOIN user_tariff_cs utc ON utc.uid = u.id AND utc.tariff_id = g.tariff_id "
                "WHERE g.ended_at IS NULL AND u.deleted_at IS NULL AND utc.time_left > 0 "
                "GROUP BY u.id ORDER BY g.started_at")]
        live = connection.execute("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL").fetchone()[0]
        on_plan = sum(counts['paid'] + counts['trial'] + counts['granted'] for counts in levels.values())
        return {'levels': levels, 'holders': holders, 'no_plan': int(live) - on_plan}
    finally:
        connection.close()
