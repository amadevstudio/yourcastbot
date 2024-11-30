import json
import math

from telebot import types

from app.controller.general.notify import notify
import lib.markup.cleaner
from app.core.message.navigationBuilder import determine_search_query_and_page, get_full_message_navigation, \
    FullMessageNavigation
from lib.telegram.general.message_master import message_master, render_messages, InlineButtonData
from app.i18n.messages import get_message, get_message_rtd
from app.repository.storage import storage
from config import db_path
from db.sqliteAdapter import SQLighter
from app.routes.ptypes import Message, Callback, ControllerParams
from lib.tools.logger import logger

PER_PAGE = 5


def show_genres(data: ControllerParams):
    current_state_data = determine_search_query_and_page(data['callback'], data['message'], data['united_data'])

    search_query = current_state_data.get('search', None)

    db_users = SQLighter(db_path)
    message_navigation = get_full_message_navigation(
        current_state_data.get('p', None), search_query,
        db_users.select_genres,
        [data['language_code'], data['united_data'].get('lngTp', False), search_query],
        db_users.select_genres_count,
        [data['language_code'], data['united_data'].get('lngTp', False), search_query],
        PER_PAGE, None,
        data['language_code'], 'topGnrs', back_button_text='goBackMenu')
    db_users.close()

    if 'error' in message_navigation['page_data']:
        logger.warn('Top error in message navigation', message_navigation['page_data']['error'])
        error_message = get_message_rtd(['errors', 'unknown'], data['language_code'])
        notify(data['callback'], data['message'], text=error_message, resending=True)
        return False

    result = construct_genres_message(message_navigation, data['language_code'],
                                      data['united_data'].get('lngTp', False))

    render_messages(data['chat_id'], result)

    storage.set_user_state_data(
        data['chat_id'], 'topGnrs',
        {**current_state_data, 'p': message_navigation['page_data']['current_page']})


def construct_genres_message(message_navigation: FullMessageNavigation, language_code: str, language_top: bool):
    text = get_message('genresMessage', language_code) % get_message(
        ('podcastTopLang' if language_top else 'podcastTop'), language_code)

    genres_keyboard: list[list[InlineButtonData]] = []

    # общий топ
    if message_navigation['page_data']['current_page'] == 1:
        genres_keyboard.append([{'text': get_message("generalTop", language_code),
                                 'callback_data': {'tp': 'top_ch', 'id': None, 'p': 1}}])

    for genre in message_navigation['page_data']['data']:
        genres_keyboard.append([{
            'text': lib.markup.cleaner.html_mrkd_cleaner(
                get_message_rtd(["genres", genre['name']], language_code)
                .encode('utf-8').capitalize().decode('utf-8')),
            'callback_data': {'tp': 'top_ch', 'id': genre['id'], 'p': 1}}])

    if message_navigation['nav_layout_parts'] is not None:
        if message_navigation['nav_layout_parts'].get('exit_search_mode_row', None) is not None:
            genres_keyboard += [message_navigation['nav_layout_parts']['exit_search_mode_row']]
        genres_keyboard += [message_navigation['nav_layout_parts']['navigation_row']]

    return [{
        'type': 'text',
        'text': text + "\n" + message_navigation['routing_helper_message'],
        'reply_markup': genres_keyboard
    }]


def show_top(data: ControllerParams):
    genre_data = storage.get_user_state_data(data['chat_id'], 'topGnrs')
    lang_top = genre_data is not None and 'lngTp' in genre_data and genre_data['lngTp']

    current_state_data = determine_search_query_and_page(data['callback'], data['message'], data['united_data'])
    genre_id = current_state_data.get('id', None)

    search_query = current_state_data.get('search', None)

    db_users = SQLighter(db_path)
    message_navigation = get_full_message_navigation(
        current_state_data.get('p', None), search_query,
        db_users.select_top,
        [genre_id, data['language_code'], lang_top, search_query],
        db_users.select_top_count,
        [genre_id, data['language_code'], lang_top, search_query],
        PER_PAGE, None,
        data['language_code'], 'top_ch', back_button_text='goBackMenu')

    if genre_data is None or genre_id is None:
        genre_name = get_message('generalTop', data['language_code'])
    else:
        genre_name = db_users.get_genre(genre_id)['name']
    db_users.close()

    if 'error' in message_navigation['page_data']:
        logger.warn('Top error in message navigation', message_navigation['page_data']['error'])
        if message_navigation['page_data']['error'] == 'empty':
            error_message = get_message_rtd(['search', 'empty'], data['language_code'])
        else:
            error_message = get_message_rtd(['errors', 'unknown'], data['language_code'])
        notify(data['callback'], data['message'], text=error_message, resending=True)
        return False

    result = construct_top_message(message_navigation, data['language_code'], lang_top, genre_name)

    render_messages(data['chat_id'], result)

    storage.set_user_state_data(
        data['chat_id'], 'top_ch',
        {**current_state_data, 'p': message_navigation['page_data']['current_page']})


def construct_top_message(message_navigation: FullMessageNavigation, language_code: str, language_top: bool,
                          genre_name: str):
    text = get_message('genresMessage', language_code) % get_message(
        ('podcastTopLang' if language_top else 'podcastTop'), language_code)
    text += ' <b>' + get_message_rtd(["genres", genre_name], language_code) + '</b>'

    tops_keyboard: list[list[InlineButtonData]] = []

    for podcast in message_navigation['page_data']['data']:
        tops_keyboard.append([{
            'text': lib.markup.cleaner.html_mrkd_cleaner(podcast['name'])
                    + f" {podcast['rate']} ({podcast['rates_count']})",
            'callback_data': {'tp': 'podcast', 'id': podcast['id']}
        }])

    if message_navigation['nav_layout_parts'] is not None:
        if message_navigation['nav_layout_parts'].get('exit_search_mode_row', None) is not None:
            tops_keyboard += [message_navigation['nav_layout_parts']['exit_search_mode_row']]
        tops_keyboard += [message_navigation['nav_layout_parts']['navigation_row']]

    return [{
        'type': 'text',
        'text': text + "\n" + message_navigation['routing_helper_message'],
        'reply_markup': tops_keyboard
    }]
