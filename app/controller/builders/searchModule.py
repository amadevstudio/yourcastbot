# -*- coding: utf-8 -*-
# import telebot
# from telebot import apihelper
import json
import re
import typing
from hashlib import sha256
from typing import TypedDict

import requests
from telebot import types

import app.i18n.messages
import app.service.podcast.podcast
import app.service.record.helpers
import app.service.user.language
import lib.markup.cleaner
from agent.bot_telebot import bot
from app.controller.builders.podcastModule import (
    filter_genre, channel_query)
from app.controller.builders.recsModule import load_records_data
from app.controller.general.notify import notify
from app.core.message.navigationBuilder import get_full_message_navigation, FullMessageNavigation, \
    determine_search_query_and_page
from app.core.sender.send_record_helper import Sender, transform_duration, get_file_size_HTTP
from app.i18n.messages import get_message, emojiCodes, get_message_rtd
from app.repository.storage import storage, telegram_cache
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import ControllerParams, InlineControllerParams
from app.routes.routes_list import AvailableRoutes
from config import (
    db_path, available_podcast_hoster_links, botName, server, maxPodcastDateCallDataHexLen,
    apple_itunes_search)
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import render_messages, MessageStructuresInterface, \
    InlineButtonData
from lib.tools.logger import logger

PER_PAGE = 5


def search(data: ControllerParams):
    current_state_data = determine_search_query_and_page(
        data['callback'], data['message'], data['united_data'], numbers_are_pages=False)
    search_query = current_state_data.get('search', None)

    if search_query is None:
        render_messages(data['chat_id'], [{
            'type': 'text',
            'text': get_message("searchAdv", data['language_code']),
            'reply_markup': go_back_inline_markup(data['language_code'])
        }])
        return

    try:
        message_navigation = get_full_message_navigation(
            current_state_data['p'], search_query,
            make_search, [search_query], None, None, PER_PAGE,
            [{'have_new_episodes': 'DESC'}, 'channels.name'],
            data['language_code'], typing.cast(AvailableRoutes, data['route_name']),
            back_button_text='goBackMenu', order_builder=None, with_pro_tip=False, with_exit_search_button=False)
    except Exception as e:
        logger.err(e)
        notify(data['callback'], data['message'], text=get_message('parsingError', data['language_code']))
        return False

    if 'error' in message_navigation['page_data']:
        if message_navigation['page_data']['error'] == 'empty':
            error_message = get_message('searchResultsNotFound', data['language_code'])
        else:
            error_message = get_message_rtd(['errors', 'unknown'], data['language_code'])
        notify(data['callback'], data['message'], text=error_message, resending=True)
        return False

    search_msg = construct_search_message(message_navigation, data['language_code'])

    render_messages(data['chat_id'], search_msg, resending=data['is_command'])

    storage.set_user_state_data(data['chat_id'], data['route_name'],
                                {**current_state_data, 'p': message_navigation['page_data']['current_page']})


class SearchResult(TypedDict):
    title: str
    collectionId: str
    trackCount: int
    lastDate: str


def make_search(message_text: str, _, per_page: int = PER_PAGE, offset: int = 0) \
        -> TypedDict('MakeSearch', {'results': list[SearchResult], 'count': int}):
    cache_key = f'itunes/search/{message_text}'
    cached_result = telegram_cache.get_cached(cache_key)

    if cached_result is None:
        payload = {'media': 'podcast', 'term': message_text}
        response = requests.get(apple_itunes_search, params=payload)

        result = json.loads(response.content.decode('utf-8'))
        telegram_cache.add_cache(cache_key, result)
    else:
        result = cached_result

    podcast_results = []

    item_counter = 0
    per_page_limit = 0
    for item in result["results"]:
        item_counter += 1

        # if "feedUrl" in result:
        if item_counter <= offset:
            continue

        podcast_results.append({
            'title': item['collectionName'],
            'collectionId': item['collectionId'],
            'trackCount': item['trackCount'],
            'lastDate': app.service.podcast.podcast.prepare_podcast_update_time(item['releaseDate'])
        })

        per_page_limit += 1
        if per_page_limit == per_page:
            break

    return {'results': podcast_results, 'count': result['resultCount']}


