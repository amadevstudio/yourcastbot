import datetime
import sqlite3
import time

from app.i18n.messages import get_message
from app.jobs.relay_remind import (
    clear_relay_d3_sent, relay_nudge_markup, send_relay_d3_reminders)
from app.jobs.tariff_tick import run_tariff_tick
from app.service import analytics_events
from app.service.payment import plan_end, stars_subscription
from app.service.payment.paymentModule import get_tariff_description_and_button_text
from app.service.payment.paymentSafeModule import decode_tariff, get_tariff_info_message
from app.service.payment.referral import invite_row
from app.jobs.winback import send_winback_messages, start_winback
from app.service.payment.storefront import plan_off_text
from config import db_path, tariff_period
from db import runtime_kv
from db.connection import connect_sqlite
from lib.telegram.general.message_master import outer_sender
from lib.tools.logger import logger

# bot_runtime_kv: a plan-off notice Telegram did not take (no network, a flood wait), when.
# The tick has ended the plan; the notice and its offer must not end with a lost send.
PLAN_OFF_RETRY = "plan_off_retry_"
PLAN_OFF_RETRY_HOURS = 24


def balance_watcher(update_time):
    while True:
        if update_time == 'per_hour':
            delta = datetime.timedelta(hours=1)
            now = datetime.datetime.now()
            next_hour = (now + delta).replace(microsecond=0, second=0, minute=0)
            wait_seconds = (next_hour - now).seconds
        else:
            wait_seconds = 3600
        time.sleep(wait_seconds)
        time.sleep(1)  # bcs of repeats in 1 second

        prolonged_users, not_prolonged_users, tariffs = run_tariff_tick()
        # # INFO: Debug string
        # not_prolonged_users = [{
        # 	'balance': 0, 'telegramId': creatorId, 'lang': 'ru',
        # 	'tid': 3, 'tprice': 10, 'tlevel': 3, 'tnc': 100}]

        tariffs_by_id = {}
        for tariff in tariffs:
            tariffs_by_id[tariff['id']] = tariff

        lang = 'no_lang'
        for pu in prolonged_users:
            if pu['telegramId']:
                clear_relay_d3_sent(pu['telegramId'])
                if lang != pu['lang']:
                    lang = pu['lang']

                message_base = get_message("tariff_prolonged_by_daemon", lang) + "\n\n"

                balance = int(pu['balance']) - int(pu['tprice'])

                tariff_str = decode_tariff(pu['tlevel'], lang)
                message = message_base + get_tariff_info_message(
                    tariff_str, balance, pu['tprice'], tariff_period, pu['tnc'], lang)
                outer_sender(pu['telegramId'], [{'type': 'text', 'text': message}])

        try:
            retry_plan_off_notices(tariffs_by_id)
        except Exception as e:
            logger.err("plan_off retry batch:", e)

        try:
            start_winback(not_prolonged_users)
        except Exception as e:
            logger.warn("winback/start:", e)

        for npu in not_prolonged_users:
            try:
                message, offered = plan_off_message(npu, tariffs_by_id.get(npu['tid']))
            except Exception as e:  # one user's notice never holds back the others'
                logger.err("plan_off notice:", npu['telegramId'], e)
                message, offered = None, False
            # the trial-to-paid funnel: a plan nobody paid for that ended is a trial that did not convert
            analytics_events.plan_off(npu['telegramId'], npu['tlevel'], offer=offered)
            if message is None:
                continue
            try:
                if not outer_sender(npu['telegramId'], [message]):
                    note_plan_off_unsent(npu['telegramId'])
            except Exception as e:
                logger.err(e)

        try:
            send_relay_d3_reminders()
        except Exception as e:
            logger.err("relay_d3_batch:", e)

        try:
            send_winback_messages()
        except Exception as e:
            logger.err("winback_batch:", e)


