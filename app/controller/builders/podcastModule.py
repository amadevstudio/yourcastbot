# -*- coding: utf-8 -*-
# import telebot
# from telebot import apihelper
import copy
import json
import re
import typing
from datetime import datetime
from typing import TypedDict, Literal
from urllib.parse import quote, unquote

from app.controller.general.notify import notify
import app.service.podcast.podcast
import app.service.podcast.subscription
import app.service.record.caption
import lib.markup.cleaner
from app.routes.message_tools import go_back_inline_markup
from lib.telegram.general.message_master import message_master, render_messages, MessageStructuresInterface, \
    message_editor, InlineButtonData
from app.i18n.messages import get_message, get_message_rtd, emojiCodes, standartSymbols
from app.repository.storage import storage
from config import (db_path, noPhoto, botName, max_subscriptions_without_tariff)
from db.sqliteAdapter import SQLighter
from app.routes.ptypes import ControllerParams


class GenresType(TypedDict):
    name: str
    isMain: bool


class PodcastStateData(TypedDict, total=False):
    id: int | None
    service_id: str | None
    service_name: str | None
    title: str
    descr: str
    imgUrl: str
    recCount: int
    lastDate: str
    subscribed: bool
    notify: bool
    rate: int | None
    rating: dict[Literal['value', 'count'], int]
    channelLink: str
    genres: list[GenresType]
    have_new_episodes: bool
    last_user_date: datetime
    last_user_guid: str
    unavailable: bool


def channel_query(data: ControllerParams):
    if data['callback'] is None and data['message'] is not None:
        try:
            call_data = json.loads(data['message'].text)
        except json.decoder.JSONDecodeError:
            call_data = {}
        # открытие по сообщению — это из команды start или добавление по rss, сброс состояния
        storage.del_user_state_data(data['chat_id'], 'podcast')
    else:
        call_data = data['united_data']

    render_messages(data['chat_id'], [{
        'type': 'text',
        'text': get_message('loading', data['language_code']),
    }], resending=data['callback'] is None)

    podcast_exist = True
    podcast_data = None

    service_id = None
    service_name = None

    db_users = SQLighter(db_path)
    # Custom service id
    if "sId" in call_data:
        service_id = call_data["sId"]
        service_name = call_data.get("sName", "itunes")
        channel = db_users.get_channel_by_service(service_id, service_name)
        channel_id = (channel["id"] if (channel is not None) else None)
        bad_data = False
    # Std id
    elif "id" in call_data:
        channel = db_users.get_channel(call_data["id"])
        channel_id = (channel["id"] if (channel is not None) else None)
        bad_data = False
    else:
        channel = None
        bad_data = True
        channel_id = None
    db_users.close()

    # Get channel data
    if not bad_data and \
            storage.get_user_state_data_empty(data['chat_id'], 'podcast'):

        if channel is not None:

            podcast_exist = False
            if channel["itunes_id"] is not None and channel["itunes_id"]:
                podcast_exist, podcast_data = get_and_set_podcast_data(
                    data['chat_id'], channel["itunes_id"], channel_id)
            if (
                    channel["rss_link"] is not None and channel["rss_link"]
                    and not podcast_exist
            ):
                podcast_exist, podcast_data = get_and_set_podcast_data(
                    data['chat_id'], channel["rss_link"], channel_id, 'rss')

        elif "sId" in call_data:
            podcast_exist, podcast_data = get_and_set_podcast_data(
                data['chat_id'], service_id, channel_id, service_name)

    # если не удалось получить, то сообщить об этом и выйти
    if not podcast_exist or bad_data:
        empty_data: PodcastStateData = {'id': channel_id, 'title': '', 'unavailable': True}
        if channel is not None:
            cant_find_response = cant_find_podcast(data['chat_id'], channel_id, data['language_code'])
            empty_data |= {'service_id': channel['itunes_id'], 'service_name': 'itunes'}
        elif "sId" in call_data:
            cant_find_response = cant_find_podcast(data['chat_id'], channel_id, data['language_code'])
            empty_data |= {'service_id': service_id, 'service_name': service_name}
        else:
            cant_find_response = cant_find_podcast(data['chat_id'], None, data['language_code'])
            empty_data |= {'service_id': None, 'service_name': 'itunes'}
        storage.set_user_state_data(data['chat_id'], 'podcast', empty_data)
        render_messages(data['chat_id'], cant_find_response)
        return

    ch_msg = construct_channel_message(data['chat_id'], data['language_code'], podcast_data)

    try:
        render_messages(data['chat_id'], ch_msg)
    except Exception as e:
        # If telegram can't send podcast image
        if "Bad Request: wrong file identifier/HTTP URL specified" in str(e):
            ch_msg_without_image: list[MessageStructuresInterface] = [{
                'type': 'text',
                'text': ch_msg[0]['text'],
                'disable_web_page_preview': True,
                'reply_markup': ch_msg[1]['reply_markup']
            }]
            render_messages(data['chat_id'], ch_msg_without_image)

        else:
            raise e