def construct_search_message(message_navigation: FullMessageNavigation, language_code: str) \
        -> list[MessageStructuresInterface]:
    res_keyboard: list[list[InlineButtonData]] = []
    disk_emoji = emojiCodes.get('disk')

    res: SearchResult
    for res in message_navigation['page_data']['data']:
        res_keyboard.append([
            {'text': f"{res['title']} – {res['trackCount']} {disk_emoji} {res['lastDate']}",
             'callback_data': {'tp': 'podcast', 'sId': res['collectionId']}}
        ])

    if message_navigation['page_data']['page_count'] is not None and message_navigation['page_data']['page_count'] > 1:
        res_keyboard += [[{
            'text': get_message('page', language_code) + ' 1',
            'callback_data': {'tp': 'search', 'p': 1}
        }, {
            'text': f"{get_message('page', language_code)} {message_navigation['page_data']['page_count']}",
            'callback_data': {'tp': 'search', 'p': message_navigation['page_data']['page_count']}
        }]]

    if message_navigation['nav_layout_parts'] is not None:
        if message_navigation['nav_layout_parts'].get('exit_search_mode_row', None) is not None:
            res_keyboard += [message_navigation['nav_layout_parts']['exit_search_mode_row']]
        res_keyboard += [message_navigation['nav_layout_parts']['navigation_row']]

    return [{
        'type': 'text',
        'text': get_message("searchResults", language_code) + "\n"
                + message_navigation['routing_helper_message'],
        'reply_markup': res_keyboard
    }]


# !!!!!!!!!!!!!!!!!!!!!!!!!!
# добавление подкаста по rss
def open_adding_by_rss_page(data: ControllerParams):
    rrs_page_message = construct_adding_by_rss_page(data['language_code'])

    render_messages(data['chat_id'], [{
        'type': 'text', 'text': rrs_page_message['message'], 'reply_markup': rrs_page_message['markup']}])


def construct_adding_by_rss_page(language_code):
    message = get_message("addingByRssMessage", language_code)
    for hosterLink in available_podcast_hoster_links:
        message += "\n\U00002022 " + hosterLink  # точка bullet

    return {
        "message": message,
        "markup": go_back_inline_markup(language_code)
    }


def show_adding_rss_result(data: ControllerParams):
    if data['message'] is None:
        notify(data['callback'], data['message'], get_message_rtd(['errors', 'unknown'], data['language_code']))
        return False

    link_testers = []
    for host_link in available_podcast_hoster_links:
        prepared_host_link = r'%s' % "\\.".join(host_link.split('.'))
        link_testers.append(
            re.compile(r'https?:\/\/((?:[a-z0-9_-]+\.)*%s\/.*)' % prepared_host_link))

    reg_result = None
    for link_tester in link_testers:
        # regResult = linkTester.fullmatch(message.text)
        reg_result = link_tester.match(data['message'].text)
        if reg_result is not None:
            break

    # строка не удовлетворяет регулярке
    if reg_result is None or len(reg_result.groups()) != 1:
        render_messages(data['chat_id'], [{
            'type': 'text', 'text': get_message("wrongUrl", data['language_code']),
            'reply_markup': go_back_inline_markup(data['language_code'])
        }])
        return

    # render_messages(data['chat_id'], [{
    #     'type': 'text', 'text': get_message('loading', data['language_code'])}])

    # проверка, существует ли подкаст
    rss_link = "http://%s" % reg_result.group(1)

    # db_users = SQLighter(db_path)
    # # channel = db_users.get_channel_by_service(regResult.string, 'rss')
    # channel = db_users.get_channel_by_service(rss_link, 'rss')
    # channel_id = (channel["id"] if (channel is not None) else None)
    # db_users.close()
    #
    # podcast_exist, podcast_data = get_and_set_podcast_data(
    #     data['chat_id'], rss_link, channel_id, 'rss')
    #
    # # если не удалось получить, то сообщить об этом и выйти
    # if not podcast_exist:
    #     cant_find_response = cant_find_podcast(data['chat_id'], channel_id, data['language_code'])
    #     # TODO Remove pc_unavailable
    #     storage.set_user_state_data(
    #         data['chat_id'], 'podcast',
    #         {'id': channel_id, 'title': '', 'unavailable': True})
    #     render_messages(data['chat_id'], cant_find_response)
    #     return
    #
    # ch_msg = construct_channel_message(data['chat_id'], data['language_code'], podcast_data)
    #
    # render_messages(data['chat_id'], ch_msg)

    podcast_route_name: AvailableRoutes = 'podcast'
    data['route_name'] = podcast_route_name
    data['message'].text = json.dumps({'sId': rss_link, 'sName': 'rss'})
    channel_query(data)

    # Don't show error messages when goback from podcast
    if storage.get_user_curr_state(data['chat_id']) == 'addBRss':
        storage.del_user_curr_state(data['chat_id'])
    storage.add_user_state(data['chat_id'], 'podcast')
    return False


