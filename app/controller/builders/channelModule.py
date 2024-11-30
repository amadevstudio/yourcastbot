import json
import typing
from typing import TypedDict, Required

from agent.bot_telebot import bot
from app.controller.general.notify import notify
import app.i18n.messages
import app.service.user.language
from app.core.message.navigationBuilder import determine_search_query_and_page, get_full_message_navigation, \
    FullMessageNavigation
from app.routes.message_tools import go_back_inline_markup, go_back_inline_button
from lib.telegram.general.message_master import message_master, render_messages, InlineButtonData
from app.i18n.messages import get_message, get_message_rtd, emojiCodes
from app.repository.storage import storage
from app.service.payment import paymentModule
from config import db_path, maxTgChannelsPerAccount
from db.sqliteAdapter import SQLighter
from app.routes.ptypes import ControllerParams
from lib.tools.logger import logger

PER_PAGE = 5


# открыть страницу каналов юзера
def open_connecting_channel(data: ControllerParams):
    tariff, balance, time_left, notify_left = paymentModule.get_tariff_params_by_tg(data['chat_id'])

    db = SQLighter(db_path)
    tariffs = db.getTariffs(channel_control=True)
    db.close()

    conn_message = get_connecting_channel_message(data['language_code'], tariff, tariffs)

    render_messages(data['chat_id'], [{'type': 'text', 'text': conn_message['message'],
                                       'reply_markup': conn_message['markup']}])


# сборка сообщения
def get_connecting_channel_message(language_code, tariff, tariffs):
    message_text = ""

    keyboard: list[list[InlineButtonData]] = []

    required_tariff_levels = [x['level'] for x in tariffs]

    if tariff['level'] in required_tariff_levels:
        message_text += get_message("connectTgChannelMessage", language_code)

        keyboard.append([{'text': get_message('myTgChannels', language_code),
                          'callback_data': {'tp': 'myTgChnlList', 'p': 1}}])
        keyboard.append([{'text': get_message('addTgChannel', language_code),
                          'callback_data': {'tp': 'addTgChannel', 'p': 1}}])

    else:
        if len(required_tariff_levels) > 0:
            required_tariff_levels_message = ",  ".join(
                [paymentModule.decode_tariff(x, language_code)
                 for x in required_tariff_levels][:len(required_tariff_levels) - 1])
            if len(required_tariff_levels) > 1:
                required_tariff_levels_message += "  %s  " % get_message("or", language_code)
            required_tariff_levels_message += paymentModule.decode_tariff(
                required_tariff_levels.pop(), language_code)
        else:
            required_tariff_levels_message = ""

        message_text += get_message("connectTgChannelMessage", language_code) \
            + "\n\n" + get_message("cantConnectTgChannelMessage", language_code) % (
                            required_tariff_levels_message,
                            paymentModule.decode_tariff(tariff['level'], language_code))

    keyboard += go_back_inline_markup(language_code)

    result = {
        "message": message_text,
        "markup": keyboard
    }
    return result


# открыть страницу добавленных каналов юзера
def open_channel_list(data: ControllerParams):
    current_state_data = determine_search_query_and_page(data['callback'], data['message'], data['united_data'])

    # search_query = current_state_data.get('search', None)
    search_query = None  # We are don't keep the name of connected channel for now TODO: let's keep?

    db_users = SQLighter(db_path)
    message_navigation = get_full_message_navigation(
        current_state_data.get('p', None), search_query,
        db_users.get_user_tg_channels,[data['chat_id']],  # search_query
        db_users.get_user_tg_channels_count, [data['chat_id']],  # search_query
        PER_PAGE, 'ch.tg_id DESC',
        data['language_code'], data['route_name'], back_button_text='goBackMenu')
    db_users.close()

    if 'error' in message_navigation['page_data']:
        logger.warn(message_navigation['page_data']['error'])
        if message_navigation['page_data']['error'] == 'empty':
            error_message = get_message('yourTgChannelsEmpty', data['language_code'])
        else:
            error_message = get_message_rtd(['errors', 'unknown'], data['language_code'])
        notify(data['callback'], data['message'], error_message)
        return

    list_message = get_channel_list_message(data['language_code'], message_navigation)

    render_messages(data['chat_id'], list_message)

    storage.set_user_state_data(data['chat_id'], "myTgChnlList", {
        **current_state_data, 'p': message_navigation['page_data']['current_page']})


