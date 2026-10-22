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
from lib.markup import telegram_html
from lib.telegram.general.message_master import render_messages, message_editor, MessageStructuresInterface
from lib.tools.logger import logger


def start(data: ControllerParams):
    welcome_message = construct_welcome_message(data['language_code'], data['chat_id'])

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


def construct_welcome_message(language_code, chat_id=None) -> list[MessageStructuresInterface]:
    # popular podcasts in the user's language as checkboxes, a tap subscribes to one
    top_list, mark, ticked = onboarding.picker(language_code, chat_id)
    return onboarding.welcome_message(language_code, top_list, ticked, mark)


def _redraw(data: ControllerParams, screen: list[MessageStructuresInterface]):
    if data['callback'] is not None and data['callback'].message is not None:
        try:
            message_editor(data['chat_id'], screen[0], data['callback'].message.message_id)
            return
        except Exception:
            pass
    render_messages(data['chat_id'], screen)


def _fresh(data: ControllerParams, toast: str = ''):
    """The list changed since it was drawn (or the button is from before): draw it again."""
    notify(data['callback'], data['message'], toast)
    top_list, mark, ticked = onboarding.picker(data['language_code'], data['chat_id'])
    _redraw(data, onboarding.welcome_message(data['language_code'], top_list, ticked, mark))


def toggle_pick(data: ControllerParams):
    # a tap is the subscription (ticks were left unsubscribed): a ticked one again unsubscribes
    index, _, checksum, mark = onboarding.read_tap(data['callback'].data if data['callback'] else None)
    if mark is None:
        return _fresh(data)
    top_list, mark, ticked = onboarding.picker(data['language_code'], data['chat_id'], mark)
    if index is None or index >= len(top_list) or checksum != onboarding.list_checksum(top_list):
        return _fresh(data)
    row, note = top_list[index], None
    if row['id'] in ticked:
        notify(data['callback'], data['message'], '')
        onboarding.unsubscribe(data['chat_id'], row)
        ticked.discard(row['id'])
    elif onboarding.subscribe_room(data['chat_id']) == 0:
        notify(data['callback'], data['message'], get_message('freeLimitReached', data['language_code']).format(
            limit=config.max_subscriptions_without_tariff), alert=True)
        return
    else:
        notify(data['callback'], data['message'], get_message("welcomeSubscribing", data['language_code']))
        done, failed, over = onboarding.subscribe(data['chat_id'], [row])
        if done:
            ticked.add(row['id'])
            recsModule.send_latest_episode_later(row['id'], data['chat_id'], data['language_code'])
        elif failed or over:
            note = onboarding.result_message(data['language_code'], [], failed, over)[0]['text']
    _redraw(data, onboarding.welcome_message(data['language_code'], top_list, ticked, mark, note))


def subscribe_picked(data: ControllerParams):
    _, mask, checksum, mark = onboarding.read_tap(data['callback'].data if data['callback'] else None)
    if mark is not None:
        # "Done": the ticks are subscribed already, this sums them up
        top_list, mark, ticked = onboarding.picker(data['language_code'], data['chat_id'], mark)
        if checksum != onboarding.list_checksum(top_list):
            return _fresh(data, get_message("screenOutdated", data['language_code']))
        names = [telegram_html.plain_text(row['name']) for row in top_list if row['id'] in ticked]
        if not names:
            notify(data['callback'], data['message'], get_message("welcomePickNothing", data['language_code']))
            return
        notify(data['callback'], data['message'], '')
        _redraw(data, onboarding.result_message(data['language_code'], names, [], []))
        return
    # a button drawn before: its ticks were never subscribed, subscribe them now
    top_list = onboarding.top_podcasts(data['language_code'], data['chat_id'])
    if checksum != onboarding.list_checksum(top_list):
        return _fresh(data, get_message("screenOutdated", data['language_code']))
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