def inline_podcast_searcher(data: InlineControllerParams):
    inline_query = data['inline']
    splitter = " / "
    max_results = 50

    query = inline_query.query
    record_query = None

    if splitter in query:
        query, record_query = query.split(splitter, 1)

    api_url_base = apple_itunes_search
    payload = {'media': 'podcast', 'term': query}
    response = requests.get(api_url_base, params=payload)

    try:
        result = json.loads(response.content.decode('utf-8'))
    except Exception:
        # TODO
        # print error
        # answer inline
        return

    founded_count = int(result['resultCount'])
    founded_count = max_results if founded_count > max_results else founded_count

    inline_buttons = []

    if founded_count == 0:
        return

    db = SQLighter(db_path)
    user = db.get_user_by_tg(inline_query.user_id)
    if user is not None:
        language_code = app.service.user.language.user_language(user['lang'])
    else:
        language_code = "en"
    db.close()

    # def get_rss_data(collection_id, rss_datas, index):
    # 	podcastExists, podcastRssData = podcastModule.getPodcastData(None, collection_id)
    # 	if podcastExists:
    # 		rss_datas[index] = podcastRssData

    # ответ с подкастами
    if record_query is None or record_query == "":
        db = SQLighter(db_path)
        podcasts = []
        # rss_datas = [None] * founded_count
        # threads = [None] * founded_count
        for i in range(founded_count):
            podcast_data = result['results'][i]
            podcast = db.get_channel_by_service(podcast_data['collectionId'], 'itunes')
            podcasts.append({'podcast': podcast, 'podcastData': podcast_data})
        db.close()

        # # Too long to load all rss data
        # 	threads[i] = Thread(target=get_rss_data, args=(podcastData['collectionId'], rss_datas, i))
        # 	threads[i].start()
        # for i in range(founded_count):
        # 	threads[i].join()

        for i in range(founded_count):
            button = construct_inline_podcast_searcher_channel(
                # podcasts[i]['podcast'], podcasts[i]['podcastData'], rss_datas[i], language_code)
                podcasts[i]['podcast'], podcasts[i]['podcastData'], None, language_code)
            inline_buttons.append(button)

    # ответ с аудиовыпусками
    else:
        podcast_data = result['results'][0]

        try:
            page = int(record_query)
        except Exception:
            page = None

        payload = {'entity': 'podcast', 'id': podcast_data['collectionId']}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload)

        if root is False:
            return

        # Getting records info
        if page is None:
            rd = load_records_data(root, search_query=record_query, take_file_links=True)
        else:
            rd = load_records_data(root, curr_page=page, take_file_links=True)

        founded_count = len(rd['title'])
        founded_count = max_results if founded_count > max_results else founded_count
        inline_buttons = construct_inline_podcast_searcher_records(podcast_data, rd, founded_count, language_code)

    try:
        bot.answer_inline_query(
            inline_query.id, inline_buttons,
            cache_time=(300 if server else 1))
    except Exception as e:
        logger.err(e)