def get_and_set_podcast_data(
        chat_id, service_id, podcast_id=None, service_name='itunes') -> tuple[bool, PodcastStateData | None]:
    podcast_exists, podcast_data = get_podcast_data(chat_id, service_id, podcast_id, service_name)

    if not podcast_exists:
        return False, None

    set_podcast_data(chat_id, podcast_data)

    return podcast_exists, podcast_data


def get_podcast_data(chat_id, service_id, podcast_id=None, service_name='itunes') \
        -> tuple[bool, PodcastStateData | None]:
    if service_name == 'itunes':
        payload = {'entity': 'podcast', 'id': service_id}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload)
    elif service_name == 'rss':
        payload = {'rss_link': service_id}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload, 'rss', direct_link=True)
    else:
        root = False
        pc_info = None

    if root is False:
        return False, None

    last_date = pc_info["lastDate"]

    im_url = None
    itunes_im_url = ""
    title = ""
    descr = ""
    channel_link = ""

    checked_first_record_date = False
    last_pub_date = None
    # lastGuid = ""
    # lastRecordTitle = ""

    rec_count = 0
    for channel_descr in root.getchildren():
        if channel_descr.tag == "title":
            title = str(channel_descr.text)

        # получение lastDate из RSS в формате itunes
        elif channel_descr.tag in ["lastBuildDate", "pubDate"] and last_date is None:
            last_date = str(channel_descr.text)

        elif channel_descr.tag == "description":
            try:
                descr = str(channel_descr.text)
            except Exception:
                descr = channel_descr.text

        elif channel_descr.tag == "image":
            for imBlockParam in channel_descr.getchildren():
                if imBlockParam.tag == "url":
                    im_url = imBlockParam.text
                elif imBlockParam.tag == "link" and im_url is None:
                    im_url = imBlockParam.text

        elif channel_descr.tag in [
            "{http://www.itunes.com/dtds/podcast-1.0.dtd}image", "itunes:image"]:
            try:
                itunes_im_url = channel_descr.attrib["href"]
            except Exception:
                itunes_im_url = noPhoto

        elif channel_descr.tag == "item":
            rec_count += 1
            if not checked_first_record_date:
                for record in channel_descr.getchildren():
                    if record.tag == "pubDate":
                        checked_first_record_date = True
                        last_pub_date = app.service.podcast.podcast.prepare_string_from_rss(str(record.text))
                # elif record.tag == "guid":
                # 	lastGuid = str(record.text)
                # elif record.tag == "title":
                # 	lastRecordTitle = str(record.text)

        elif channel_descr.tag == "link":
            try:
                channel_link = quote(channel_descr.text, safe=":/?=")
            except Exception:
                channel_link = channel_descr.text
    # imUrl = json.loads(
    # 	response.content.decode('utf-8'))["results"][0]["artworkUrl600"]

    if descr is None or descr == "None":
        descr = ""

    if im_url == "" or im_url is None:
        if itunes_im_url != "":
            im_url = unquote(itunes_im_url)
        else:
            im_url = noPhoto
    else:
        im_url = unquote(im_url)

    podcast_genres: list[GenresType] = []
    if pc_info['itunesData'] is not None and 'genres' in pc_info['itunesData']:
        if 'primaryGenreName' in pc_info['itunesData']:
            primary_genre_name = pc_info['itunesData']['primaryGenreName']
        else:
            primary_genre_name = ''
        for genre in pc_info['itunesData']['genres']:
            genre = filter_genre(genre)
            if genre is not None:
                podcast_genres.append({
                    'name': genre,
                    'isMain': primary_genre_name == genre
                })

    db_users = SQLighter(db_path)

    # subscribed = db_users.check_subscription(chId, itunes_id)
    # notify = db_users.check_notify(chId, itunes_id)
    db_users.complete_itunes_data(podcast_id, pc_info['feedUrl'], service_id, service_name)

    if chat_id is not None:
        user_related_info = db_users.get_user_related_podcast_info(chat_id, podcast_id)
    else:
        user_related_info = db_users.get_user_related_podcast_info(None, None)

    subscribed = user_related_info['subscribed']
    notify = user_related_info['notify']
    user_rate = user_related_info['rate']
    rating = user_related_info['rating']
    have_new_episodes = user_related_info['have_new_episodes']
    last_user_date = user_related_info['last_date']
    last_user_guid = user_related_info['last_guid']

    db_users.catchGenres(podcast_id, podcast_genres)

    db_users.close()

    # не всегда в rss присутствует lastBuildDate
    if last_pub_date is not None:
        last_date = app.service.podcast.podcast.set_last_date(last_date, last_pub_date)

    podcast_data: PodcastStateData = {
        "id": podcast_id, "service_id": service_id, "service_name": service_name,
        "title": title, "descr": descr, "imgUrl": im_url, "recCount": rec_count,
        "lastDate": last_date, "subscribed": subscribed, "notify": notify,
        'rate': user_rate, "rating": rating, "channelLink": channel_link,
        "genres": podcast_genres, "have_new_episodes": have_new_episodes,
        "last_user_date": last_user_date, "last_user_guid": last_user_guid}

    return True, podcast_data


