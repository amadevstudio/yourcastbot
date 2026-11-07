# -*- coding: utf-8 -*-
"""One question to the listeners nearest to paying, what stops you from taking a plan,
and to the trials nobody used, what got in the way.

On 2026-11-07 none of the 66 Relay trials that had ended was paid for, and the
D-3, plan-off and win-back messages (154, with the 30% offer) brought one tap.
Free users who meet the weekly cap do not pay either. Nobody knows why, so the
bot asks them, once each:

- `limit`: no plan running and `free_rec_per_week` episodes by click in the
  last 14 days (they meet the cap or come close to it);
- `ended`: their Relay ended (`winback`) at least `ENDED_AFTER_DAYS` ago, no plan
  running now, and they used the bot themselves (a show of their own, a click,
  a summary or a transcript), not only the welcome show's files;
- `idle`: their Relay ended as above, and they used nothing (most trials: the
  welcome show's files only). They are asked what got in the way instead
  (`IDLE_ANSWERS`: how it works, their podcasts not found, another app, no
  need for podcasts in Telegram), with no offer;
- `old`: the accounts the bot has long been silent to (2026-11-07: ~10k live
  chats with no plan and no digest in 14 days, almost all from before 2026,
  9 in 10 with no subscription): what is new, why they stopped
  (`OLD_ANSWERS`) and the week's gift; the search button after the answer. Newest rows first,
  at most `OLD_PER_RUN` an hour and `why_old_limit` (config) in all, a pilot
  the owner raises after reading its blocks. One in ten (the hundreds digit
  of the id is 0) is a holdout, marked `control` and never sent: the
  revival is read against it (`survey_control`). Digest recipients stay out
  while the digest's A/B runs (to 21.11).

The message names four reasons and "I'll write it myself" (route `why`,
`whySurveyModule`); a trial's end that has not spent the offer gets the first
month at the discount under it, with change-plan (storefront rules). The first
answer of a chat the survey reached gives a week of Relay (`grant_week`, once:
`users.flags` `why_reward`): a running plan gets the hours on top, else Relay
runs for the week on the balance the chat has. A chat whose balance covers
Relay is not asked: the tick would renew the gift from that money. It goes
until `why_survey_until` (config), so the trials that end meanwhile are asked
too. `users.flags` `why_survey`: unsent, then sent (a crash in between never
sends it twice); `why_group` the group it was sent for. Never to a blocked
chat, never fails the jobs role.
Lock: python app/jobs/test_why_survey.py
"""
import time

from app.service import analytics_events
from app.service.payment.plan_end import WELCOME_CHANNEL_ID
from config import db_path, free_rec_per_week, why_old_limit, why_survey_until
from db.connection import connect_sqlite
from lib.tools.logger import logger

SURVEY_FLAG = "why_survey"
ACTION = "why"  # the route its buttons open
PAY_ANSWERS = ("price", "pay", "free", "need", "own")
IDLE_ANSWERS = ("how", "find", "app", "tg", "own")
OLD_ANSWERS = ("forgot", "app", "missing", "tg", "own")
ANSWERS = tuple(dict.fromkeys(PAY_ANSWERS + IDLE_ANSWERS + OLD_ANSWERS))
OLD_PER_RUN = 300
DIGEST_DAYS = 14
GROUP_FLAG = "why_group"
REWARD_FLAG = "why_reward"
REWARD_HOURS = 7 * 24
LIMIT_DAYS = 14
ENDED_AFTER_DAYS = 2
CHECK_SECONDS = 3600


def open_until(now=None) -> bool:
    import datetime
    now = time.time() if now is None else now
    return datetime.datetime.fromtimestamp(now, datetime.timezone.utc).date().isoformat() <= why_survey_until


