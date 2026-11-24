# -*- coding: utf-8 -*-
"""One nudge to a newcomer who has no podcast of their own yet.

Newcomers of 21-30.10.2026 who subscribed to a show of their own (not only
the welcome show /start gives) blocked the bot 13% of the time and 96% of
those who stayed took episodes; without one, 33% blocked, mostly within a
day and before anything reached them, and 20% of those who stayed took
episodes. So between 1 and 6 hours after /start, a chat with only the
welcome show gets one message: send a name or a link, or an OPML export,
or tap a popular podcast (the welcome screen's buttons: a tap subscribes,
state independent).

It was an A/B test (even ids got it, odd ones were the control): of the
newcomers whose first week was over on 2026-11-24, 5 of 66 meant to get it
subscribed to a show of their own against 0 of 58 in the control, and 26%
blocked the bot against 38%. The owner's call (2026-11-24): every newcomer
gets it now. The chats marked `control` stay marked (`users.flags`
`own_show_nudge`: sent, unsent, control), so the admin page "Product" still
reads the test. With the trial waiting for a show of the chat's own
(app/service/plan/trial.py) the nudge says so. Once per chat, never to a
blocked one, never fails the jobs role.
Lock: python app/jobs/test_own_show_nudge.py
"""
import time

from app.service import analytics_events
from app.service.payment.plan_end import WELCOME_CHANNEL_ID
from config import db_path
from db.connection import connect_sqlite
from lib.tools.logger import logger

NUDGE_FLAG = "own_show_nudge"
AFTER_HOURS = 1
WINDOW_HOURS = 6
CHECK_SECONDS = 600


def due(database=None, now=None) -> list:
    """[(telegram id, lang)]: joined between WINDOW_HOURS and AFTER_HOURS ago (users.created_at
    is UTC), here still, not marked, no subscription but the welcome show."""
    now = time.time() if now is None else now
    connection = connect_sqlite(db_path if database is None else database)
    try:
        return [(row[0], row[1]) for row in connection.execute(
            "SELECT u.telegramId, u.lang FROM users u "
            "WHERE typeof(u.telegramId) = 'integer' AND u.telegramId > 0 AND u.deleted_at IS NULL "
            "AND u.created_at <= datetime(?, 'unixepoch') AND u.created_at >= datetime(?, 'unixepoch') "
            "AND json_extract(COALESCE(u.flags, '{}'), '$.%s') IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM user_channel_cs s WHERE s.user_telegram_id = u.telegramId "
            "AND s.channel_id != ?)" % NUDGE_FLAG,
            (now - AFTER_HOURS * 3600, now - WINDOW_HOURS * 3600, WELCOME_CHANNEL_ID))]
    finally:
        connection.close()


def nudge_message(language_code, telegram_id, database=None) -> dict:
    """The welcome screen's buttons (popular podcasts, search, menu) under the nudge's text."""
    from app.controller.builders import onboarding
    from app.i18n.messages import get_message
    top_list, mark, ticked = onboarding.picker(language_code, telegram_id, database=database)
    screen = onboarding.welcome_message(language_code, top_list, ticked, mark)[0]
    screen['text'] = get_message("ownShowNudge", language_code)
    from app.service.plan import trial
    try:
        hours = trial.pending_hours(telegram_id, database)
    except Exception as e:  # the nudge goes without the line
        logger.warn("own show nudge, trial:", telegram_id, type(e).__name__, e)
        hours = None
    if hours:
        screen['text'] += "\n\n" + get_message("ownShowNudgeTrial", language_code).format(**trial.days_args(hours, language_code))
    return screen


def _mark(telegram_id, value, database=None):
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path if database is None else database)
    try:
        db.set_user_flag(telegram_id, NUDGE_FLAG, value)
    finally:
        db.close()


def send_nudges(database=None, now=None, send=None) -> int:
    """Nudge the chats due; how many got it."""
    if send is None:
        from lib.telegram.general.message_master import outer_sender as send
    sent = 0
    for telegram_id, lang in due(database, now):
        lang = lang or "en"
        try:
            _mark(telegram_id, "unsent", database)  # first: a crash in between never sends it twice
            if send(telegram_id, [nudge_message(lang, telegram_id, database)]):
                _mark(telegram_id, "sent", database)
                analytics_events.track(telegram_id, "own_show_nudge", {"group": "sent"}, database=database)
                sent += 1
        except Exception as e:
            logger.warn("own show nudge:", telegram_id, type(e).__name__, e)
    return sent


def nudge_watcher():
    while True:
        try:
            send_nudges()
        except Exception as e:
            logger.err("own show nudge batch:", e)
        time.sleep(CHECK_SECONDS)