def construct_inline_podcast_searcher_channel(podcast, podcast_data, rss_podcast_data, language_code):
    inline_id = f"itunes_{podcast_data['collectionId']}"

    last_update = app.service.podcast.podcast.prepare_podcast_update_time(podcast_data['releaseDate'])

    message_text_content = lib.markup.cleaner.html_mrkd_cleaner(f"*{podcast_data['collectionName']}*\n")
    if rss_podcast_data is not None and rss_podcast_data['channelLink']:
        message_text_content += rss_podcast_data['channelLink'] + "\n"
    else:
        message_text_content += f"[Apple Podcasts]({podcast_data['collectionViewUrl']})\n"
    message_text_content += get_message("lastUpdate", language_code) + " " \
                            + last_update + "\n\n"

    # получение картинок
    thumb_url = None
    itunes_artwork_size_keys = [
        # 'artworkUrl30', 'artworkUrl60',
        'artworkUrl100', 'artworkUrl600']
    for sizeKey in itunes_artwork_size_keys:
        if sizeKey in podcast_data:
            if thumb_url is None:
                thumb_url = podcast_data[sizeKey]
            photo_url = podcast_data[sizeKey]

    # получение ссылки на подкаст
    if podcast is not None:
        url = f"t.me/{botName}?start=podcast_{podcast['id']}"
        message_text_content += get_message(
            "linkInTheBotByPodcastId", language_code).format(
            botName=botName, id=podcast['id'], mode="podcast")
    else:
        url = f"t.me/{botName}?start=podcastItunes_{podcast_data['collectionId']}"
        message_text_content += get_message(
            "linkInTheBotByPodcastId", language_code).format(
            botName=botName, id=podcast_data['collectionId'], mode="podcastItunes")
    message_text_content += "\n\n"

    description = f"{podcast_data['trackCount']} {emojiCodes.get('disk')}" \
                  + " " + last_update

    genres_str = ""
    # получение жанров
    if 'genres' in podcast_data:
        if 'primaryGenreName' in podcast_data:
            primary_genre_name = podcast_data['primaryGenreName']
        else:
            primary_genre_name = ''
        for genre in podcast_data['genres']:
            genre = filter_genre(genre)
            if genre is not None:
                if genres_str != "":
                    genres_str += ", "
                genre_localized_name = get_message_rtd(
                    ["genres", genre], language_code)
                if primary_genre_name == genre:
                    genres_str = genres_str + f"*{genre_localized_name}*"
                else:
                    genres_str = genres_str + genre_localized_name
    if genres_str != "":
        message_text_content += lib.markup.cleaner.html_mrkd_cleaner(genres_str)

    # заголовок inline результатов
    title = lib.markup.cleaner.html_mrkd_cleaner(podcast_data['collectionName'])
    # body inline результатов
    description = lib.markup.cleaner.html_mrkd_cleaner(description)
    # сообщение, которое отправляется при нажатии
    # message_text_content

    # создание кнопок
    inline_channel_actions = types.InlineKeyboardMarkup()
    inline_channel_actions.row(types.InlineKeyboardButton(
        text=get_message("openThePodcast", language_code),
        url=url))

    button = types.InlineQueryResultArticle(
        id=inline_id, title=title,
        url=url, description=description,
        thumbnail_url=thumb_url, reply_markup=inline_channel_actions,
        input_message_content=types.InputTextMessageContent(
            message_text=message_text_content, parse_mode="Markdown"))

    return button