def set_podcast_data(chat_id, podcast_data):
    storage.set_user_state_data(
        chat_id, 'podcast', podcast_data)
    storage.del_user_state_data(chat_id, "recs")


def filter_genre(genre):
    genre = genre.strip()
    if genre.lower() in ['', 'podcast', 'podcasts']:
        return None
    else:
        return genre


def cant_find_podcast(
        chat_id, channel_id, language_code) -> list[MessageStructuresInterface]:
    markup = go_back_inline_markup(language_code)

    if channel_id is not None:
        db_users = SQLighter(db_path)
        if db_users.check_subscription(chat_id, channel_id):
            markup[0].insert(0, {
                'text': get_message('unsubscribe', language_code), 'callback_data': {'tp': 'subscription'}})
        db_users.close()

    return [{
        'type': 'text',
        'text': get_message('podcastDoesNotExist', language_code),
        'reply_markup': markup
    }]


def construct_channel_message(chat_id, language_code, channel_data=None) -> list[MessageStructuresInterface]:
    if channel_data is None:
        channel_data = storage.get_user_state_data(chat_id, 'podcast')

    is_notify = None
    try:
        if "subscribed" in channel_data and channel_data["subscribed"]:
            follow_b_text = "unsubscribe"
            if "notify" in channel_data and channel_data["notify"]:
                is_notify = True
            else:
                is_notify = False
        else:
            follow_b_text = "subscribe"
    except Exception:
        follow_b_text = "subscribe"

    channel_actions: list[list[InlineButtonData]] = []

    if (
            (
                    "subscribed" in channel_data
                    and channel_data["subscribed"])
            and (
            "service_name" in channel_data
            and channel_data['service_name'] == 'itunes')
    ):

        rating_emojis = [
            emojiCodes['brokenHeart'], emojiCodes['shootingStar'],
            emojiCodes['dizzy'], emojiCodes['star'], emojiCodes['glowingStar']]
        user_rate_row: list[InlineButtonData] = []
        for i in range(1, 6):
            button_text = f"{i}"
            # показать весь рейтинг, если нет оценки, иначе только оценку
            if (
                    'rate' not in channel_data or not channel_data['rate']
                    or channel_data['rate'] == i
            ):
                button_text += " " + rating_emojis[i - 1]

            if channel_data.get('rate', None) == i:
                btn = {'text': button_text, 'callback_data': {'tp': 'rate', 'rate': None}}
            else:
                btn = {'text': button_text, 'callback_data': {'tp': 'rate', 'rate': i}}

            user_rate_row.append(btn)
        channel_actions.append(user_rate_row)

    if follow_b_text == "subscribe":
        button1 = {'text': get_message("subscribe", language_code), 'callback_data': {'tp': 'subscription'}}
    else:
        button1 = {'text': get_message("unsubscribe", language_code), 'callback_data': {'tp': 'subscription'}}
    back_data = {"tp": "recs", "p": 1}
    new_eps = standartSymbols.get("newItem", "") + " " \
        if "have_new_episodes" in channel_data and channel_data["have_new_episodes"] \
        else ""
    button2 = {'text': new_eps + get_message("listen", language_code), 'callback_data': back_data}
    channel_actions.append([button1, button2])

    if "subscribed" in channel_data and channel_data["subscribed"]:
        # subscribed
        if is_notify:
            button1 = {'text': get_message("notifyoff", language_code),
                       'callback_data': {'tp': 'notifications'}}
        else:
            button1 = {'text': get_message("notifyon", language_code),
                       'callback_data': {'tp': 'notifications'}}
        button2 = {'text': get_message("goBack", language_code), 'callback_data': {"tp": "bck"}}
        channel_actions.append([button1, button2])
    else:
        button2 = {'text': get_message("goBack", language_code), 'callback_data': {"tp": "bck"}}
        # channelActions.add(button1, button2)
        channel_actions.append([button2])

    try:
        title = channel_data["title"]
    except Exception:
        title = ""

    try:
        last_date = channel_data["lastDate"]
    except Exception:
        last_date = ""

    genres_str = ""
    if "genres" in channel_data:
        for genre in channel_data["genres"]:
            if genres_str != "":
                genres_str += ", "
            genre_localized_name = get_message_rtd(
                ["genres", genre['name']], language_code)
            if genre['isMain']:
                genres_str = genres_str + f"<b>{genre_localized_name}</b>"
            else:
                genres_str = genres_str + genre_localized_name

    try:
        descr = channel_data["descr"]
    except Exception:
        descr = ""

    try:
        channel_link = channel_data["channelLink"]
    except Exception:
        channel_link = ""

    if title is None or not title:
        title = ''
    if last_date is None or not last_date:
        last_date = ''
    if descr is None or not descr:
        descr = ''

    title = lib.markup.cleaner.html_mrkd_cleaner(title)
    last_date = lib.markup.cleaner.html_mrkd_cleaner(last_date)
    descr = lib.markup.cleaner.html_mrkd_cleaner(descr)

    message_text = "<b>" + title + "</b>" + "\n"
    if channel_link:
        message_text += lib.markup.cleaner.un_markdown_link(channel_link) + "\n"
    if last_date:
        message_text += get_message("lastUpdate", language_code) + " " + \
                        app.service.podcast.podcast.prepare_podcast_update_time(last_date) + "\n\n"

    # ссылка на бота + ссылка на подкаст в боте
    channel_id: None | int
    if channel_data.get('id', None) is not None:
        channel_id = int(channel_data['id'])
        if channel_id is not None and channel_id < 1:
            channel_id = None
    else:
        channel_id = None
    if channel_id is not None:
        message_text += get_message("linkInTheBotByPodcastId_HTML", language_code).format(
            botName=botName, id=channel_id, mode="podcast")
        message_text += " " + get_message("in_the_bot", language_code).format(botName=botName)
    elif channel_data.get('service_name', None) == "itunes" \
            and channel_data['service_id']:
        message_text += get_message("linkInTheBotByPodcastId_HTML", language_code).format(
            botName=botName, id=channel_data['service_id'], mode="podcastItunes")
        message_text += " " + get_message("in_the_bot", language_code).format(botName=botName)
    else:
        message_text += f"@{botName}"
    message_text += "\n\n"

    if genres_str or 'rating' in channel_data:
        if genres_str:
            message_text += genres_str + "\n"
        if 'rating' in channel_data and channel_data['rating']['value']:
            rating = round(float(channel_data['rating']['value']), 1)
            rating = rating if int(rating) != rating else int(rating)
            message_text += emojiCodes['trophy'] + " " + f"{rating}/5 ({channel_data['rating']['count']})\n"
        message_text += "\n"

    message_text += descr

    if channel_data is not None:
        image = channel_data.get('imgUrl', noPhoto)
    else:
        image = None

    return [{
        'type': 'text',
        'text': message_text,
        'disable_web_page_preview': True
    }, {
        'type': 'image',
        'image': image,
        'reply_markup': channel_actions
    }]