def plan_off_message(npu, tariff_row, database=None):
    """(the message, offered) for a plan the tick did not renew: the plan's own text,
    the user's podcasts that stop coming as files, the plan, and for a Relay trial
    the first month at the win-back discount, its invoice above the usual rows."""
    lang = npu['lang']
    # The plan that stopped is the user's own (Bronze, Silver, Relay)
    message = plan_off_text(npu['tlevel'], lang) + "\n\n"
    loss, _shows = plan_end.loss_text(npu['telegramId'], lang, database=database)
    if loss:
        message += loss + "\n\n"
    # a Relay trial: the discount now, not with the win-back message a week later
    offer, offer_row = plan_end.trial_offer(
        npu['telegramId'], npu['tlevel'], npu['tprice'], lang, analytics_events.PLAN_OFF_SOURCE,
        database=database)

    tariff_str = decode_tariff(npu['tlevel'], lang)
    message += get_tariff_info_message(tariff_str, int(npu['balance']), npu['tprice'], 0, 0, lang)
    if tariff_row:
        message += "\n\n" + get_message("your_tariff_description", lang) + ":\n" \
                   + get_tariff_description_and_button_text(
                       tariff_row, {'id': npu['tid']}, lang,
                       show_tariff_level_text=False)['text']
    if offer:
        message += "\n\n" + offer
    markup = relay_nudge_markup(lang, extra_row=invite_row(npu['telegramId'], lang),
                                source=analytics_events.PLAN_OFF_SOURCE)
    markup.append(stars_subscription.offer_row(lang))  # below Stars, change-plan and the invite
    if offer_row:
        markup.insert(0, offer_row)  # the discounted month first, the Stars page of every plan next
    return {'type': 'text', 'text': message, 'reply_markup': markup}, bool(offer_row)


def note_plan_off_unsent(telegram_id, database=None, now=None):
    """outer_sender answered []: the notice goes again next hour (retry_plan_off_notices)."""
    logger.warn("plan_off notice not sent, again next hour:", telegram_id)
    runtime_kv.set_kv(PLAN_OFF_RETRY + str(telegram_id), int(time.time() if now is None else now),
                      database=database)


def _plan_still_off(telegram_id, database=None):
    """The user's row as the tick's not-prolonged list has it, while the plan is still off:
    None once a payment or another plan runs, or the user blocked the bot (deleted)."""
    connection = connect_sqlite(db_path if database is None else database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT utc.balance, u.telegramId, u.lang, t.id AS tid, t.price AS tprice, t.level AS tlevel, "
            "t.notify_count AS tnc FROM user_tariff_cs utc "
            "INNER JOIN tariffs t ON t.id = utc.tariff_id INNER JOIN users u ON u.id = utc.uid "
            "WHERE u.telegramId = ? AND utc.time_left = 0 AND utc.balance < t.price "
            "AND u.deleted_at IS NULL", (int(telegram_id),)).fetchone()
    finally:
        connection.close()
    return dict(row) if row is not None else None


def retry_plan_off_notices(tariffs_by_id, database=None, now=None, send=None):
    """Plan-off notices Telegram did not take, again each hour for PLAN_OFF_RETRY_HOURS
    while the plan is still off. Built again when sent: the offer and the shows as they are now."""
    now = time.time() if now is None else now
    send = outer_sender if send is None else send
    for key, noted in runtime_kv.items_with_prefix(PLAN_OFF_RETRY, database=database):
        telegram_id = key[len(PLAN_OFF_RETRY):]
        try:
            npu = None
            if now - float(noted) <= PLAN_OFF_RETRY_HOURS * 3600:
                npu = _plan_still_off(telegram_id, database)
            if npu is not None:
                message, _offered = plan_off_message(npu, tariffs_by_id.get(npu['tid']), database=database)
                if not send(npu['telegramId'], [message]):
                    continue
                logger.log("plan_off notice sent on retry:", telegram_id)
            runtime_kv.delete_kv(key, database=database)
        except Exception as e:
            logger.err("plan_off retry:", telegram_id, e)