def due(database=None, now=None) -> list:
    """[(telegram id, lang, group)] not asked yet, here still, no plan running."""
    from db.tariff_rows import running_plan_level
    from config import creatorId
    from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL
    now = time.time() if now is None else now
    database = db_path if database is None else database
    connection = connect_sqlite(database)
    unmarked = ("u.telegramId > 0 AND u.deleted_at IS NULL "
                "AND json_extract(COALESCE(u.flags, '{}'), '$.%s') IS NULL" % SURVEY_FLAG)
    try:
        limit = connection.execute(
            "SELECT u.telegramId, u.lang FROM users u JOIN usage_events e ON e.user_id = u.telegramId "
            "WHERE %s AND e.kind = 'rec' AND e.at >= ? GROUP BY u.telegramId "
            "HAVING COUNT(DISTINCT e.ref) >= ?" % unmarked,
            (now - LIMIT_DAYS * 86400, free_rec_per_week)).fetchall()
        trials = connection.execute(
            "SELECT u.telegramId, u.lang, ("
            "EXISTS (SELECT 1 FROM user_channel_cs s WHERE s.user_telegram_id = u.telegramId "
            "AND s.channel_id != ?) "
            "OR EXISTS (SELECT 1 FROM usage_events e WHERE e.user_id = u.telegramId "
            "AND e.kind IN ('rec', 'ai', 'transcript', 'ask'))) "
            "FROM users u JOIN winback w ON w.user_telegram_id = u.telegramId "
            "WHERE %s AND w.ended_at <= ?" % unmarked,
            (WELCOME_CHANNEL_ID, now - ENDED_AFTER_DAYS * 86400)).fetchall()
        covered = {row[0] for row in connection.execute(
            "SELECT u.telegramId FROM users u JOIN user_tariff_cs ut ON ut.uid = u.id "
            "WHERE ut.balance >= (SELECT price FROM tariffs WHERE level = ?)", (SHOWCASE_TARIFF_LEVEL,))}
        taken = connection.execute(
            "SELECT COUNT(*) FROM users WHERE json_extract(COALESCE(flags, '{}'), '$.%s') = 'old'"
            % GROUP_FLAG).fetchone()[0]
        room = max(0, min(OLD_PER_RUN, int(why_old_limit) - int(taken)))
        old = connection.execute(
            "SELECT u.telegramId, u.lang FROM users u LEFT JOIN user_tariff_cs ut ON ut.uid = u.id "
            "WHERE %s AND COALESCE(ut.time_left, 0) <= 0 "
            "AND (u.nosub_digest_sent_at IS NULL OR u.nosub_digest_sent_at < datetime(?, 'unixepoch')) "
            "AND NOT EXISTS (SELECT 1 FROM winback w WHERE w.user_telegram_id = u.telegramId) "
            "ORDER BY u.id DESC LIMIT ?" % unmarked,
            (now - DIGEST_DAYS * 86400, room + 50)).fetchall() if room else []
    finally:
        connection.close()
    found = {}
    ended = [(tg, lang) for tg, lang, used in trials if used]
    idle = [(tg, lang) for tg, lang, used in trials if not used]
    for group, rows in (("ended", ended), ("limit", limit), ("idle", idle), ("old", old)):
        for telegram_id, lang in rows:
            found.setdefault(telegram_id, (telegram_id, lang, group))
    rows = [row for telegram_id, row in found.items()
            if telegram_id != int(creatorId) and telegram_id not in covered
            and running_plan_level(telegram_id, database) <= 0]
    old_rows = [row for row in rows if row[2] == "old"][:room]
    return [row for row in rows if row[2] != "old"] + old_rows


