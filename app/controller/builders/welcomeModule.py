# -*- coding: utf-8 -*-
import json
from typing import TypedDict

import config
from app.controller.builders import onboarding, podcastModule, recsModule
from app.controller.general.notify import notify
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.routes.ptypes import ControllerParams
from app.service.payment import paymentSafeModule
from app.service.podcast.subscription import add_sub
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import render_messages, message_editor, MessageStructuresInterface
from lib.tools.logger import logger


def start(data: ControllerParams):
    welcome_message = construct_welcome_message(data['language_code'])

    render_messages(data['chat_id'], message_structures=welcome_message)

    if data['is_command']:
        storage.clear_user_storage(data['chat_id'])


def referral_processing(data: ControllerParams, refer_id: int | None, action_mode: bool = False):
    db_users = SQLighter(config.db_path)

    # A link names its inviter: only an existing user other than oneself.
    # get_user_by_tg (in giveAward) would create a row for any number in the link.
    if refer_id is not None and (
            int(refer_id) == int(data['chat_id']) or not db_users.user_exists_tg(refer_id)):
        refer_id = None

    # регистрируем, если он ещё нет, с учётом рефералки
    is_new_user, is_by_refer = db_users.register_new_user(
        data['chat_id'], data['language_code'], refer_id)

    if is_by_refer is True and refer_id is not None:
        result_message_for_refer = paymentSafeModule.giveAward(refer_id, data['chat_id'], 'reged')
    else:
        result_message_for_refer = None

    db_users.close()

    # даём платную подписку на неделю новому или на пару дней при /start
    # подписываем их на Ted Talks Daily
    # a friend's link (an existing user, not oneself) makes the welcome plan longer
    welcome_message = paymentSafeModule.giveAward(
        data['chat_id'], 0, "new", invited=result_message_for_refer is not None)
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
            'text': welcome_message,
            'reply_markup': [[{
                'text': get_message("goToSearch", data['language_code']),
                'callback_data': {'tp': 'search'},
            }]]
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

    # a button of the welcome screen (wPick, wSub) is routed as 'start' too: its message is the
    # bot's own text, not a /start command, and its parameters must not be read from it
    if data['route_name'] != 'start' or data['callback'] is not None:
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


def construct_welcome_message(language_code) -> list[MessageStructuresInterface]:
    # popular podcasts in the user's language as checkboxes, one tap subscribes to the ticked ones
    return onboarding.welcome_message(language_code, onboarding.top_podcasts(language_code))


def _redraw(data: ControllerParams, screen: list[MessageStructuresInterface]):
    if data['callback'] is not None and data['callback'].message is not None:
        try:
            message_editor(data['chat_id'], screen[0], data['callback'].message.message_id)
            return
        except Exception:
            pass
    render_messages(data['chat_id'], screen)


def toggle_pick(data: ControllerParams):
    top_list = onboarding.top_podcasts(data['language_code'])
    index, mask, checksum = onboarding.read_tap(data['callback'].data if data['callback'] else None)
    if index is None or checksum != onboarding.list_checksum(top_list):
        mask = 0  # the list changed since it was drawn: start over on the new one
    else:
        mask ^= 1 << index
    notify(data['callback'], data['message'], '')
    _redraw(data, onboarding.welcome_message(data['language_code'], top_list, mask))


def subscribe_picked(data: ControllerParams):
    top_list = onboarding.top_podcasts(data['language_code'])
    _, mask, checksum = onboarding.read_tap(data['callback'].data if data['callback'] else None)
    if checksum != onboarding.list_checksum(top_list):
        notify(data['callback'], data['message'], get_message("screenOutdated", data['language_code']))
        _redraw(data, onboarding.welcome_message(data['language_code'], top_list))
        return
    rows = onboarding.picked(top_list, mask)
    if not rows:
        notify(data['callback'], data['message'], get_message("welcomePickNothing", data['language_code']))
        return
    notify(data['callback'], data['message'], get_message("welcomeSubscribing", data['language_code']))
    done, failed, over = onboarding.subscribe(data['chat_id'], rows)
    _redraw(data, onboarding.result_message(data['language_code'], done, failed, over))


def maintenance(data: ControllerParams):
    render_messages(data['chat_id'], [{
        'type': 'text', 'text': get_message("maintenance", data['language_code'])
    }], True)

    # Don't change state after
    return False
