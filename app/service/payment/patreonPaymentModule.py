import calendar
import datetime
import threading
from typing import Any

import patreon
import requests
from telebot import types

from agent.bot_telebot import bot
from app.controller.general.notify import notify
from app.routes.message_tools import go_back_inline_button, go_back_inline_markup
from app.routes.ptypes import ControllerParams
from lib.telegram.general.message_master import message_master, render_messages, InlineButtonData, outer_sender
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.service.payment.paymentModule import (
    decode_tariff, get_tariff_info_message, get_tariff_params_by_tg)
from config import (
    db_path, creator_email, special_paid_emails,
    patreon_creator_access_token, patreon_subs_perpage,
    donate_link)
from db.sqliteAdapter import SQLighter
from lib.tools.logger import logger


# страница ввода почты patreon
def open_subscription_page(data: ControllerParams):
    tariff, balance, time_left, notify_left = get_tariff_params_by_tg(data['chat_id'])

    sub_msg = get_sub_message(data['language_code'], tariff['level'], tariff['price'],
                              balance, time_left, notify_left)

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': sub_msg['message'], 'reply_markup': sub_msg['markup'],
        'disable_web_page_preview': True}])


def get_sub_message(language_code, tariff_lvl, tariff_price, balance, time_left, notify_left):
    message_text = "<b>" + get_message("bot_sub_page_header", language_code) + "</b>\n\n"
    message_text += get_message("patreon_page_body", language_code) + "\n\n"

    tariff_str = decode_tariff(tariff_lvl, language_code)
    message_text += get_tariff_info_message(
        tariff_str, balance, tariff_price, time_left, notify_left, language_code)

    menu_keyboard: list[list[InlineButtonData]] = [
        [{'text': get_message('pay', language_code), 'url': donate_link}],
        [{'text': get_message('tellPatreonEmail', language_code), 'callback_data': {'tp': 'bs_patrem'}}],
        [{'text': get_message('checkPatreonStatus', language_code), 'callback_data': {'tp': 'bs_patrupd'}}],
        [go_back_inline_button(language_code)]]

    result = {
        "message": message_text,
        "markup": menu_keyboard
    }
    return result


# страница ввода почты patreon / сохранение почты
def patreon_email_input_page(data: ControllerParams):
    # Update email if it is sent
    if data['callback'] is None:
        email = data['message'].text if data['message'] is not None else None

        db = SQLighter(db_path)
        db.savePaymentServiceEmail(data['chat_id'], email, "patreon")
        saved_email = db.getPaymentServiceEmail(data['chat_id'], "patreon")
        db.close()

        saved = (True if saved_email == email else False)
        tariff_payment_message = get_patreon_email_message(saved_email, data['language_code'], saved)

    # Show status message
    else:
        db = SQLighter(db_path)
        current_email = db.getPaymentServiceEmail(data['chat_id'], "patreon")
        db.close()

        tariff_payment_message = get_patreon_email_message(current_email, data['language_code'])

    render_messages(data['chat_id'], [{'type': 'text', 'text': tariff_payment_message['message'],
                                       'reply_markup': tariff_payment_message['markup']}],
                    resending=data['callback'] is None)


def get_patreon_email_message(current_email, language_code, status: bool | None = None):
    message_text = get_message("donate_page_email_input", language_code)
    if current_email is not None and current_email != "":
        message_text += "\n\n" + get_message("current_email", language_code) + ": " \
                        + current_email

    if status is not None:
        if status is True:
            message_text += "\n\n" + get_message("email_saved", language_code)
        elif status is False:
            message_text += "\n\n" + get_message("save_error", language_code)

    menu_key_board = go_back_inline_markup(language_code)

    result = {
        "message": message_text,
        "markup": menu_key_board
    }
    return result