def switch_subscription(data: ControllerParams):
    if data['united_data'] is None or data['callback'] is None:
        notify(
            data['callback'], data['message'], get_message("parsingError", data['language_code']), alert=True)
        return False

    if 'subscribed' in data['united_data']:
        action = not data['united_data'].get('subscribed')
    else:
        db_users = SQLighter(db_path)
        user_related_info = db_users.get_user_related_podcast_info(
            data['chat_id'], data['united_data'].get('id', None))
        action = not user_related_info['subscribed']
        db_users.close()

    updated_state_data: PodcastStateData = (copy.deepcopy(data['united_data'])
                                            | {'subscribed': action})

    # ограничение подписок
    db_users = SQLighter(db_path)
    subs_count = db_users.get_uccs_count_by_tg(data['chat_id'])
    subscription = db_users.getUserSubscriptionByTg(data['chat_id'])
    db_users.close()

    # если больше максимального, нет тарифа и одновременно действие подписки
    if subs_count > max_subscriptions_without_tariff \
            and (
            subscription is None
            or not (subscription['tariff_id'] > 0 and subscription['time_left'] > 0)) \
            and updated_state_data['subscribed']:
        notify(
            data['callback'], data['message'],
            get_message("withoutTariffSubscriptionsLimited", data['language_code']), alert=True)
        return False

    # основная логика
    if updated_state_data['subscribed']:
        pc_name, new_podcast_id = app.service.podcast.subscription.add_sub(
            data['chat_id'],
            updated_state_data['id'], updated_state_data['service_id'], updated_state_data['service_name'])
        u_action = "yousubscribedto"

        # Update channel id if created, Important!
        updated_state_data['id'] = new_podcast_id
    else:
        pc_name = app.service.podcast.subscription.remove_sub(
            data['chat_id'],
            updated_state_data['id'], updated_state_data['service_id'], updated_state_data['service_name'])
        u_action = "youunsubscribedto"

    if pc_name is None:
        notify(data['callback'], data['message'], get_message("parsingError", data['language_code']))
        return False

    # Clean state data
    get_and_set_podcast_data(
        data['chat_id'], updated_state_data['service_id'], updated_state_data['id'], updated_state_data['service_name'])

    try:
        notify(data['callback'], data['message'], get_message(u_action, data['language_code']) % pc_name, alert=True)
    except Exception:
        pass

    # If unsubscribe from unavailable podcast, go back
    if data['united_data'].get('unavailable', False):
        return data['go_back_action'](data)

    channel_msg = construct_channel_message(data['chat_id'], data['language_code'])
    if data['callback'].message is not None:
        message_editor(data['chat_id'], channel_msg[1], data['callback'].message.message_id)
    else:
        render_messages(data['chat_id'], channel_msg)


