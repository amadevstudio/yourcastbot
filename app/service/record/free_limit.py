# -*- coding: utf-8 -*-
"""Free listeners get `free_rec_per_week` episodes by click in any 7 days.

Counted from the usage ledger (db/usage.py, kind 'rec'): distinct episodes
delivered in the last 7 days, plus clicks still waiting in the outbox (one
in flight per user: fast taps must not slip past the limit). The same
episode again is free. Any running plan (the welcome trial too) has no
limit. Automatic deliveries and the episode list are not limited.

At the limit the click is not queued: the user gets every plan with its
Stars price, Relay first, and the page of plans (other ways to pay) next to
them (storefront rules: no SKU hidden).
"""
import math
import time

from config import db_path, free_rec_per_week
from db import usage
from db.connection import connect_sqlite


def has_running_plan(chat_id, database=None) -> bool:
    """A plan with time left, whatever its notify_count: clicks are not notifies."""
    c = connect_sqlite(db_path if database is None else database)
    try:
        return c.execute(
            "SELECT 1 FROM user_tariff_cs utc JOIN users u ON u.id = utc.uid "
            "WHERE u.telegramId = ? AND utc.tariff_id > 0 AND utc.time_left > 0",
            (int(chat_id),)).fetchone() is not None
    finally:
        c.close()


def check(chat_id, link, open_links=(), plan=None, now=None, database=None, limit=None):
    """(allowed, seconds until the next free episode or None).

    open_links: links of this chat's clicks not delivered yet.
    plan: has_running_plan(chat_id), read here when not given.
    """
    limit = free_rec_per_week if limit is None else limit
    if plan is None:
        plan = has_running_plan(chat_id, database)
    if plan:
        return True, None
    now = time.time() if now is None else now
    since = now - usage.WEEK_SECONDS
    counted = usage.episodes_since(chat_id, 'rec', since, database=database)
    counted |= {usage.episode_ref(other) for other in open_links}
    if usage.episode_ref(link) in counted or len(counted) < limit:
        return True, None
    oldest = usage.oldest_since(chat_id, 'rec', since, database=database)
    wait = (oldest + usage.WEEK_SECONDS - now) if oldest is not None else usage.WEEK_SECONDS
    return False, max(wait, 60)


def wait_text(seconds, language_code) -> str:
    from app.i18n.messages import get_message
    hours = math.ceil(seconds / 3600)
    if hours < 48:
        return get_message("freeEpisodesNextHours", language_code).format(hours=hours)
    return get_message("freeEpisodesNextDays", language_code).format(days=math.ceil(hours / 24))


def limit_message(language_code, wait_seconds, limit=None):
    """The limit as a message: every plan, Stars price on its button, Relay first."""
    from app.i18n.messages import get_message
    from app.service.payment.paymentModule import get_tariff_description_and_button_text
    from app.service.payment.starsPaymentModule import get_stars_withdraw_rate_x1000, stars_for_balance
    from app.service.payment.storefront import CHANGE_PLAN_CALLBACK, tariffs_for_storefront
    from db.sqliteAdapter import SQLighter

    limit = free_rec_per_week if limit is None else limit
    db_users = SQLighter(db_path)
    try:
        tariffs = db_users.getTariffs()
    finally:
        db_users.close()
    rate_x1000 = get_stars_withdraw_rate_x1000()

    text = "<b>" + get_message("freeEpisodesUsed", language_code).format(limit=limit) + "</b>\n"
    text += wait_text(wait_seconds, language_code) + " "
    text += get_message("freeEpisodesAnyPlan", language_code) + "\n\n"
    rows = []
    for tariff in tariffs_for_storefront(tariffs):
        texts = get_tariff_description_and_button_text(tariff, {'id': 0}, language_code)
        text += texts['text'] + "\n\n"
        rows.append([{
            'text': "%s – %d ⭐" % (texts['button_text'], stars_for_balance(tariff['price'], rate_x1000)),
            'callback_data': {'tp': 'bs_stars_pay', 'v': tariff['id']},
        }])
    rows.append([{'text': get_message("tariffs", language_code),
                  'callback_data': {'tp': CHANGE_PLAN_CALLBACK}}])
    return {'type': 'text', 'text': text.strip(), 'reply_markup': rows,
            'disable_web_page_preview': True}