def construct_inline_podcast_searcher_records(podcast_data, rd, founded_count, language_code):
    inline_buttons = []

    db = SQLighter(db_path)
    channel = db.get_channel_by_service(podcast_data['collectionId'], 'itunes')
    db.close()

    for i in range(founded_count):
        pgd = app.service.record.helpers.get_record_uniq_id(rd['guids'][i], rd['pubDates'][i], rd['title'][i])
        inline_id = sha256(
            f"itunes_{podcast_data['collectionId']}_{pgd}".encode('utf-8')
        ).hexdigest()[:64]

        # lastUpdate = app.service.podcast.podcast.prepare_podcast_update_time(podcastData['releaseDate'])

        duration_sec = transform_duration(rd['durations'][i])

        # создание кнопок
        inline_channel_actions = types.InlineKeyboardMarkup()

        try:
            record_size = get_file_size_HTTP(rd['links'][i]) / 1048576  # 1024 * 1024
        except Exception:
            record_size = 51

        # можно отправить через bot api
        if record_size < 20:

            # для записи прикрепляем кнопку открыть подкаст в боте
            if channel is not None:
                open_podcast_url = f"t.me/{botName}?start=podcast_{channel['id']}"
            else:
                open_podcast_url = f"t.me/{botName}?start=podcastItunes_{podcast_data['collectionId']}"
            inline_channel_actions.row(types.InlineKeyboardButton(
                text=get_message("openThePodcast", language_code),
                url=open_podcast_url))

            # генерация текста выпуска — полный текст
            record_message_text = Sender.record_text_template(
                language_code, 'default', rd['channelLink'], rd['chName'],
                rd['title'][i], channel['id'] if channel is not None else None,
                rd['pubDatesFormatted'][i], rd['descrs'][i],
                'itunes', podcast_data['collectionId'], bot_reference_botname=False)

            button = types.InlineQueryResultAudio(
                id=inline_id, audio_url=rd['links'][i],
                title=lib.markup.cleaner.html_mrkd_cleaner(rd['title'][i]),
                caption=record_message_text,
                parse_mode="HTML", performer=rd['chName'], audio_duration=duration_sec,
                reply_markup=inline_channel_actions)

        else:
            # генерация ссылки на скачивание подкаста
            dh = sha256(
                pgd.encode('utf-8')).hexdigest()[0:maxPodcastDateCallDataHexLen]
            download_episode_url = f"t.me/{botName}?start="
            if channel is not None:
                download_episode_url += f"episode_{channel['id']}_{dh}_{rd['rssNumbers'][i]}"
            else:
                download_episode_url += f"episodeItunes_{podcast_data['collectionId']}_{dh}_{rd['rssNumbers'][i]}"

            # генерация текста выпуска — короткий текст
            record_message_text = Sender.record_text_template(
                language_code, 'short', rd['channelLink'], rd['chName'],
                rd['title'][i], channel['id'] if channel is not None else None,
                rd['pubDatesFormatted'][i], rd['descrs'][i],
                'itunes', podcast_data['collectionId'], bot_reference_botname=False)

            # получение картинки
            thumb_url = None
            itunes_artwork_size_keys = [
                # 'artworkUrl30', 'artworkUrl60',
                'artworkUrl100', 'artworkUrl600']
            for sizeKey in itunes_artwork_size_keys:
                if sizeKey in podcast_data:
                    if thumb_url is None:
                        thumb_url = podcast_data[sizeKey]

            description = rd['chName']

            inline_channel_actions.row(types.InlineKeyboardButton(
                text=get_message("downloadEpisode", language_code),
                url=download_episode_url))

            button = types.InlineQueryResultArticle(
                id=inline_id, title=lib.markup.cleaner.html_mrkd_cleaner(rd['title'][i]),
                description=description,
                thumbnail_url=thumb_url, reply_markup=inline_channel_actions,
                input_message_content=types.InputTextMessageContent(
                    message_text=record_message_text, parse_mode="HTML"))

        inline_buttons.append(button)
    return inline_buttons