def check_patreon_accounts(initiator=None):
    logger.log("Patron update, initiator: ", initiator)
    patrons = load_patrons()
    if patrons is None:
        logger.warn("Can't load patrons")
        return

    # Send to creator too for debug
    patrons[creator_email] = {
        "cents": 100,
    }

    db = SQLighter(db_path)
    payments_data = db.getPaymentDataByService("patreon")

    today = datetime.datetime.today().date()

    initiator_answer = None

    max_tariff = db.getExtremeTariff('max')

    db.close()

    for data in payments_data:
        patron_email = data['email'].lower()

        if patron_email in patrons:
            patron = patrons[patron_email]

            # TODO: check if patron active and update status
            # if active:

            last_update = data['last_replenishment']
            user_id = data['user_id']
            cents = int(patron['cents'])

            if patron_email in special_paid_emails:
                if cents < max_tariff['price']:
                    cents = max_tariff['price']

            db = SQLighter(db_path)
            user = db.get_user_by_id(user_id)
            current_subscription = db.getUserSubscriptionByUid(user['id'])

            # проверяем дату, должен быть
            # как минимум следующий месяц и второе число
            if last_update is not None:
                last_date = datetime.datetime.strptime(last_update, "%Y-%m-%d").date()
                # следующий месяц
                # и (
                # прошло больше 1 месяца
                # или день месяца старше
                # или последний день месяца
                # )
                months_delta = (today.year - last_date.year) * 12 \
                    + today.month - last_date.month
                if not (
                        (months_delta > 0)
                        and (
                                months_delta > 1
                                or today.day >= last_date.day
                                or today.day == calendar.monthrange(today.year, today.month)[1])
                ):
                    # посылаем инициатору сообщение, что уже было пополнено в этом месяце
                    if initiator is not None:
                        if initiator['telegramId'] == user['telegramId']:
                            initiator_answer = get_message(
                                "thisMonthHasAlreadyBeenReplenished", initiator['language_code'])
                    continue

            # Пополняем баланс в бд
            if current_subscription is None:
                db.subscribeUserToTariffByUid(
                    user['id'], 0, cents, 0, 0)
                current_subscription = {
                    'tariff_id': 0,
                    'balance': 0,
                    'time_left': 0,
                    'notify_count': 0
                }
            else:
                db.subscribeUserToTariffByUid(
                    user['id'], current_subscription['tariff_id'],
                    int(current_subscription['balance']) + cents,
                    current_subscription['time_left'],
                    current_subscription['notify_count'])

            now_utc = datetime.datetime.now(datetime.timezone.utc)

            db.updatePaymentServiceLastReplenishment(user_id, 'patreon', now_utc.strftime("%Y-%m-%d"))

            message = get_message("balanceFromPatreonAdded", user['lang'])

            tariff = db.getTariffById(current_subscription['tariff_id'])
            db.close()

            tariff_str = decode_tariff(tariff['level'], user['lang'])

            message += "\n\n" + get_tariff_info_message(
                tariff_str, int(current_subscription['balance']) + cents,
                tariff['price'], current_subscription['time_left'],
                current_subscription['notify_count'], user['lang'])

            # пополнение, шлём инициатору ниже
            if initiator is not None and initiator['telegramId'] == user['telegramId']:
                initiator_answer = message

            else:
                outer_sender(
                    user['telegramId'],
                    [{'type': 'text', 'text': message,
                      'reply_markup': go_back_inline_markup(user['lang'])}])

    # послать ошибку или сообщение инициатору
    if initiator is not None:
        # если инициатору не пришло, и при этом не прошёл месяц, значит, данных нет
        if initiator_answer is None:
            initiator_answer = get_message("noDataUpdatePatreon", initiator['language_code'])

        render_messages(initiator['telegramId'], [{
            'type': 'text', 'text': initiator_answer,
            'reply_markup': go_back_inline_markup(initiator['language_code'])}])
        storage.add_user_state(initiator['telegramId'], 'empty')


# загрузить патронов из patreon
def load_patrons() -> dict[str, Any] | None:
    api_client = patreon.API(patreon_creator_access_token)
    try:
        campaign_id = api_client.fetch_campaign_and_patrons().data()[0].id()
    except requests.exceptions.JSONDecodeError as e:
        logger.err(e)
        return None

    pledges_response = api_client.fetch_page_of_pledges(
        campaign_id,
        patreon_subs_perpage,
    )
    all_pledges = pledges_response.data()
    members: dict[str, Any] = {}
    for member in all_pledges:
        patron_email = member.relationship('patron').attribute('email').lower()
        members[patron_email] = {
            'cents': member.attribute('amount_cents'),
            'currency': member.attribute('currency'),
            'declined_since': member.attribute('declined_since'),
            'status': member.attribute('status'),
            'is_paused': member.attribute('is_paused'),
        }

    return members


# пользователь решил обновить вручную
def patreon_force_watcher(data: ControllerParams):
    notify(data['callback'], data['message'], get_message('updateInProgress', data['language_code']))
    one_fire_watcher = threading.Thread(
        target=check_patreon_accounts,
        kwargs={'initiator': {"telegramId": data['chat_id'], "language_code": data['language_code']}})
    one_fire_watcher.start()