def change_channel_notify(data: ControllerParams):
    if data['united_data'] is None:
        notify(
            data['callback'], data['message'], get_message("parsingError", data['language_code']), alert=True)
        return False

    updated_state_data: PodcastStateData = (copy.deepcopy(data['united_data'])
                                            | {'notify': not data['united_data']['notify']})

    u_action = 'notifyoned' if updated_state_data['notify'] else 'notifyoffed'
    try:
        db_users = SQLighter(db_path)
        db_users.turn_notify_tg(
            data['chat_id'],
            storage.get_user_state_data(data['chat_id'], 'podcast')["id"],
            updated_state_data['notify'])
        notify(data['callback'], data['message'], get_message(u_action, data['language_code']), alert=True)
        db_users.close()
    except Exception:
        try:
            notify(
                data['callback'], data['message'],
                get_message("parsingError", data['language_code']), alert=True)
        except Exception:
            pass

    set_podcast_data(data['chat_id'], updated_state_data)

    channel_msg = construct_channel_message(data['chat_id'], data['language_code'], updated_state_data)
    message_editor(data['chat_id'], channel_msg[1], data['callback'].message.message_id)


def rate(data: ControllerParams):
    current_state_data: PodcastStateData = data['united_data']
    if current_state_data is None:
        notify(
            data['callback'], data['message'], get_message("parsingError", data['language_code']), alert=True)
        return False

    db_users = SQLighter(db_path)
    try:
        db_users.rate_podcast(
            data['chat_id'], storage.get_user_state_data(data['chat_id'], 'podcast')['id'],
            current_state_data['rate'])
    except Exception:
        try:
            notify(
                data['callback'], data['message'],
                get_message("parsingError", data['language_code']), alert=True)
        except Exception:
            pass

        return
    db_users.close()

    storage.set_user_state_data(data['chat_id'], 'podcast', current_state_data)

    channel_msg = construct_channel_message(data['chat_id'], data['language_code'], current_state_data)
    message_editor(data['chat_id'], channel_msg[1], data['callback'].message.message_id)
