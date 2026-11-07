# -*- coding: utf-8 -*-
"""Free listeners get the no-plan profile's episodes by click (`free_rec_per_week`, 10) in any 7 days.

Counted from the usage ledger (db/usage.py, kind 'rec'): distinct episodes
delivered in the last 7 days, plus clicks still waiting in the outbox (one
in flight per user: fast taps must not slip past the limit). The same
episode again is free. A paid plan has no limit. A plan nobody paid for
(the welcome trial, referral days; `tariff_rows.paid_for_days`) gets the
trial profile's (`trial_rec_per_day`) by click in any 24 hours, counted the same way:
one trial took ~1000 episodes of one show in 4 days, holding one of the 4 rec
workers the whole time (2026-10). Automatic deliveries and the episode list
are not limited.

At the limit the click is not queued: the user gets every plan with its
Stars price, Relay first, and the page of plans (other ways to pay) next to
them (storefront rules: no SKU hidden). At the trial's limit: Relay's invoice
(paying lifts the limit at once) and change-plan. Each stop is an Amplitude
event (`free_limit_hit`) and the buttons carry `s: lim`, so the limit's
funnel (stop, invoice, payment) can be read.
Lock: python app/service/record/test_free_limit.py
"""
import math
import time
from typing import NamedTuple, Optional

from app.service.plan import entitlements, features
from config import db_path
from db import usage
from db.tariff_rows import running_plan_level


def has_running_plan(chat_id, database=None) -> bool:
    """A plan with time left, whatever its notify_count: clicks are not notifies."""
    return running_plan_level(chat_id, database) > 0


def window_check(chat_id, link, open_links, limit, window_seconds, now=None, database=None):
    """(allowed, seconds until the next episode or None): `limit` distinct episodes by click in
    any `window_seconds`, waiting clicks (open_links) included; the same episode again is free."""
    now = time.time() if now is None else now
    since = now - window_seconds
    counted = usage.episodes_since(chat_id, 'rec', since, database=database)
    counted |= {usage.episode_ref(other) for other in open_links}
    if usage.episode_ref(link) in counted or len(counted) < limit:
        return True, None
    leaves = usage.first_to_leave(chat_id, 'rec', since, database=database)
    wait = (leaves + window_seconds - now) if leaves is not None else window_seconds
    return False, max(wait, 60)


def check(chat_id, link, open_links=(), plan=None, now=None, database=None, limit=None):
    """(allowed, seconds until the next free episode or None) of a chat without a plan.

    open_links: links of this chat's clicks not delivered yet.
    plan: has_running_plan(chat_id), read here when not given.
    """
    free = features.profile(features.NONE)
    limit = free['clicks'] if limit is None else limit
    if plan is None:
        plan = has_running_plan(chat_id, database)
    if plan or limit is None:
        return True, None
    return window_check(chat_id, link, open_links, limit, free['clicks_hours'] * 3600, now, database)


def trial_check(chat_id, link, open_links=(), now=None, database=None, limit=None):
    """(allowed, seconds until the next episode or None) for a plan nobody paid for: the trial
    profile's episodes by click in any of its windows, waiting clicks included."""
    trial = features.profile(features.TRIAL)
    limit = trial['clicks'] if limit is None else limit
    if limit is None:
        return True, None
    return window_check(chat_id, link, open_links, limit, trial['clicks_hours'] * 3600, now, database)


class Hit(NamedTuple):
    """A click the limit stops: 'week' (no plan) or 'trial' (a plan nobody paid for)."""
    limit: str
    wait: float
    level: int
    count: Optional[int] = None  # the episodes the limit allows; None: the profile's


def limit_hit(chat_id, link, open_links, now=None, database=None) -> Optional[Hit]:
    """None when this click may be queued: the chat's profile (entitlements) says how many
    episodes in what window: no plan, the free week's; a plan nobody paid for, the trial's day;
    a paid plan, none; a grant (db/plan_grants.py), its profile's."""
    rights = entitlements.of(chat_id, database)
    count = rights.get('clicks')
    if count is None:
        return None
    allowed, wait = window_check(chat_id, link, open_links, count, rights.get('clicks_hours') * 3600, now, database)
    if allowed:
        return None
    return Hit('grant' if rights.grant else 'trial' if rights.running else 'week', wait, rights.level, count)


