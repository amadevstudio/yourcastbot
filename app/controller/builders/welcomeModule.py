# -*- coding: utf-8 -*-
import json
from typing import TypedDict

import config
from app.controller.builders import podcastModule, recsModule
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.routes.ptypes import ControllerParams
from app.service.payment import paymentSafeModule
from app.service.podcast.subscription import add_sub
from config import db_path
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import render_messages, MessageStructuresInterface, InlineButtonData
from lib.tools.logger import logger


def start(data: ControllerParams):
    welcome_message = construct_welcome_message(
        data['language_code'], top=True)

    render_messages(data['chat_id'], message_structures=welcome_message)

    if data['is_command']:
        storage.clear_user_storage(data['chat_id'])


def referral_processing(data: ControllerParams, refer_id: int | None, action_mode: bool = False):
    db_users = SQLighter(config.db_path)

    # регистрируем, если он ещё нет, с учётом рефералки
    is_new_user, is_by_refer = db_users.register_new_user(
        data['chat_id'], data['language_code'], refer_id)

    if is_by_refer is True and refer_id is not None and int(refer_id) != int(data['chat_id']):
        result_message_for_refer = paymentSafeModule.giveAward(refer_id, data['chat_id'], 'reged')
    else:
        result_message_for_refer = None

    db_users.close()

    # даём платную подписку на неделю новому или на пару дней при /start
    # подписываем их на Ted Talks Daily
    welcome_message = paymentSafeModule.giveAward(data['chat_id'], 0, "new")
    if welcome_message is not None:
        # подписка на ted talks daily (только при выдаче награды, то есть в первый раз)
        pc_name, _ = add_sub(data['chat_id'], 21, 160904630, 'itunes')
        if pc_name is not None:
            welcome_message += "\n\n" + \
                               get_message(
                                   "weAlsoSignedYouOnPodcastName", data['language_code']) \
                               % (config.botName, "21", "Ted Talks Daily")

    # не забудьте посетить welcome, если открытие бота по ссылке (только при выдаче награды, то есть в первый раз)
    if action_mode:
        if welcome_message is not None:
            welcome_message += "\n\n" + get_message(
                "dontForgetToVisitStart", data['language_code'])

    # По вашей ссылке зарегистрировались
    if result_message_for_refer is not None:
        render_messages(refer_id, [{
            'type': 'text',
            'text': result_message_for_refer
        }], True)
    # Отправка приветственного сообщения
    if welcome_message is not None:
        render_messages(data['chat_id'], [{
            'type': 'text',
            'text': welcome_message
        }], True)

    return is_new_user, is_by_refer


class StartRelatedParamsType(TypedDict):
    action: str | None
    is_new_user: bool
    is_by_refer: bool


def start_related_options(data: ControllerParams) -> StartRelatedParamsType:
    action: str | None = None  # Открытие подкаста или выпуска из бота
    refer_id = None
    action_params = []

    if data['route_name'] != 'start':
        return {
            'action': None,
            'is_new_user': False,
            'is_by_refer': False
        }

    if data['message'] is not None:
        start_data = data['message'].text[7:]
        if start_data != '':
            # реферальный пользователь
            try:
                refer_id = int(start_data)
            except ValueError:
                # podcast + id
                # podcastItunes + itunes id
                action, *action_params = start_data.split("_")
                if action == '':
                    action = None

    is_new_user, is_by_refer = referral_processing(data, refer_id, action is not None)
    action_processing(data, action, *action_params)

    return {
        'action': action,
        'is_new_user': is_new_user,
        'is_by_refer': is_by_refer
    }


