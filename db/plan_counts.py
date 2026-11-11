# -*- coding: utf-8 -*-
"""Who is on which plan now, for /usersCount: per level, paid for, a trial (nobody paid; of them the
survey's week, `users.flags` `why_reward`) or a grant's (db/plan_grants.py), and the live chats with no
plan.

Paid for is `tariff_rows.paid_for_days`: a payment or a Patreon replenishment. The creator's
account is in no line: its plan is paid by tests and its own Patreon address. A user with two live tariff rows counts once, at the higher level. Read-only; a table
the database does not have yet counts as empty.
Lock: python db/test_plan_counts.py
"""
from db.connection import connect_sqlite

PLAN_NAMES = {1: 'Bronze', 2: 'Silver', 3: 'Relay'}
GRANT_NAMES = {'channels': 'за каналы'}
HOLDERS_SHOWN = 20


def format_lines(plans: dict) -> str:
    """The /usersCount plans block (HTML): no plan in the header, a line per level that has anyone
    (paid, trial with the survey's weeks among them, a grant's; zeros left out), the grants' holders."""
    holders = plans['holders']
    kinds = sorted({kind for _, kind in holders})
    granted = GRANT_NAMES.get(kinds[0], kinds[0]) if len(kinds) == 1 else "бесплатно"
    lines = ["💳 <b>Тарифы</b> · без тарифа %d" % plans['no_plan']]
    for level, counts in sorted(plans['levels'].items(), reverse=True):
        parts = []
        if counts['paid']:
            parts.append("%d опл." % counts['paid'])
        if counts['trial']:
            survey = " (%d за опрос)" % counts['survey'] if counts.get('survey') else ""
            parts.append("%d триал%s" % (counts['trial'], survey))
        if counts['granted']:
            parts.append("%d %s" % (counts['granted'], granted))
        if parts:
            lines.append("%s: %s" % (PLAN_NAMES.get(level, "уровень %d" % level), " · ".join(parts)))
    for kind in kinds:
        ids = [telegram_id for telegram_id, held in holders if held == kind]
        shown = ", ".join("<code>%s</code>" % telegram_id for telegram_id in ids[:HOLDERS_SHOWN])
        more = len(ids) - HOLDERS_SHOWN
        lines.append("%s: %s%s" % (GRANT_NAMES.get(kind, kind).capitalize(), shown,
                                   " и ещё %d" % more if more > 0 else ""))
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
                        "AND p.status = 'paid')")
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
            "WHERE u.deleted_at IS NULL AND u.telegramId != :creator AND utc.tariff_id > 0 AND utc.time_left > 0 GROUP BY u.id) "
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
                "WHERE g.ended_at IS NULL AND u.deleted_at IS NULL AND u.telegramId != ? AND utc.time_left > 0 "
                "GROUP BY u.id ORDER BY g.started_at", (int(creator_id),))]
        live = connection.execute("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL AND telegramId != ?",
                                  (int(creator_id),)).fetchone()[0]
        on_plan = sum(counts['paid'] + counts['trial'] + counts['granted'] for counts in levels.values())
        return {'levels': levels, 'holders': holders, 'no_plan': int(live) - on_plan}
    finally:
        connection.close()