def hit_message(hit: Hit, language_code) -> dict:
    if hit.limit == 'week':
        return limit_message(language_code, hit.wait, hit.count)
    return trial_limit_message(language_code, hit.wait, hit.level, hit.count, grant=hit.limit == 'grant')


def click_limit(chat_id, link, open_links, language_code, now=None, database=None):
    """None when this click may be queued, else the message to send instead."""
    hit = limit_hit(chat_id, link, open_links, now=now, database=database)
    return None if hit is None else hit_message(hit, language_code)


def wait_text(seconds, language_code) -> str:
    from app.i18n.messages import get_message
    hours = math.ceil(seconds / 3600)
    if hours < 48:
        return get_message("freeEpisodesNextHours", language_code).format(hours=hours)
    return get_message("freeEpisodesNextDays", language_code).format(days=math.ceil(hours / 24))


def plans_offer(language_code, source=None) -> tuple[str, list]:
    """(text, keyboard rows): every plan with its Stars price, Relay first, then the
    page of plans for the other ways to pay. Shared by the limits that sell a plan.
    source: the message's key in analytics_events.SOURCES, on every button (`s`)."""
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
    tag = {'s': source} if source else {}

    text = ""
    rows = []
    for tariff in tariffs_for_storefront(tariffs):
        texts = get_tariff_description_and_button_text(tariff, {'id': 0}, language_code)
        text += texts['text'] + "\n\n"
        rows.append([{
            'text': "%s – %d ⭐" % (texts['button_text'], stars_for_balance(tariff['price'], rate_x1000)),
            'callback_data': {'tp': 'bs_stars_pay', 'v': tariff['id'], **tag},
        }])
    rows.append([{'text': get_message("tariffs", language_code),
                  'callback_data': {'tp': CHANGE_PLAN_CALLBACK, **tag}}])
    return text, rows


def limit_message(language_code, wait_seconds, limit=None):
    """The limit as a message: every plan, Stars price on its button, Relay first."""
    from app.i18n.messages import get_message
    from app.service.analytics_events import LIMIT_SOURCE

    limit = features.profile(features.NONE)['clicks'] if limit is None else limit
    plans_text, rows = plans_offer(language_code, source=LIMIT_SOURCE)
    text = "<b>" + get_message("freeEpisodesUsed", language_code).format(limit=limit) + "</b>\n"
    text += wait_text(wait_seconds, language_code) + " "
    text += get_message("freeEpisodesAnyPlan", language_code) + "\n\n" + plans_text
    return {'type': 'text', 'text': text.strip(), 'reply_markup': rows,
            'disable_web_page_preview': True}


def trial_limit_message(language_code, wait_seconds, level, limit=None, grant=False):
    """The trial's day used up: Relay's invoice when the trial is Relay (paying lifts the
    limit at once), else the Stars page (an invoice would only top up the running plan),
    and change-plan next to it. `grant`: a grant's day (db/plan_grants.py), every plan's
    invoice: a plan bought replaces the grant, and Bronze is the cheapest."""
    from app.i18n.messages import get_message
    from app.service.analytics_events import LIMIT_SOURCE
    from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL, relay_nudge_markup

    limit = features.profile(features.TRIAL)['clicks'] if limit is None else limit
    used = "grantEpisodesUsed" if grant else "trialEpisodesUsed"
    text = "<b>" + get_message(used, language_code).format(limit=limit) + "</b>\n" \
        + get_message("trialEpisodesNext", language_code).format(hours=math.ceil(wait_seconds / 3600))
    if grant:
        rows = plans_offer(language_code, source=LIMIT_SOURCE)[1]
    else:
        rows = relay_nudge_markup(language_code, invoice=int(level) == SHOWCASE_TARIFF_LEVEL, source=LIMIT_SOURCE)
    return {'type': 'text', 'text': text, 'reply_markup': rows, 'disable_web_page_preview': True}
