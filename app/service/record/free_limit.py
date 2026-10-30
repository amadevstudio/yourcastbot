# -*- coding: utf-8 -*-
"""Free listeners get `free_rec_per_week` episodes by click in any 7 days.

Counted from the usage ledger (db/usage.py, kind 'rec'): distinct episodes
delivered in the last 7 days, plus clicks still waiting in the outbox (one
in flight per user: fast taps must not slip past the limit). The same
episode again is free. A paid plan has no limit. A plan nobody paid for
(the welcome trial, referral days; `tariff_rows.paid_for_days`) gets
`trial_rec_per_day` episodes by click in any 24 hours, counted the same way:
one trial took ~1000 episodes of one show in 4 days, holding one of the 4 rec
workers the whole time (2026-10). Automatic deliveries and the episode list
are not limited.

At the limit the click is not queued: the user gets every plan with its
Stars price, Relay first, and the page of plans (other ways to pay) next to
them (storefront rules: no SKU hidden). At the trial's limit: Relay's invoice
(paying lifts the limit at once) and change-plan.
Lock: python app/service/record/test_free_limit.py
"""
import math
import time

from config import db_path, free_rec_per_week, trial_rec_per_day
from db import usage
from db.tariff_rows import paid_for_days, running_plan_level

DAY_SECONDS = 86400


def has_running_plan(chat_id, database=None) -> bool:
    """A plan with time left, whatever its notify_count: clicks are not notifies."""
    return running_plan_level(chat_id, database) > 0


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
    leaves = usage.first_to_leave(chat_id, 'rec', since, database=database)
    wait = (leaves + usage.WEEK_SECONDS - now) if leaves is not None else usage.WEEK_SECONDS
    return False, max(wait, 60)


def trial_check(chat_id, link, open_links=(), now=None, database=None, limit=None):
    """(allowed, seconds until the next episode or None) for a plan nobody paid for:
    `trial_rec_per_day` distinct episodes by click in any 24 hours, waiting clicks included."""
    limit = trial_rec_per_day if limit is None else limit
    now = time.time() if now is None else now
    since = now - DAY_SECONDS
    counted = usage.episodes_since(chat_id, 'rec', since, database=database)
    counted |= {usage.episode_ref(other) for other in open_links}
    if usage.episode_ref(link) in counted or len(counted) < limit:
        return True, None
    leaves = usage.first_to_leave(chat_id, 'rec', since, database=database)
    wait = (leaves + DAY_SECONDS - now) if leaves is not None else DAY_SECONDS
    return False, max(wait, 60)


def click_limit(chat_id, link, open_links, language_code, now=None, database=None):
    """None when this click may be queued, else the message to send instead:
    no plan, the free week's; a plan nobody paid for, the trial's day; a paid plan, none."""
    level = running_plan_level(chat_id, database)
    if level <= 0:
        allowed, wait = check(chat_id, link, open_links, plan=False, now=now, database=database)
        return None if allowed else limit_message(language_code, wait)
    if paid_for_days(chat_id, database):
        return None
    allowed, wait = trial_check(chat_id, link, open_links, now=now, database=database)
    return None if allowed else trial_limit_message(language_code, wait, level)


def wait_text(seconds, language_code) -> str:
    from app.i18n.messages import get_message
    hours = math.ceil(seconds / 3600)
    if hours < 48:
        return get_message("freeEpisodesNextHours", language_code).format(hours=hours)
    return get_message("freeEpisodesNextDays", language_code).format(days=math.ceil(hours / 24))


def plans_offer(language_code) -> tuple[str, list]:
    """(text, keyboard rows): every plan with its Stars price, Relay first, then the
    page of plans for the other ways to pay. Shared by the limits that sell a plan."""
    from app.i18n.messages import get_message
    from app.service.payment.paymentModule import get_tariff_description_and_button_text
    from app.service.payment.starsPaymentModule import get_stars_withdraw_rate_x1000, stars_for_balance
    from app.service.payment.storefront import CHANGE_PLAN_CALLBACK, tariffs_for_storefront
    from db.sqliteAdapter import SQLighter

    db_users = SQLighter(db_path)
    try:
        tariffs = db_users.getTariffs()
    finally:
        db_users.close()
    rate_x1000 = get_stars_withdraw_rate_x1000()

    text = ""
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
    return text, rows


def limit_message(language_code, wait_seconds, limit=None):
    """The limit as a message: every plan, Stars price on its button, Relay first."""
    from app.i18n.messages import get_message

    limit = free_rec_per_week if limit is None else limit
    plans_text, rows = plans_offer(language_code)
    text = "<b>" + get_message("freeEpisodesUsed", language_code).format(limit=limit) + "</b>\n"
    text += wait_text(wait_seconds, language_code) + " "
    text += get_message("freeEpisodesAnyPlan", language_code) + "\n\n" + plans_text
    return {'type': 'text', 'text': text.strip(), 'reply_markup': rows,
            'disable_web_page_preview': True}


def trial_limit_message(language_code, wait_seconds, level, limit=None):
    """The trial's day used up: Relay's invoice when the trial is Relay (paying lifts the
    limit at once), else the Stars page (an invoice would only top up the running plan),
    and change-plan next to it."""
    from app.i18n.messages import get_message
    from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL, relay_nudge_markup

    limit = trial_rec_per_day if limit is None else limit
    text = "<b>" + get_message("trialEpisodesUsed", language_code).format(limit=limit) + "</b>\n" \
        + get_message("trialEpisodesNext", language_code).format(hours=math.ceil(wait_seconds / 3600))
    return {'type': 'text', 'text': text,
            'reply_markup': relay_nudge_markup(language_code, invoice=int(level) == SHOWCASE_TARIFF_LEVEL),
            'disable_web_page_preview': True}