def holdout(telegram_id) -> bool:
    """One old account in ten is not sent the revival: what it is read against."""
    return (abs(int(telegram_id)) // 100) % 10 == 0


def grant_week(telegram_id, database=None, now=None) -> int:
    """The survey's thanks: REWARD_HOURS of Relay, once, to a chat the survey reached. A running plan
    gets the hours on top; else Relay runs for them (the balance stays). The hours given, 0 when none."""
    from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL
    now = time.time() if now is None else now
    connection = connect_sqlite(db_path if database is None else database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute(
            "SELECT id, json_extract(COALESCE(flags, '{}'), '$.%s'), json_extract(COALESCE(flags, '{}'), '$.%s') "
            "FROM users WHERE telegramId = ?" % (SURVEY_FLAG, REWARD_FLAG), (int(telegram_id),)).fetchone()
        relay = connection.execute(
            "SELECT id, notify_count FROM tariffs WHERE level = ?", (SHOWCASE_TARIFF_LEVEL,)).fetchone()
        if user is None or user[1] != "sent" or user[2] is not None or relay is None:
            connection.rollback()
            return 0
        row = connection.execute(
            "SELECT id, tariff_id, time_left FROM user_tariff_cs WHERE uid = ?", (user[0],)).fetchone()
        if row is not None and int(row[1] or 0) > 0 and int(row[2] or 0) > 0:
            connection.execute("UPDATE user_tariff_cs SET time_left = time_left + ? WHERE id = ?",
                               (REWARD_HOURS, row[0]))
        elif row is not None:
            connection.execute("UPDATE user_tariff_cs SET tariff_id = ?, time_left = ?, notify_count = ? "
                               "WHERE id = ?", (relay[0], REWARD_HOURS, relay[1], row[0]))
        else:
            connection.execute("INSERT INTO user_tariff_cs (uid, tariff_id, balance, time_left, notify_count) "
                               "VALUES (?, ?, 0, ?, ?)", (user[0], relay[0], REWARD_HOURS, relay[1]))
        connection.execute("UPDATE users SET flags = json_set(COALESCE(flags, '{}'), ?, ?) WHERE id = ?",
                           ('$.' + REWARD_FLAG, int(now), user[0]))
        connection.commit()
        return REWARD_HOURS
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def survey_message(language_code, telegram_id, database=None, group="ended") -> dict:
    """The question, a button per reason, the gift, and a trial's offer when it is due; an idle
    trial is asked what got in the way, with no offer."""
    from app.i18n.messages import get_message
    from app.service.payment import plan_end
    from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL
    from db.sqliteAdapter import SQLighter
    answers = {"idle": IDLE_ANSWERS, "old": OLD_ANSWERS}.get(group, PAY_ANSWERS)
    rows = [[{'text': get_message("whyAnswer_" + answer, language_code),
              'callback_data': {'tp': ACTION, 'a': answer}}] for answer in answers]
    reward = get_message("whyReward", language_code).format(days=REWARD_HOURS // 24)
    if group == "idle":
        return {'type': 'text', 'text': get_message("whySurveyIdle", language_code) + "\n\n" + reward,
                'reply_markup': rows, 'disable_web_page_preview': True}
    if group == "old":  # the search button comes after the answer: a tap on it here would turn this into search
        return {'type': 'text', 'text': get_message("whySurveyOld", language_code) + "\n\n" + reward,
                'reply_markup': rows, 'disable_web_page_preview': True}
    db = SQLighter(db_path if database is None else database)
    try:
        price = next((int(t['price']) for t in db.getTariffs() if int(t['level']) == SHOWCASE_TARIFF_LEVEL), 500)
    finally:
        db.close()
    line, offer_row = plan_end.trial_offer(telegram_id, SHOWCASE_TARIFF_LEVEL, price, language_code,
                                           analytics_events.SURVEY_SOURCE, database=database)
    text = get_message("whySurvey", language_code) + "\n\n" + reward
    if offer_row:
        from app.service.payment.storefront import CHANGE_PLAN_CALLBACK
        text += "\n\n" + line
        rows.append(offer_row)
        rows.append([{'text': get_message("tariffs", language_code),
                      'callback_data': {'tp': CHANGE_PLAN_CALLBACK, 's': analytics_events.SURVEY_SOURCE}}])
    return {'type': 'text', 'text': text, 'reply_markup': rows, 'disable_web_page_preview': True}


def _mark(telegram_id, value, database=None, flag=SURVEY_FLAG):
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path if database is None else database)
    try:
        db.set_user_flag(telegram_id, flag, value)
    finally:
        db.close()


def send_surveys(database=None, now=None, send=None) -> int:
    """Ask the chats due while the survey is open; how many got it."""
    if not open_until(now):
        return 0
    if send is None:
        from lib.telegram.general.message_master import outer_sender as send
    sent = 0
    for telegram_id, lang, group in due(database, now):
        try:
            if group == "old" and holdout(telegram_id):
                _mark(telegram_id, "control", database)
                _mark(telegram_id, group, database, GROUP_FLAG)
                analytics_events.track(telegram_id, "survey_control", {"group": group}, database=database)
                continue
            _mark(telegram_id, "unsent", database)  # first: a crash in between never sends it twice
            _mark(telegram_id, group, database, GROUP_FLAG)  # first too: the old ones' cap counts it
            if send(telegram_id, [survey_message(lang or "en", telegram_id, database, group)]):
                _mark(telegram_id, "sent", database)
                analytics_events.track(telegram_id, "survey_sent", {"group": group}, database=database)
                sent += 1
        except Exception as e:
            logger.warn("why survey:", telegram_id, type(e).__name__, e)
    return sent


def survey_watcher():
    while True:
        try:
            send_surveys()
        except Exception as e:
            logger.err("why survey batch:", e)
        time.sleep(CHECK_SECONDS)
