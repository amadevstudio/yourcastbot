# -*- coding: utf-8 -*-

from typing import Literal

import config
from app.repository.storage import storage
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import ControllerParams
from app.routes.routes_list import AvailableRoutes
from app.service.payment import paymentModule
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import render_messages
from scripts import restart_bot as restart_bot_script

CreatorAlertLevel = Literal['fatal', 'error', 'warning', 'info']

_CREATOR_TAGS = {
    'fatal': '#problem #fatal',
    'error': '#problem #error',
    'warning': '#problem #warning',
    'info': '#info',
}


def is_admin(data: ControllerParams) -> bool:
    if data['chat_id'] != config.creatorId:
        return False

    return True


def format_users_count_message(
        total: int, with_subs: int, with_subs_notify: int,
        with_bot_sub: int, blocked: int,
        updater_channel_id: int, max_channel_id: int) -> str:
    return (
        "Всего: " + str(total)
        + "\nС подписками на каналы: " + str(with_subs)
        + "\nС подписками и уведомлениями: " + str(with_subs_notify)
        + "\nС подпиской на бота: " + str(with_bot_sub)
        + "\nЗаблокировали бота (не считаются выше): " + str(blocked)
        + "\nАпдейтер каналов: "
        + str(updater_channel_id) + " / " + str(max_channel_id)
    )


def send_users_count_to_creator(data: ControllerParams):
    db_users = SQLighter(config.db_path)
    total = db_users.count_users()
    with_subs = db_users.count_users(True)
    with_subs_notify = db_users.count_users(with_subs_active=True)
    with_bot_sub = db_users.count_users(payed=True)
    blocked = db_users.count_users(deleted=True)
    last_channel_row = db_users.get_last_channel_id()
    max_channel_id = int(last_channel_row['id']) if last_channel_row else 0
    db_users.close()
    render_messages(data['chat_id'], [{
        'type': 'text',
        'text': format_users_count_message(
            total, with_subs, with_subs_notify, with_bot_sub, blocked,
            storage.get_last_channel_id(), max_channel_id),
        'reply_markup': go_back_inline_markup(data['language_code'])
    }])


def add_to_balance(data: ControllerParams):
    if data['message'] is None:
        return

    incoming = data['message'].text.split()
    user_tg_id = incoming[1]
    new_balance = int(incoming[2]) * 100

    db_users = SQLighter(config.db_path)
    curr_sub = db_users.getUserSubscriptionByTg(user_tg_id)
    curr_trf = db_users.getTariffById(curr_sub['tariff_id'])

    if curr_sub is not None:
        new_balance += int(curr_sub['balance'])

    db_users.subscribeUserToTariffByTg(
        user_tg_id, curr_sub['tariff_id'], new_balance,
        curr_sub['time_left'], curr_sub['notify_count'])

    db_users.close()

    lang_code = 'en'
    tariff_str = paymentModule.decode_tariff(curr_trf['level'], lang_code)
    tariffs_sub_msg = paymentModule.get_tariff_info_message(
        tariff_str, new_balance, curr_trf['price'],
        curr_sub['time_left'], curr_sub['notify_count'], lang_code)

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': tariffs_sub_msg, 'reply_markup': go_back_inline_markup(data['language_code'])}])


def restart_bot(_: ControllerParams):
    send_thread_dead_message_to_creator()
    restart_bot_script.restart()


def show_commands(data: ControllerParams):
    admin_commands: list[AvailableRoutes] = ['usersCount', 'admin_restartBot', 'addToBalance']
    helpers: dict[AvailableRoutes, str] = {'addToBalance': "/addToBalance tg_id amount_dlrs"}
    msg = ""
    for admin_command in admin_commands:
        msg += helpers.get(admin_command, f"/{admin_command}") + "\n"

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': msg, 'reply_markup': go_back_inline_markup(data['language_code'])}])


# Helpers
def send_thread_dead_message_to_creator():
    storage.set_last_channel_restarted(True)
    send_message_to_creator('Поток упал! Перезагрузка...', level='fatal')


def send_message_to_creator(message_text: str, level: CreatorAlertLevel = 'info'):
    tagged = f"{_CREATOR_TAGS[level]}\n{message_text}"
    render_messages(config.creatorId, [{'type': 'text', 'text': tagged}], resending=True)
