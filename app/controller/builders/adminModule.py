# -*- coding: utf-8 -*-

import threading
import time
from typing import Literal

import config
from app.repository.storage import storage
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import ControllerParams
from app.routes.routes_list import AvailableRoutes
from app.service.payment import paymentModule
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import render_messages
from lib.tools.logger import logger
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
        total: int, with_subs: int, with_bot_sub: int,
        receive_episodes: int, digest_reminder: int, blocked: int,
        updater_channel_id: int, max_channel_id: int) -> str:
    return (
        "Всего: " + str(total)
        + "\nС подписками на каналы: " + str(with_subs)
        + "\nС подпиской на бота: " + str(with_bot_sub)
        + "\nПолучают выпуски (тариф + уведомления): "
        + str(receive_episodes)
        + "\nНапоминание о боте (уведомления, без тарифа): "
        + str(digest_reminder)
        + "\nЗаблокировали бота (не считаются выше): " + str(blocked)
        + "\nОбход подкастов: "
        + str(updater_channel_id) + " / " + str(max_channel_id)
    )


_users_count_lock = threading.Lock()
_users_count_running = False


def compute_users_count_text() -> str:
    started = time.monotonic()
    db_users = SQLighter(config.db_path)
    try:
        total = db_users.count_users()
        with_subs = db_users.count_users(True)
        with_bot_sub = db_users.count_users(payed=True)
        receive_episodes = db_users.count_users(receive_episodes=True)
        digest_reminder = db_users.count_users(digest_reminder=True)
        blocked = db_users.count_users(deleted=True)
        last_channel_row = db_users.get_last_channel_id()
        max_channel_id = int(last_channel_row['id']) if last_channel_row else 0
    finally:
        db_users.close()
    text = format_users_count_message(
        total, with_subs, with_bot_sub, receive_episodes, digest_reminder,
        blocked, storage.get_last_channel_id(), max_channel_id)
    logger.log(
        "usersCount computed in %.2fs" % (time.monotonic() - started,))
    return text


def send_users_count_to_creator(data: ControllerParams):
    # Off the incoming worker so this chat's next message is not queued
    # behind the COUNT, and extra /usersCount is dropped.
    global _users_count_running
    chat_id = data['chat_id']
    language_code = data['language_code']

    with _users_count_lock:
        if _users_count_running:
            return
        _users_count_running = True

    def work():
        global _users_count_running
        try:
            text = compute_users_count_text()
        except Exception as e:
            logger.err("usersCount failed:", e)
            text = "Не получилось посчитать: %s" % e
        try:
            storage.set_user_resend_flag(chat_id)
            render_messages(chat_id, [{
                'type': 'text',
                'text': text,
                'reply_markup': go_back_inline_markup(language_code)
            }])
        except Exception as e:
            logger.err("usersCount reply failed:", e)
        finally:
            with _users_count_lock:
                _users_count_running = False

    threading.Thread(target=work, name="usersCount", daemon=True).start()


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
    send_message_to_creator('Поток упал! Перезагрузка роли...', level='fatal')


def send_message_to_creator(message_text: str, level: CreatorAlertLevel = 'info'):
    tagged = f"{_CREATOR_TAGS[level]}\n{message_text}"
    try:
        from agent.bot_telebot import bot
        bot.send_message(config.creatorId, tagged)
    except Exception as e:
        logger.err("send_message_to_creator failed:", e)
