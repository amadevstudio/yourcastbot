# -*- coding: utf-8 -*-
import math

from app.controller.builders import advertisingModule
from app.controller.builders.advertisingModule import get_advertising_text
from app.routes.ptypes import ControllerParams
from lib.telegram.general.message_master import render_messages, MessageStructuresInterface, InlineButtonData
from app.i18n.messages import get_message, standartSymbols
from app.repository.storage import storage
from app.service.payment import paymentModule
from config import db_path, advertising_contact
from db.sqliteAdapter import SQLighter
from lib.tools.logger import logger


def send_menu_message(data: ControllerParams):
    menu_message = construct_menu_message(
        data['language_code'], data['chat_id'])
    if not data['is_step_back']:
        storage.clear_user_storage(data['chat_id'])

    render_messages(data['chat_id'], message_structures=menu_message, resending=data['is_command'])


def construct_menu_message(language_code, chat_id) -> list[MessageStructuresInterface]:
    # информация о тарифе
    tariff, balance, time_left, notify_left = \
        paymentModule.get_tariff_params_by_tg(chat_id)
    tariff_str = \
        paymentModule.decode_tariff(tariff['level'], language_code)
    message = "<b>" + \
              get_message("curr_tariff", language_code) + \
              ": " + tariff_str + \
              "</b>"
    if tariff['level'] == 0:
        message += "\n" + get_message(
            "you_cant_recieve_notifications", language_code)
    else:
        if tariff['price'] > balance:
            if 0 < time_left < 24:
                days_left_str = "<1"
            else:
                days_left_str = str(math.floor(time_left / 24))

            message += "\n" + get_message("days_left", language_code) % \
                       days_left_str + " "
            message += \
                get_message("not_enough_for_renewal", language_code) \
                % str(paymentModule.prepare_price(tariff['price'] - balance, 0.5))

    ad_message = get_advertising_text(chat_id, language_code)
    if ad_message is not None:
        message += "\n\n" + ad_message

    message += "\n\n" + get_message("patreonShort", language_code)

    # есть ли новые эпизоды
    db_users = SQLighter(db_path)
    have_new_eps = db_users.is_user_have_new_episodes(chat_id)
    db_users.close()

    if have_new_eps:
        message += "\n\n" + standartSymbols.get("newItem", "") + " " \
                   + get_message("youHaveNewEpisodesShort", language_code)

    message += "\n\n" + get_message('advertisingQuestions', language_code) % advertising_contact

    message += "\n\n" + get_message("menuMessage", language_code)

    # кнопки меню
    new_eps = standartSymbols.get("newItem", "") + " " if have_new_eps else ""

    menu_keyboard: list[list[InlineButtonData]] = []

    menu_keyboard.append([{
        'text': get_message("search", language_code),
        'callback_data': "{\"tp\": \"search\"}"
    }, {
        'text': new_eps + get_message("subscriptions", language_code),
        'callback_data': "{\"tp\": \"subs\", \"p\": 1}"}
    ])

    menu_keyboard.append([
        {'text': get_message("update", language_code), 'callback_data': "{\"tp\": \"update\"}"},
        {'text': get_message("another_projects", language_code), 'callback_data': "{\"tp\": \"another\"}"}])

    menu_keyboard.append([
        {'text': get_message("podcastTop", language_code), 'callback_data': "{\"tp\": \"topGnrs\", \"p\": 1}"},
        {'text': get_message("podcastTopLang", language_code),
         'callback_data': "{\"tp\": \"topGnrs\", \"p\": 1, \"lngTp\": true}"}
    ])

    menu_keyboard.append([
        {'text': get_message("donation", language_code), 'callback_data': "{\"tp\": \"donate\"}"},
        {'text': get_message("help", language_code), 'callback_data': "{\"tp\": \"help\"}"}])

    menu_keyboard.append([
        {'text': get_message("channelConnect", language_code), 'callback_data': "{\"tp\": \"myTgChannels\"}"},
        {'text': get_message("add_by_rss", language_code), 'callback_data': "{\"tp\": \"addChByRss\"}"}])

    b1: InlineButtonData = {'text': get_message("bot_subscription", language_code),
                            'callback_data': "{\"tp\": \"botSub\"}"}
    # b2 = {'text': get_message("settings", language_code), '#':     callback_data="{\"tp\": \"setts\"}"}
    menu_keyboard.append([b1])

    return [{
        'type': 'text',
        'text': message,
        'reply_markup': menu_keyboard,
        'disable_web_page_preview': ad_message is None
    }]
