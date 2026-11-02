# -*- coding: utf-8 -*-
"""Run what payments set off (db/payment_effects.py), in the jobs role.

Each effect has a handler here: handler(user_id) runs at least once per
payment and must be idempotent. One that fails is tried again later; after
db.payment_effects.MAX_ATTEMPTS the creator hears of it. A payment is never
touched: its money is credited before any of this runs.

PAID_MODELS: better AI models on (app/service/ai/paid_models.py). The first
time it turns them on, with a plan running, the chat hears so, once, with
where to turn them off; a renewal, a chat that turned them off, or a top-up
with no plan running hears nothing. Not delivered (blocked, no network) is a
WARN: the models are on all the same.

At start, chats that paid before the effect existed get its row
(`backfill`, once per chat).
Lock: python app/jobs/test_payment_effects.py
"""
import time

from app.i18n.messages import get_message
from app.service.ai import paid_models
from config import db_path
from db import payment_effects
from db.connection import connect_sqlite
from lib.tools.logger import logger

CHECK_SECONDS = 30


def _chat(user_id, database=None):
    connection = connect_sqlite(db_path if database is None else database)
    try:
        row = connection.execute("SELECT telegramId, lang FROM users WHERE id = ?", (int(user_id),)).fetchone()
    finally:
        connection.close()
    return (row[0], row[1] or 'en') if row else (None, 'en')


def turn_on_paid_models(user_id, database=None, send=None):
    if not paid_models.available() or not paid_models.turn_on(user_id, database):
        return  # nothing configured, or set before (on, or the user's off): nothing to say
    chat_id, lang = _chat(user_id, database)
    if not chat_id or paid_models.standing(chat_id, database) != paid_models.ON:
        return  # no plan running (a top-up): the models come with the plan, nothing to announce now
    text = get_message('paidModelsOnNotice', lang).format(what=paid_models.what(lang))
    if send is None:
        from lib.telegram.general.message_master import outer_sender as send  # the bot's client: jobs role only
    if not send(chat_id, [{'type': 'text', 'text': text}]):
        logger.warn('payment effect: paid models notice not delivered to', chat_id)


HANDLERS = {payment_effects.PAID_MODELS: turn_on_paid_models}


def run_due(handlers=None, database=None, now=None, notify=None) -> int:
    """Every effect that is due, one after another; how many ran."""
    handlers = HANDLERS if handlers is None else handlers
    ran = 0
    while True:
        row = payment_effects.claim(database, now)
        if row is None:
            return ran
        ran += 1
        handler = handlers.get(row['effect'])
        error = None
        try:
            if handler is None:
                raise LookupError('no handler for %s' % row['effect'])
            handler(row['user_id'], database=database)
        except Exception as e:
            error = '%s: %s' % (type(e).__name__, e)
            logger.warn('payment effect', row['effect'], 'of', row['payment'], 'failed:', error)
        if payment_effects.finish(row, error, database, now) == 'failed':
            message = 'payment effect %s of %s failed %d times: %s' % (
                row['effect'], row['payment'], row['attempts'], error)
            logger.err(message)
            if notify:
                notify(message)


def _notify_creator(text):
    try:
        from app.controller.builders.adminModule import send_message_to_creator
        send_message_to_creator(text, level='warning')
    except Exception as e:
        logger.warn('payment effect: creator not told:', e)


def backfill(database=None) -> int:
    if not paid_models.available():
        return 0
    return payment_effects.backfill(payment_effects.PAID_MODELS, paid_models.paying_users(database), database)


def effects_watcher():
    try:
        added = backfill()
        if added:
            logger.log('Payment effects: paid models for', added, 'chats that paid before')
    except Exception as e:
        logger.warn('payment effects backfill:', type(e).__name__, e)
    while True:
        try:
            run_due(notify=_notify_creator)
        except Exception as e:
            logger.err('payment effects:', e)
        time.sleep(CHECK_SECONDS)