# сборка сообщения
def get_channel_list_message(language_code, message_navigation: FullMessageNavigation):
    message_text = get_message("yourTgChannelList", language_code)
    message_text += message_navigation['routing_helper_message']

    keyboard: list[list[InlineButtonData]] = []

    for channel in message_navigation['page_data']['data']:
        if channel['active']:
            title = emojiCodes['whiteHeavyCheckMark']
        else:
            title = emojiCodes['crossMark']

        title += f" ({channel['podcast_count']}) "

        try:
            tg_channel = bot.get_chat(channel['tg_id'])
            title += tg_channel.title
        except Exception:
            title += str(channel['tg_id'])

        keyboard.append([{'text': title, 'callback_data': {'tp': 'myTgChannel', 'id': channel['id']}}])

    if message_navigation['nav_layout_parts'] is not None:
        if message_navigation['nav_layout_parts'].get('exit_search_mode_row', None) is not None:
            keyboard += [message_navigation['nav_layout_parts']['exit_search_mode_row']]
        keyboard += [message_navigation['nav_layout_parts']['navigation_row']]

    return [{
        'type': 'text',
        'text': message_text,
        'reply_markup': keyboard
    }]


class TgChannelDataType(TypedDict, total=False):
    id: Required[int]
    user_id: Required[int]
    tg_id: Required[int]
    active: Required[bool]
    podcast_count: Required[int]
    title: str | None
    deleting: bool


def get_channel_title(channel_id: int) -> str | None:
    try:
        channel = bot.get_chat(channel_id)
        return channel.title
    except Exception:
        # Possible not an admin
        return None


# открыть страницу управления добавленным каналом
def open_connected_channel(data: ControllerParams):
    db = SQLighter(db_path)
    channel_data_row = db.getTgChannelDataById(data['chat_id'], data['united_data']['id'])
    db.close()

    channel_data: TgChannelDataType = {
        'id': channel_data_row['id'], 'user_id': channel_data_row['user_id'], 'tg_id': channel_data_row['tg_id'],
        'active': channel_data_row['active'], 'podcast_count': channel_data_row['podcast_count']}

    channel_data['title'] = get_channel_title(channel_data['tg_id'])

    stop_deleting_channel(channel_data)

    channel_message = get_connected_channel_message(channel_data, data['language_code'])

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': channel_message['message'], 'reply_markup': channel_message['markup']}])

    storage.set_user_state_data(data['chat_id'], 'myTgChannel', channel_data)


# сборка сообщения
def get_connected_channel_message(tg_channel_data, language_code):
    message_text = emojiCodes.get('electricPlug', '') + "\n"

    if tg_channel_data.get('title', None) is None:
        message_text += "<b>" + str(tg_channel_data["tg_id"]) + "</b>\n\n"
        message_text += get_message("tgChannelNotFoundEnsureBotAdmin", language_code)

        if 'deleting' in tg_channel_data:
            btn_text = emojiCodes['warning']
        else:
            btn_text = emojiCodes['exclamationMark']
        keyboard: list[list[InlineButtonData]] = [[{
            'text': btn_text + get_message("tgChannelDelete", language_code),
            'callback_data': {'tp': 'myTgChDel'}
        }, go_back_inline_button(language_code)]]

        return {'message': message_text, 'markup': keyboard}

    message_text += "<b>" + tg_channel_data['title'] + "</b>\n\n"
    message_text += get_message("yourTgChannel", language_code)

    keyboard = []

    if tg_channel_data['active']:
        btn_text = emojiCodes['whiteHeavyCheckMark']
    else:
        btn_text = emojiCodes['crossMark']
    btn_text += " " + get_message('tgChannelStatus', language_code) + " "
    keyboard.append([{'text': btn_text, 'callback_data': {'tp': 'changeTgChActive'}}])

    keyboard.append([{
        'text': f"{get_message('tgChannelSubs', language_code)} ({tg_channel_data['podcast_count']})",
        'callback_data': {'tp': 'myTgChSubs', 'p': 1}}])

    if 'deleting' in tg_channel_data:
        btn_text = emojiCodes['warning']
    else:
        btn_text = emojiCodes['exclamationMark']
    btn_text += " " + get_message('tgChannelDelete', language_code)
    keyboard.append([{'text': btn_text, 'callback_data': {'tp': 'myTgChDel'}}])

    keyboard += go_back_inline_markup(language_code)

    return {'message': message_text, 'markup': keyboard}


# смена активности
def change_channel_active(data: ControllerParams):
    tg_channel_data = typing.cast(TgChannelDataType, data['united_data'])
    stop_deleting_channel(tg_channel_data)

    tg_channel_data['active'] = not tg_channel_data['active']

    db = SQLighter(db_path)
    db.addOrUpdateTgChannel(data['chat_id'], tg_channel_data['tg_id'], tg_channel_data['active'])
    db.close()

    storage.set_user_state_data(data['chat_id'], 'myTgChannel', tg_channel_data)

    tg_channel_data['title'] = get_channel_title(tg_channel_data['tg_id'])

    channel_message = get_connected_channel_message(tg_channel_data, data['language_code'])

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': channel_message['message'], 'reply_markup': channel_message['markup']}])


