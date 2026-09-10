# -*- coding: utf-8 -*-
"""Once-per-period Relay reminder when time_left first enters 72 hours.

Runs from the existing hourly balance_watcher. Does not touch payment apply.
"""
from app.i18n.messages import get_message
from app.service.payment.storefront import CHANGE_PLAN_CALLBACK
from config import db_path
from db import runtime_kv
from db.sqliteAdapter import SQLighter
from lib.tools.logger import logger

RELAY_D3_HOURS = 72


def d3_kv_key(telegram_id) -> str:
    return "relay_d3_sent_" + str(telegram_id)


def days_left_label(time_left_hours) -> int:
    hours = int(time_left_hours or 0)
    if hours <= 0:
        return 0
    return max(1, hours // 24)


def should_send_d3(time_left_hours, already_sent) -> bool:
    hours = int(time_left_hours or 0)
    if hours <= 0 or hours > RELAY_D3_HOURS:
        return False
    return not bool(already_sent)


def d3_already_sent(telegram_id, database=None) -> bool:
    value = runtime_kv.get_kv(d3_kv_key(telegram_id), database=database)
    return value is not None and value != ""


def mark_d3_sent(telegram_id, database=None):
    runtime_kv.set_kv(d3_kv_key(telegram_id), "1", database=database)


def clear_relay_d3_sent(telegram_id, database=None):
    if telegram_id is None:
        return
    runtime_kv.delete_kv(d3_kv_key(telegram_id), database=database)


def relay_nudge_markup(language_code, extra_row=None):
    """Stars first, then change-plan. Do not trap the user on one SKU."""
    rows = [[{
        "text": get_message("relayEnableButton", language_code),
        "callback_data": {"tp": "bs_stars"},
    }], [{
        "text": get_message("tariffs", language_code),
        "callback_data": {"tp": CHANGE_PLAN_CALLBACK},
    }]]
    if extra_row:
        rows.append(extra_row)
    return rows


def _send(chat_id, messages):
    from lib.telegram.general.message_master import outer_sender
    return outer_sender(chat_id, messages)


def send_relay_d3_reminders(database=None):
    db_file = db_path if database is None else database
    db = SQLighter(db_file)
    try:
        users = db.get_users_nearing_expiry(RELAY_D3_HOURS)
    finally:
        db.close()

    sent = 0
    for user in users:
        telegram_id = user["telegramId"]
        if not telegram_id:
            continue
        if not should_send_d3(
                user["time_left"], d3_already_sent(telegram_id, database=db_file)):
            continue
        lang = user["lang"] if user["lang"] else "en"
        days = days_left_label(user["time_left"])
        text = get_message("relay_trial_ending", lang) % days
        try:
            _send(telegram_id, [{
                "type": "text",
                "text": text,
                "reply_markup": relay_nudge_markup(lang),
            }])
        except Exception as e:
            logger.err("relay_d3:", telegram_id, e)
            continue
        mark_d3_sent(telegram_id, database=db_file)
        sent += 1
    return sent
