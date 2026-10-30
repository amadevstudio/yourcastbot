# -*- coding: utf-8 -*-
"""Win back a user whose Relay stopped: a message a week after, another a month after.

Runs from the hourly balance_watcher, after D-3. A schedule starts when a
Relay plan stops (balance_watcher's plan-off notice), so the old expiries
are never mailed. Each message is claimed before it is sent (at most once);
a flood wait gives it back for the next hour. The user is re-read when the
message goes: back on a plan or gone ends the schedule, nothing is sent.

The first month at winback_offer_discount % off is offered once per user
(offers.offer_open); a user who spent it gets the plain message. The end of a
Relay trial already offered it (plan_end.trial_offer): these messages repeat it.
Each message sent is a `winback_sent` event, its buttons carry the source `wb`.

Lock: python app/jobs/test_winback.py
"""
from app.core.sender.outbox import OutboxRetryableError
from app.i18n.messages import get_message
from app.service import analytics_events
from app.service.payment.offers import WINBACK_OFFER, offer_open
from app.service.payment.paymentSafeModule import is_subscription_active
from app.service.payment.storefront import (
    RELAY_INVOICE_CALLBACK, SHOWCASE_TARIFF_LEVEL, relay_nudge_markup)
from config import db_path, winback_after_days, winback_offer_discount
from db import winback
from db.sqliteAdapter import SQLighter
from lib.tools.logger import logger

AFTER_SECONDS = tuple(int(days) * 24 * 60 * 60 for days in winback_after_days)


def start_winback(stopped_users, now=None, database=None):
    """The plans balance_watcher just switched off: Relay ones start a schedule.

    Called with the tick's plan-off list only, so the backlog of plans that
    stopped before this job existed is never mailed.
    """
    for user in stopped_users:
        if user["tlevel"] == SHOWCASE_TARIFF_LEVEL and user["telegramId"]:
            winback.start(user["telegramId"], now=now, database=database)


def winback_message(stage, language_code, with_offer):
    """Stage 0 is the first message, 1 the last one."""
    source = analytics_events.WINBACK_SOURCE
    if with_offer:
        text = get_message("winbackOffer" if stage == 0 else "winbackOfferLast",
                           language_code).format(discount=winback_offer_discount)
        cta = {"text": get_message("winbackOfferButton", language_code).format(
                   discount=winback_offer_discount),
               "callback_data": dict(RELAY_INVOICE_CALLBACK, o=WINBACK_OFFER, s=source)}
        # the offer's invoice first, change-plan next to it, as every nudge
        rows = [[cta]] + relay_nudge_markup(language_code, source=source)[1:]
    else:
        text = get_message("winbackPlain", language_code)
        rows = relay_nudge_markup(language_code, invoice=True, source=source)
    return {"type": "text", "text": text, "reply_markup": rows}


def _user_state(telegram_id, database):
    """(language, still away) read now; still away is False for a gone user."""
    db = SQLighter(database)
    try:
        if db.is_user_deleted_tg(telegram_id) or not db.user_exists_tg(telegram_id):
            return None, False
        user = db.get_user_by_tg(telegram_id)
        away = not is_subscription_active(db.getUserSubscriptionByTg(telegram_id))
        return (user["lang"] or "en"), away
    finally:
        db.close()


def _send(chat_id, messages):
    from lib.telegram.general.message_master import outer_sender
    return outer_sender(chat_id, messages, on_flood="raise")


def send_winback_messages(now=None, database=None):
    """Send what is due. Returns how many messages went out."""
    db_file = db_path if database is None else database
    sent = 0
    for telegram_id, stage in winback.due(AFTER_SECONDS, now=now, database=db_file):
        if not winback.claim(telegram_id, stage, database=db_file):
            continue  # another run took it
        language, away = _user_state(telegram_id, db_file)
        if not away:
            winback.forget(telegram_id, database=db_file)
            continue
        with_offer = offer_open(telegram_id, WINBACK_OFFER, database=db_file)
        message = winback_message(stage, language, with_offer)
        try:
            _send(telegram_id, [message])
        except OutboxRetryableError as e:
            winback.give_back(telegram_id, stage, database=db_file)
            logger.warn("winback/flood:", e)
            break  # Telegram asks to wait: the rest go next hour
        analytics_events.winback_sent(telegram_id, stage, with_offer, database=db_file)
        sent += 1
    return sent