# удаление канала
def stop_deleting_channel(tg_channel_data: TgChannelDataType):
    if 'deleting' in tg_channel_data:
        del tg_channel_data['deleting']
    return tg_channel_data


def delete_channel(data: ControllerParams):
    # !!! удаление
    if 'deleting' in data['united_data']:
        db = SQLighter(db_path)
        db.deleteTgChannel(data['chat_id'], data['united_data']['id'])
        db.close()

        return data['go_back_action'](data)

    # первый клик, подготовка к удалению
    data['united_data']['deleting'] = True

    storage.set_user_state_data(data['chat_id'], 'myTgChannel', data['united_data'])

    data['united_data']['title'] = get_channel_title(data['united_data']['tg_id'])

    channel_message = get_connected_channel_message(data['united_data'], data['language_code'])

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': channel_message['message'], 'reply_markup': channel_message['markup']}])

    notify(data['callback'], data['message'],
           get_message('tapAgainToDeleteTgChannel', data['language_code']), alert=True)


# страница с подписками канала
def open_channel_subs(data: ControllerParams):
    tg_channel_data = typing.cast(
        TgChannelDataType, storage.get_user_state_data(data['chat_id'], 'myTgChannel'))
    stop_deleting_channel(tg_channel_data)

    current_state_data = determine_search_query_and_page(data['callback'], data['message'], data['united_data'])
    search_query = current_state_data.get('search', None)

    db = SQLighter(db_path)
    message_navigation = get_full_message_navigation(
        current_state_data.get('p', None), search_query,
        db.select_users_subs_name_tg_channel, [data['chat_id'], tg_channel_data['id'], search_query],
        db.select_users_subs_count, [data['chat_id'], search_query],
        PER_PAGE, ['channels.name'],
        data['language_code'], 'myTgChSubs')
    db.close()

    if 'error' in message_navigation['page_data']:
        logger.warn(message_navigation['page_data']['error'])
        if message_navigation['page_data']['error'] == 'empty':
            error_message = get_message_rtd(['subs', 'error', 'paging', 'empty'], data['language_code'])
        else:
            error_message = get_message_rtd(['errors', 'unknown'], data['language_code'])
        notify(data['callback'], data['message'], error_message)
        return

    list_message = get_channel_sub_list_message(data['language_code'], message_navigation)

    render_messages(data['chat_id'], list_message)

    storage.set_user_state_data(data['chat_id'], 'myTgChSubs', {
        **current_state_data, 'p': message_navigation['page_data']['current_page']})


# сборка сообщения
def get_channel_sub_list_message(language_code, message_navigation: FullMessageNavigation):
    message_text = get_message("yourTgChannelSubList", language_code)
    message_text += message_navigation['routing_helper_message']

    keyboard: list[list[InlineButtonData]] = []

    for sub in message_navigation['page_data']['data']:

        if int(sub['connected']) == 1:
            button_text = emojiCodes['whiteHeavyCheckMark'] + " "
        else:
            button_text = ""
        button_text += sub['name'] if sub['name'] is not None else ''

        keyboard.append([{'text': button_text, 'callback_data': {'tp': 'myTgChSubChActive', 'id': sub['id']}}])

    if message_navigation['nav_layout_parts'] is not None:
        if message_navigation['nav_layout_parts'].get('exit_search_mode_row', None) is not None:
            keyboard += [message_navigation['nav_layout_parts']['exit_search_mode_row']]
        keyboard += [message_navigation['nav_layout_parts']['navigation_row']]

    return [{
        'type': 'text',
        'text': message_text,
        'reply_markup': keyboard
    }]


# привязка подкаста к каналу
def change_channel_sub_active(data: ControllerParams):
    tg_channel_data = typing.cast(
        TgChannelDataType, storage.get_user_state_data(data['chat_id'], 'myTgChannel'))

    channel_id = tg_channel_data['id']

    podcast_id = data['united_data']['id']

    db = SQLighter(db_path)
    updated = db.changeTgChannelToPodcastConnect(data['chat_id'], channel_id, podcast_id)
    db.close()

    # обновляем счётчик числа подкастов
    if updated == "deleted":
        tg_channel_data["podcast_count"] -= 1
    elif updated == "created":
        tg_channel_data["podcast_count"] += 1
    storage.set_user_state_data(data['chat_id'], "myTgChannel", tg_channel_data)

    if updated is not False:
        open_channel_subs(data)

    else:
        notify(data['callback'], data['message'],
               get_message("parsingError", data['language_code']), alert=True)