def action_processing(data: ControllerParams, action: str | None, *action_params: str):
    if action is not None:
        # открываем подкаст, если ссылка на канал
        try:
            if action in ["podcast", "podcastItunes"] and len(action_params) > 0 and data['message'] is not None:
                action_uniq_id = int(action_params[0])
                storage.del_user_state(data['chat_id'])
                storage.add_user_state(data['chat_id'], 'menu')
                storage.add_user_state(data['chat_id'], 'podcast')

                if action == "podcast":
                    data['message'].text = json.dumps({"id": action_uniq_id})
                elif action == "podcastItunes":
                    data['message'].text = json.dumps({"sId": action_uniq_id, "service": "itunes"})

                podcastModule.channel_query(data)

            elif action in ["episode", "episodeItunes"] and len(action_params) > 0:
                channel = int(action_params[0])
                prev_hash = action_params[1]
                from_num = int(action_params[2])

                storage.del_user_state(data['chat_id'])
                storage.add_user_state(data['chat_id'], "menu")

                if action == "episode":
                    episode_data = {"id": channel, "prev_hash": prev_hash, "from_num": from_num}
                elif action == "episodeItunes":
                    episode_data = {"sId": channel, "service": "itunes", "prev_hash": prev_hash, "from_num": from_num}
                else:
                    episode_data = {}

                recsModule.send_record_by_hash_using_start(data, episode_data)

        except Exception as e:
            logger.err(e)


def construct_welcome_message(language_code, offer=False, top=False) -> list[MessageStructuresInterface]:
    if top:
        welcome_elements_count = 6
        db_users = SQLighter(db_path)

        top_list = db_users.select_top(
            None,
            language_code, True,
            None, None, welcome_elements_count, 0)

        founded_count = len(top_list)
        top_list_glob = None
        if founded_count < welcome_elements_count:
            top_list_glob = db_users.select_top(
                None,
                language_code, False,
                None, None, (welcome_elements_count - founded_count), 0)

        db_users.close()

        if top_list_glob is not None:
            for el in top_list_glob:
                if el not in top_list:
                    top_list.append(el)

        def top_button_row(channels: list):
            return [{'text': channel["name"],
                    'callback_data': {"tp": "podcast", "id": channel["id"]}} for channel in channels]

        welcome_channels = [top_button_row(top_list[i: i + 2]) for i in range(0, len(top_list), 2)]

    # захардкоженный топ, в перспективе рекламные подкасты
    else:
        if language_code != 'ru':
            data_lang = 'en'
        else:
            data_lang = 'ru'
        welcome_channels_list = {
            "ru":
                {"list": [
                    {"name": "Лайфхакер", "id": 1297225487},
                    {"name": "Медуза: как жить", "id": 1325076874},
                    {"name": "Science Friday", "id": 73329284},
                    {"name": "КиноЧетверг", "id": 1029693220},
                    {"name": "The Empire Film Podcast", "id": 507987292}
                ]},
            "en":
                {"list": [
                    {"name": "Science Friday", "id": 73329284},
                    {"name": "The Empire Film Podcast", "id": 507987292}
                ]},
        }[data_lang]

        def top_button_row(channels: list):
            return [{'text': channel["name"],
                    'callback_data': {"tp": "podcast", "sId": channel["id"]}} for channel in channels]

        welcome_channels = [
            top_button_row(welcome_channels_list["list"][i: i + 2])
            for i in range(0, len(welcome_channels_list["list"]), 2)]

    if offer:
        b_text = "goBack"
        message_text = "offerMessage"
    else:
        b_text = "skipWelcome"
        message_text = "welcomeMessage"

    menu_button: InlineButtonData = {'text': get_message(b_text, language_code), 'callback_data': {'tp': 'menu'}}
    if len(welcome_channels[-1]) == 1:
        welcome_channels[-1].append(menu_button)
    else:
        welcome_channels.append([menu_button])

    search_button: InlineButtonData \
        = {'text': get_message("goToSearch", language_code), 'callback_data': {'tp': 'search'}}
    welcome_channels.append([search_button])

    result: list[MessageStructuresInterface] = [{
        'type': 'text',
        'text': get_message(message_text, language_code),
        'reply_markup': welcome_channels
    }]
    return result


def maintenance(data: ControllerParams):
    render_messages(data['chat_id'], [{
        'type': 'text', 'text': get_message("maintenance", data['language_code'])
    }], True)

    # Don't change state after
    return False
