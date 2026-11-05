# -*- coding: utf-8 -*-
"""A Stars payment taken back: what the chat and the creator hear (db/stars_refund.py
takes it off the balance and the plan).

Two ways in, one effect: the service message Telegram sends for a refund
(`MessageActionPaymentRefunded`, the bot role) and a daily look at the bot's
Star transactions (`getStarTransactions`, the jobs role), for a chargeback at
Apple, Google or a bank that Telegram deducts from the bot's balance: the Bot
API says so, it does not say such a refund sends the message. A refund is an
outgoing transaction (`receiver`) whose id is the payment's charge id.
Lock: python app/service/payment/test_stars_refund.py
"""
import time

from app.i18n.messages import get_message
from app.service import analytics_events
from config import db_path
from db import runtime_kv, stars_refund
from db.connection import connect_sqlite
from lib.tools.logger import logger

CHECK_EVERY_SECONDS = 24 * 3600
FIRST_CHECK_DELAY_SECONDS = 600
LAST_CHECK_KEY = 'stars_refund_checked_at'
PAGE = 100  # getStarTransactions' limit
MAX_PAGES = 200


def notice_text(refund: dict, language_code) -> str:
    from app.service.payment.paymentSafeModule import days_left_text, money_text
    lines = [get_message('starsRefunded', language_code).format(amount=money_text(refund['amount']))]
    if refund['hours']:
        if refund['time_left'] > 0:
            lines.append(get_message('starsRefundDays', language_code).format(
                days=days_left_text(refund['time_left'])))
        else:
            lines.append(get_message('starsRefundPlanOff', language_code))
    if refund['balance'] < 0:
        lines.append(get_message('starsRefundDebt', language_code).format(debt=money_text(-refund['balance'])))
    return "\n\n".join(lines)


def _chat(user_id, database=None):
    connection = connect_sqlite(db_path if database is None else database)
    try:
        row = connection.execute("SELECT telegramId, lang FROM users WHERE id = ?", (int(user_id),)).fetchone()
    finally:
        connection.close()
    return (row[0], row[1] or 'en') if row else (None, 'en')


def _notify_creator(text):
    try:
        from app.controller.builders.adminModule import send_message_to_creator
        send_message_to_creator(text, level='info')
    except Exception as e:
        logger.warn('stars refund: creator not told:', e)


def process_refund(charge_id, source, database=None, send=None, notify_creator=None) -> dict | None:
    """Take the payment back once and tell the chat; None when there was nothing
    to take back (unknown charge, or done before). Never raises for a notice."""
    refund = stars_refund.apply_refund(charge_id, database)  # once: checked and changed in one transaction
    if refund is None:
        return None
    logger.warn('Telegram Stars refund', source, refund)
    chat_id, language_code = _chat(refund['user_id'], database)
    if chat_id is not None:
        analytics_events.track(chat_id, 'payment_refunded', {
            'method': stars_refund.STARS_SERVICE_TYPE, 'source': source,
            'amount_cents': refund['amount'], 'hours': refund['hours']}, database=database)
        try:
            if send is None:
                from lib.telegram.general.message_master import outer_sender as send
            buttons = [[
                {'text': get_message('tariffs', language_code), 'callback_data': {'tp': 'bs_trfs'}},
                {'text': get_message('goBackMenu', language_code), 'callback_data': {'tp': 'menu'}}]]
            if not send(chat_id, [{'type': 'text', 'text': notice_text(refund, language_code),
                                   'reply_markup': buttons}]):
                logger.warn('stars refund notice not delivered to', chat_id)
        except Exception as e:
            logger.warn('stars refund notice:', type(e).__name__, e)
    (notify_creator or _notify_creator)(
        "Telegram Stars refund (%s): user %s, $%.2f off the balance, %d h of the plan taken back, balance $%.2f"
        % (source, refund['user_id'], refund['amount'] / 100, refund['hours'], refund['balance'] / 100))
    return refund


def refunded_charge_ids(transactions) -> set:
    """Ids of the outgoing transactions: a refund keeps the id of the payment it returns."""
    return {str(t['id']) for t in transactions if t.get('receiver') and t.get('id')}


def fetch_transactions(request=None) -> list:
    """Every Star transaction of the bot, oldest first (Bot API getStarTransactions)."""
    if request is None:
        from telebot import apihelper
        from agent.bot_telebot import bot

        def request(offset):
            return apihelper._make_request(bot.token, 'getStarTransactions', method='post',
                                           params={'offset': offset, 'limit': PAGE})
    transactions = []
    for page in range(MAX_PAGES):
        batch = (request(page * PAGE) or {}).get('transactions') or []
        transactions.extend(batch)
        if len(batch) < PAGE:
            break
    return transactions


def check_transactions(request=None, database=None, send=None, notify_creator=None) -> int:
    """Refunds among the bot's transactions not taken back yet; how many were."""
    paid = stars_refund.paid_charge_ids(database)
    if not paid:
        return 0
    found = refunded_charge_ids(fetch_transactions(request)) & paid
    return sum(1 for charge_id in sorted(found)
               if process_refund(charge_id, 'transactions', database, send, notify_creator))


def refund_watcher():
    """The jobs role: the bot's transactions once a day (the last check survives a restart)."""
    time.sleep(FIRST_CHECK_DELAY_SECONDS)
    while True:
        try:
            last = float(runtime_kv.get_kv(LAST_CHECK_KEY) or 0)
            if time.time() - last >= CHECK_EVERY_SECONDS:
                found = check_transactions()
                runtime_kv.set_kv(LAST_CHECK_KEY, str(time.time()))
                if found:
                    logger.log('Stars refunds found among the transactions:', found)
        except Exception as e:
            logger.warn('stars refund check:', type(e).__name__, e)
        time.sleep(3600)