# страница ввода id канала
def channel_input_page(data: ControllerParams):
    db = SQLighter(db_path)
    current_channel_count = db.get_user_tg_channels_count(data['chat_id'])
    db.close()

    if current_channel_count >= maxTgChannelsPerAccount:
        notify(data['callback'], data['message'],
               get_message('maxTgChannelsForNow', data['language_code']), alert=True)

    else:
        # Open the page
        if data['message'] is None:
            channel_input_message = get_input_channel_id_message(data['language_code'])

            render_messages(data['chat_id'], [{'type': 'text', 'text': channel_input_message['message'],
                                               'reply_markup': channel_input_message['markup']}])
            return

        # Process adding
        return channel_save_id(data)


def get_input_channel_id_message(language_code, status=None, channel=None):
    message_text = emojiCodes.get('electricPlug') + "\n"

    if status is not None:
        if status == "alreadyAdded":
            message_text += "\n" + get_message("tgChannelAlreadyAdded", language_code)
        elif status == "notFound":
            message_text += "\n" + get_message(
                "tgChannelNotFoundEnsureBotAdmin", language_code)
        elif status == "error":
            message_text += "\n" + get_message("error", language_code)
        elif status == "maximumAdded":
            message_text += "\n" + get_message("maxTgChannelsForNow", language_code)

        elif status == "added":
            message_text += "\n" + get_message("tgChannelAdded", language_code)
            message_text += "\n<b>" + channel.title + "</b>"

    else:
        message_text += get_message("addTgChannelInput", language_code)

    result = {
        "message": message_text,
        "markup": go_back_inline_markup(language_code)
    }
    return result


# Сохранения id канала
def channel_save_id(data: ControllerParams):
    if data['message'] is None:
        return

    if data['message'].fwd_from is not None \
            and hasattr(data['message'].fwd_from, "channel_id") \
            and data['message'].fwd_from.channel_id != 0:

        channel_id = data['message'].fwd_from.channel_id
    else:
        channel_id = data['message'].text

    db = SQLighter(db_path)
    current_channel_count = db.get_user_tg_channels_count(data['chat_id'])
    already_added = db.isTgChannelAlreadyAdded(data['chat_id'], channel_id)
    db.close()

    # уже добавлен
    if already_added:
        channel_input_message = get_input_channel_id_message(data['language_code'], status='alreadyAdded')

    elif current_channel_count >= maxTgChannelsPerAccount:
        channel_input_message = get_input_channel_id_message(data['language_code'], status='maximumAdded')

    else:

        try:
            channel = bot.get_chat(channel_id)
        except Exception as e:
            channel = None

        # канал не найден
        if channel is None:
            channel_input_message = get_input_channel_id_message(data['language_code'], 'notFound')

        else:

            db = SQLighter(db_path)
            db.addOrUpdateTgChannel(data['chat_id'], channel_id)
            added = db.isTgChannelAlreadyAdded(data['chat_id'], channel_id)
            db.close()

            if added:
                channel_input_message = get_input_channel_id_message(data['language_code'], 'added', channel)

            # не получилось добавить
            else:
                channel_input_message = get_input_channel_id_message(data['language_code'], 'error')

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': channel_input_message['message'], 'reply_markup': channel_input_message['markup']}])


# !!!!!!!!!!!!!!!!!!!!!!!!!
# Вспомогательные функции
# !!!!!!!!!!!!!!!!!!!!!!!!!

def bot_removed_from_channel_reaction(e, tgChannelId):
    if "bot is not a member of the channel" in str(e) \
            or "need administrator rights in the channel" in str(e) \
            or "bot was kicked from the channel" in str(e) \
            or "Could not find the input entity for PeerChannel" in str(e):

        db_users = SQLighter(db_path)
        user_tg_id = db_users.getUserTgIdByChannelTg(tgChannelId)
        channel = db_users.getTgChannelDataByTgId(user_tg_id, tgChannelId)
        if channel is not None and channel['active']:
            db_users.addOrUpdateTgChannel(user_tg_id, tgChannelId, False)
            owner = db_users.get_user_by_tg(user_tg_id)
        else:
            owner = None
        db_users.close()

        if channel is not None and channel['active']:

            try:
                tg_channel = bot.get_chat(tgChannelId)
                title = tg_channel.title
            except Exception:
                title = str(tgChannelId)

            if owner is not None:
                language_code = app.service.user.language.user_language(owner['lang'])
            else:
                language_code = None

            render_messages(user_tg_id, [{
                'type': 'text',
                'text': get_message('tgChannelNotFoundEnsureBotAdminWithName', language_code) % title
            }], resending=True)

        return True

    else:
        return False
