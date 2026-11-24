# -*- coding: utf-8 -*-
"""The welcome trial starts with the chat's first podcast of its own, not at /start.

Before 2026-11-24 every newcomer got 14 days of Relay at /start, before doing anything: none of
309 newcomers in 30 days paid, and of 224 ended trials asked why, none answered and 3 opened the
bot again. Most trials ran out on a chat whose only show was the welcome one (TED Talks Daily, which
/start subscribes everyone to). The owner's call (2026-11-24): the trial starts at the moment of
value, the first subscription to a show of the chat's own.

/start (`paymentSafeModule.giveAward`, mode `new`) gives a newcomer with no show of its own the
"no plan" row and a pending trial: `users.flags` `trial_pending`, the hours it will run (the
welcome period, a friend's link's days on top). A newcomer who already subscribed to a show of its
own (a first command other than /start) gets the plan at once, as before. The first subscription
to any show but the welcome one (`subscription.add_sub_rss`: the podcast page, the welcome screen,
an OPML import, a link) starts it (`on_subscribed`): Relay for those hours, one message that says
so. Claimed once (the flag is taken in one statement; two subscriptions at once start it once).
A plan running then (paid, or a grant) keeps the flag for later; a chat that ever paid drops it.
Never fails the subscription.
Lock: python app/service/plan/test_trial.py
"""
from __future__ import annotations

from typing import Optional

from app.service.payment.plan_end import WELCOME_CHANNEL_ID
from lib.tools.logger import logger

PENDING_FLAG = "trial_pending"


def days_args(hours, language_code) -> dict:
    """The trial's days for its texts' `{days}`: the number, in Russian with its word (14 дней, 21 день)."""
    days = max(1, int(hours) // 24)
    if language_code != 'ru':
        return {'days': days}
    tens, ones = days % 100, days % 10
    word = "дней" if 11 <= tens <= 14 else "день" if ones == 1 else "дня" if 2 <= ones <= 4 else "дней"
    return {'days': "%d %s" % (days, word)}


def _db(database=None):
    from config import db_path
    from db.sqliteAdapter import SQLighter
    return SQLighter(db_path if database is None else database)


def offer(telegram_id, hours, database=None) -> None:
    """The trial waits for the chat's first show of its own."""
    db = _db(database)
    try:
        db.set_user_flag(telegram_id, PENDING_FLAG, int(hours))
    finally:
        db.close()


def pending_hours(telegram_id, database=None) -> Optional[int]:
    db = _db(database)
    try:
        hours = db.get_user_flag(telegram_id, PENDING_FLAG)
    finally:
        db.close()
    return int(hours) if hours else None


def _claim(db, telegram_id) -> Optional[int]:
    """Takes the flag; its hours for the one caller that took it, else None."""
    with db.connection:
        row = db.cursor.execute(
            "SELECT json_extract(COALESCE(flags, '{}'), ?) FROM users WHERE telegramId = ?",
            ('$.' + PENDING_FLAG, str(telegram_id))).fetchone()
        if row is None or not row[0]:
            return None
        taken = db.cursor.execute(
            "UPDATE users SET flags = json_remove(flags, ?) WHERE telegramId = ? "
            "AND json_extract(COALESCE(flags, '{}'), ?) IS NOT NULL",
            ('$.' + PENDING_FLAG, str(telegram_id), '$.' + PENDING_FLAG)).rowcount
    return int(row[0]) if taken else None


def start(telegram_id, channel_id, database=None) -> Optional[int]:
    """Relay for the pending hours when `channel_id` is a show of the chat's own; the hours, or None."""
    if channel_id is None or int(channel_id) == WELCOME_CHANNEL_ID:
        return None
    from db.tariff_rows import ever_paid, running_plan_level
    from config import db_path
    path = db_path if database is None else database
    if pending_hours(telegram_id, path) is None:
        return None
    if running_plan_level(telegram_id, path):
        return None  # a plan runs (paid, a grant): the trial waits for it to end
    db = _db(path)
    try:
        if ever_paid(telegram_id, path):
            _claim(db, telegram_id)  # paid once: no free trial after
            return None
        hours = _claim(db, telegram_id)
        if hours is None:
            return None
        current = db.getUserSubscriptionByTg(telegram_id)
        relay = db.getExtremeTariff('max')
        db.subscribeUserToTariffByTg(telegram_id, relay['id'], current['balance'] if current else 0,
                                     hours, relay['notify_count'])
        return hours
    finally:
        db.close()


def notice(telegram_id, hours, language_code) -> dict:
    from app.i18n.messages import get_message
    from app.service.payment.paymentSafeModule import (decode_tariff, get_tariff_info_message,
                                                       get_tariff_params_by_tg)
    text = get_message("trialStarted", language_code).format(**days_args(hours, language_code))
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(telegram_id)
    text += "\n\n" + get_tariff_info_message(decode_tariff(tariff['level'], language_code), balance,
                                             tariff['price'], time_left, notify_left, language_code)
    return {'type': 'text', 'text': text}


def on_subscribed(telegram_id, channel_id, database=None, send=None) -> Optional[int]:
    """After a subscription: the pending trial starts and the chat hears it. Never raises."""
    try:
        hours = start(telegram_id, channel_id, database)
        if hours is None:
            return None
        from app.service import analytics_events
        analytics_events.track(telegram_id, "trial_started", {"hours": hours, "trigger": "own_show"},
                               database=database)
        db = _db(database)
        try:  # not get_user_by_tg: it makes a row for any number
            row = db.cursor.execute("SELECT lang FROM users WHERE telegramId = ?", (str(telegram_id),)).fetchone()
        finally:
            db.close()
        language_code = (row[0] if row else None) or 'en'
        if send is None:
            from lib.telegram.general.message_master import outer_sender as send
        send(telegram_id, [notice(telegram_id, hours, language_code)])
        return hours
    except Exception as e:
        logger.warn("trial start:", telegram_id, type(e).__name__, e)
        return None
