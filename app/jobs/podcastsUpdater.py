# -*- coding: utf-8 -*-
import asyncio
import time
import typing
from urllib.parse import quote

from telebot import types  # type: ignore
from telethon import TelegramClient
from telethon.sessions import StringSession

import app.i18n.messages
import app.service.podcast.podcast
import app.service.record.helpers
import app.service.user.language
import lib.markup.cleaner
from agent.bot_telebot import bot
from agent.bot_telethon import thobot_session_handler
from app.controller.builders.helpModule import get_promo_messages
from app.controller.general.notify import notify
from app.core.sender.send_record_helper import ChatParamsType, DescriptionModeOptions
from app.routes.message_tools import go_back_inline_markup
from app.service.payment.paymentSafeModule import is_subscription_active
from lib.telegram.general.message_master import message_master, outer_sender, render_messages
import lib.tools.time_tools.general
from app.controller.builders import recsModule
from app.controller.builders.adminModule import send_message_to_creator
from app.core.sender import send_record_helper
from app.i18n.messages import get_message
from app.repository.storage import storage
from config import (
    db_path, std_bitrate, server,
    another_projects_texts, max_subscriptions_without_tariff,
    app_api_id, app_api_hash, token, botName)
from db.sqliteAdapter import SQLighter
from lib.tools.logger import Logger
from app.routes.ptypes import ControllerParams

MAX_EPISODES_PER_PODCAST = 3

logger = Logger(file="updater")


def main(interval=120):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop = asyncio.get_event_loop()

    asyncio.set_event_loop(loop)
    thonbot = TelegramClient(
        StringSession(thobot_session_handler), app_api_id, app_api_hash, loop=loop
    ).start(bot_token=token)
    thonbot.disconnect()

    while True:
        if not server:
            send_message_to_creator("Started")
            time.sleep(60 * 60)
            storage.set_last_channel_id(1)

        last_updated_channel_id = storage.get_last_channel_id()
        # если поток упал, то пропустить то, что уронило
        logger.log("Restarted?", storage.is_last_channel_restarted())
        if storage.is_last_channel_restarted() or last_updated_channel_id != 1:
            last_updated_channel_id += 1
            storage.set_last_channel_restarted(False)
            send_message_to_creator("#restarted")

        logger.log("New circle, luci: ", last_updated_channel_id, "| ", time.ctime())
        send_message_to_creator(
            "New cirlce #new_circle; luci: " + str(last_updated_channel_id))

        db_users = SQLighter(db_path)
        # # получение всех подкастов с подписками
        # channels_to_check = db_users.get_channels_to_check()
        # channels_to_check_ids = []
        # for channel in channels_to_check:
        # 	channels_to_check_ids.append(str(channel['id']))
        # # channels = db_users.get_all_channels()
        # # for channel in channels:
        # channel = db_users.get_channel_or_next(
        # 	last_updated_channel_id, channels_to_check_ids)
        # ---------
        # получение всех, так как шлём пользователям без подписки уведомления
        channel = db_users.get_channel_or_next(last_updated_channel_id)
        db_users.close()

        storage.clear_new_podcast_available_flags()

        while channel is not None:

            # if not server:
            logger.log("Processig channel", channel['id'])

            db_users = SQLighter(db_path)
            # работаем только с пользователями, у которых есть включены уведомления
            # именно благодаря им у остальных будет появляться надпись "new"
            # ...
            # пользователи с подпиской на бота и уведомлениями
            connections = db_users.get_uccs_by_channel(
                channel['id'], have_subscription=True, notifications_enabled=True)
            # пользователи без подписки на бота и уведомлениями
            nosubs_connections = db_users.get_uccs_by_channel(
                channel['id'], have_subscription=False, notifications_enabled=True)
            # каналы, владельцы которых подписаны на бота
            tg_channel_connections = db_users.getTgChannelSubConnectionsByPodcast(
                channel['id'], have_subscription=True, notifications_enabled=True)
            db_users.close()

            storage.set_last_channel_id(channel['id'])

            if connections is not None:
                send_new_records_by_channel(
                    channel, connections, thonbot=thonbot,
                    nosubs_connections=nosubs_connections,
                    tg_channel_connections=tg_channel_connections)

            db_users = SQLighter(db_path)
            channel = db_users.get_next_channel(channel['id'])
            db_users.close()

            if channel is None:
                logger.log("Next channel is None!")
            else:
                logger.log("Next channel is:", channel['id'])

            time.sleep(6)
            # time.sleep(60 * 60)

        storage.set_last_channel_id(1)
        storage.set_last_channel_restarted(False)

        send_message_to_creator(
            "Circle finished #circle_finished; luci: "
            + str(storage.get_last_channel_id()))

        # отправка уведомлений о новых эпизодах пользователям без подписки
        flag_no_sub_users = storage.get_new_podcast_available_flags()
        if flag_no_sub_users is not None and len(flag_no_sub_users) > 0:
            logger.log(
                "Sending 'new episodes available' message to "
                + str(len(flag_no_sub_users)) + " users")
            for user_tg_id in flag_no_sub_users:
                db_users = SQLighter(db_path)
                user = db_users.get_user_by_tg(user_tg_id)
                db_users.close()
                user_language = app.service.user.language.user_language(user['lang'])
                outer_sender(user['telegramId'], [{
                    'type': 'text', 'text': get_message("youHaveNewEpisodes", user_language)
                                            + " t.me/" + botName + "?start=" + str(user['telegramId'])}])
                time.sleep(1)

        time.sleep(interval * 60)


def send_new_records_by_channel(
        channel, connections, manual=False, thonbot=None,
        nosubs_connections=None, tg_channel_connections=None
):
    new_recs_flag = False
    # print(channel['id'], flush=True)
    # print((channel['name']).encode('utf-8'), flush=True)
    # connections = list(filter(lambda c: c['notify'] != 0, connections))
    # if not manual:
    # 	connections = list(filter(lambda c: (
    # 		c['notify_count'] is not None and c['notify_count'] != 0), connections))

    # if len(connections) == 0:
    if len(connections) == 0 \
            and (nosubs_connections is None or len(nosubs_connections) == 0) \
            and (tg_channel_connections is None or len(tg_channel_connections) == 0):
        # # обновление инф. о последнем обновлении канала
        # updatePodcastLastGuidDate(channel)
        return new_recs_flag

    root: app.service.podcast.podcast.RootAdapter | typing.Literal[False] = False
    pc_info: app.service.podcast.podcast.PodcastInfoType = {}
    service_name: str | None = None

    if channel["itunes_id"] is not None and channel["itunes_id"]:
        payload = {'entity': 'podcast', 'id': channel['itunes_id']}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload)
        service_name = 'itunes'
        service_id = channel["itunes_id"]
    if root is False and channel["rss_link"] is not None and channel["rss_link"]:
        payload = {'rss_link': channel["rss_link"]}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload, 'rss')
        service_name = 'rss'
        service_id = channel["rss_link"]

    if root is False:
        try:
            if nosubs_connections is not None:
                for connection in nosubs_connections:
                    db_users = SQLighter(db_path)
                    db_users.turn_notify_tg(
                        connection['user_telegram_id'], connection['channel_id'], False)
                    db_users.close()
        except Exception:
            pass

        for connection in connections:
            db_users = SQLighter(db_path)
            user = db_users.get_user_by_tg(connection['user_telegram_id'])
            user_language = app.service.user.language.user_language(user['lang'])
            # Выключить уведомления для канала для пользователей с подпиской
            db_users.turn_notify_tg(user['telegramId'], connection['channel_id'], False)
            db_users.close()
            collection_name = ""

            try:
                if ("collectionName" in pc_info) \
                        and (pc_info["collectionName"] is not None) \
                        and (pc_info["collectionName"] != ""):
                    outer_sender(connection['user_telegram_id'], [{
                        'type': 'text', 'text':
                            "<br>" + pc_info['collectionName'] + "</b>\n\n"
                            + get_message('notificationsFCDisabled', user_language)
                    }])
                    storage.set_user_resend_flag(user[1])
                    new_recs_flag = True
                    collection_name = pc_info["collectionName"]
            except Exception as e:
                logger.err("podcastsUpdater/whileNotifyUserAboutNtfDisabled: ", e)

            try:
                logger.log(
                    "PARSING ERROR! In podcastUpdater2. ",
                    "Notifications disabled for podcast ", collection_name)
            except Exception as e:
                logger.err(
                    "PARSING ERROR! In podcastUpdater2. ",
                    "Notifications disabled for podcast ", e)
        return new_recs_flag

    if service_name == 'itunes':
        # # flag = True
        # # но itunes иногда отдаёт неправильные даты
        # flag = False
        last_date = pc_info["lastDate"]
        itunes_link = pc_info["itunesLink"]
        feed_url = pc_info["feedUrl"]
    elif service_name == 'rss':
        # flag = False
        last_date = pc_info["lastDate"]  # None
        itunes_link = pc_info["itunesLink"]  # None
        feed_url = pc_info["feedUrl"]
    else:
        return

    # объединение связей с пользователями и каналами
    all_target_connections = connections
    if tg_channel_connections is not None:
        all_target_connections += tg_channel_connections

    notify_left_tg = {}
    last_saved_guids_map: dict[str, list[int]] = {}  # guid -> [chat_id]
    last_saved_dates_map: dict[str, list[int]] = {}  # date -> [chat_id]
    target_users_tg_set: dict[int, ChatParamsType] = {}  # chat_id ->
    # Core logic!
    for connection in all_target_connections:
        # продолжаем, если хотя бы у одного дата отличается
        # flag = flag and (lastDate == connection['last_date'])
        # но itunes иногда отдаёт неправильные даты

        # список юзеров, которым отправляем
        target_users_tg_set[connection['user_telegram_id']] = {}

        # обработка каналов: в их связях есть дополнительные поля
        if 'user_type' in connection.keys() and \
                connection['user_type'] == 'channel' and 'owner_id' in connection.keys():
            target_users_tg_set[connection['user_telegram_id']]['silent'] = True
            target_users_tg_set[connection['user_telegram_id']]['dont_set_resend'] = True
            target_users_tg_set[connection['user_telegram_id']]['based_on_user_id'] = \
                connection['owner_id']
            target_users_tg_set[connection['user_telegram_id']]['bot_reference'] = False
            target_users_tg_set[connection['user_telegram_id']]['show_updated_text'] = \
                False
            target_users_tg_set[connection['user_telegram_id']]['description_mode'] = typing.cast(
                DescriptionModeOptions, 'none')

        # для данного последнего guid создаём массив с пользователями
        if connection['last_guid'] not in last_saved_guids_map:
            last_saved_guids_map[connection['last_guid']] = []
        # то же для даты
        if connection['last_date'] \
                and connection['last_date'] not in last_saved_dates_map:
            last_saved_dates_map[connection['last_date']] = []

        # и добавляем туда текущего юзера (там уже могут быть другие)
        last_saved_guids_map[connection['last_guid']].append(
            connection['user_telegram_id'])
        # то же для даты
        last_saved_dates_map[connection['last_date']].append(
            connection['user_telegram_id'])

        if connection['notify_count'] is None:
            notify_left_tg[connection['user_telegram_id']] = 0
        else:
            notify_left_tg[connection['user_telegram_id']] = connection['notify_count']

    # для пользователей без подписки, аналогично
    nosub_connections_to_pgd = {}
    if nosubs_connections is not None:
        for connection in nosubs_connections:
            nosub_connections_to_pgd[connection['user_telegram_id']] = \
                connection['last_guid']

    # if flag:  # если можно получить и сравнить lastDate до rss, обычно из itunes
    #     return new_recs_flag

    target_chats = dict(target_users_tg_set)
    utg_langs: dict[int, str] = {}
    bitrates_tg: dict[int, int | None] = {}
    db_users = SQLighter(db_path)
    for utg in target_users_tg_set:
        user = db_users.get_user_by_tg(utg)
        utg_langs[utg] = app.service.user.language.user_language(user['lang'])

        subscription = db_users.getUserSubscriptionByTg(utg)
        if user['bitrate'] is not None and is_subscription_active(subscription):
            bitrates_tg[utg] = int(user['bitrate'])
        else:
            bitrates_tg[utg] = std_bitrate
    db_users.close()

    ch_name = ""
    flag_have_users = 0
    i = 0
    links = []
    descrs = []
    titles = []
    pub_dates = []
    pub_dates_strped = []
    durations = []
    guids = []
    last_guids_to_users: dict[str, dict[int, ChatParamsType]] = {}
    channel_link = ""

    for channelDescr in root.getchildren():
        if channelDescr.tag == "link":
            try:
                channel_link = quote(channelDescr.text, safe=":/?=")
            except Exception:
                channel_link = channelDescr.text

        elif channelDescr.tag == "title":
            ch_name = str(channelDescr.text)

        # получение lastDate из RSS в формате itunes
        elif channelDescr.tag in ["lastBuildDate", "pubDate"] and last_date is None:
            try:
                last_date = lib.tools.time_tools.general.format_rss_last_date(str(channelDescr.text))
            except Exception:
                last_date = str(channelDescr.text)

            flag_rss = True
            for connection in all_target_connections:
                flag_rss = flag_rss and (last_date == connection['last_date'])

            # если lastDate можно получить только из rss и все уже отправлены
            if flag_rss:
                return new_recs_flag

        elif channelDescr.tag == "item":
            if flag_have_users == 1 or i > MAX_EPISODES_PER_PODCAST:  # ограничение на кол-во подкастов
                break
            links.append("")
            titles.append("")
            descrs.append("")
            pub_dates.append("")
            durations.append("")
            guids.append("")
            pub_dates_strped.append("")

            for record in channelDescr.getchildren():
                if record.tag == "enclosure":
                    try:
                        links[len(links) - 1] = str(quote(record.attrib["url"], safe=":/?=_"))
                    except Exception:
                        links[len(links) - 1] = ""
                elif record.tag == "description":
                    try:
                        descrs[len(descrs) - 1] = str(record.text)
                    except Exception:
                        descrs[len(descrs) - 1] = record.text
                elif record.tag == "title":
                    titles[len(titles) - 1] = str(record.text)
                elif record.tag == "pubDate":
                    try:
                        pub_dates[len(pub_dates) - 1] = app.service.podcast.podcast.prepare_string_from_rss(
                            lib.tools.time_tools.general.format_rss_last_date(str(record.text)))
                    except Exception:
                        pub_dates[len(pub_dates) - 1] = app.service.podcast.podcast.prepare_string_from_rss(
                            str(record.text))

                    # dt = datetime.strptime(str(record.text), '%a, %d %b %Y %H:%M:%S %z')
                    # pubDatesStrped[len(pubDatesStrped) - 1] = dt
                    pub_dates_strped[len(pub_dates_strped) - 1] = app.service.podcast.podcast.prepare_string_from_rss(
                        str(record.text))
                elif record.tag == "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration":
                    durations[len(durations) - 1] = record.text
                elif record.tag == "guid":
                    guids[len(guids) - 1] = str(record.text)

            # Core logic!
            # подготавливаем для данного guid массив юзеров
            # pgd = guids[-1] + "_" + pubDatesStrped[-1]
            pgd = app.service.record.helpers.get_record_uniq_id(guids[-1], pub_dates_strped[-1], titles[-1])

            if pgd not in last_guids_to_users:
                last_guids_to_users[pgd] = {}

            # если этот guid — последний для юзеров,
            # то убираем этих юзеров из целевых для данной записи
            if pgd in last_saved_guids_map:
                for u in last_saved_guids_map[pgd]:
                    if u in target_users_tg_set:
                        del target_users_tg_set[u]

            # также перебираем даты, если последняя дата юзера больше даты подкаста
            # то игнорируем этого юзера
            # это нужно, если подкастер перезальёт подкаст
            if pub_dates[-1]:
                record_date = lib.tools.time_tools.general.prepare_date_time_from_formatted(pub_dates[-1])
                if record_date:
                    for last_saved_date in last_saved_dates_map:
                        last_saved_date_formatted = lib.tools.time_tools.general.prepare_date_time_from_formatted(
                            last_saved_date)
                        if last_saved_date_formatted >= record_date:
                            for u in last_saved_dates_map[last_saved_date]:
                                if u in target_users_tg_set:
                                    del target_users_tg_set[u]

            # для оставшихся юзеров заполняем цели по id
            for u in target_users_tg_set:
                last_guids_to_users[pgd][u] = target_users_tg_set[u]

            # если юзеров не осталось — выходим
            if len(target_users_tg_set) == 0:
                flag_have_users = 1
            i += 1

    if len(links) < 1:
        return new_recs_flag

    last_date = app.service.podcast.podcast.set_last_date(last_date, pub_dates_strped[0])

    last_guid = guids[0]
    last_pub_date_strped = pub_dates_strped[0]
    last_title = titles[0]

    # удалить тот, который уже был отправлен, если были такие пользователи
    if flag_have_users != 0:
        links.pop()
        descrs.pop()
        titles.pop()
        pub_dates.pop()
        pub_dates_strped.pop()
        durations.pop()
        guids.pop()

    # хронологический порядок
    links.reverse()
    descrs.reverse()
    titles.reverse()
    pub_dates.reverse()
    pub_dates_strped.reverse()
    durations.reverse()
    guids.reverse()

    if itunes_link is None or itunes_link == "None":
        itunes_link = ""
    if channel_link is None or channel_link == "None":
        channel_link = ""

    for i, link in enumerate(links):

        if link == "":
            continue

        descr = descrs[i]
        title = titles[i]
        pubDate = pub_dates[i]
        pubDateStrped = pub_dates_strped[i]
        duration = durations[i]
        guid = guids[i]

        pgd = app.service.record.helpers.get_record_uniq_id(guid, pubDateStrped, title)

        if pgd == '':
            send_message_to_creator(
                "BAD GUID: " + str(pgd) + "; "
                + str(title) + "; " + link)
            logger.warn((
                                "BAD GUID: " + str(pgd) + "; "
                                + str(title) + "; " + str(link)
                        ).encode('utf-8'))

        if not manual:
            for utg in last_guids_to_users[pgd]:
                if notify_left_tg[utg] == 0:
                    del last_guids_to_users[pgd][utg]
        if len(last_guids_to_users[pgd]) == 0:
            continue
        new_recs_flag = True

        if descr is None or descr == "None":
            descr = ""
        if title is None or title == "None":
            title = ""
        if pubDate is None or pubDate == "None":
            pubDate = ""
        if ch_name is None or ch_name == "None" or ch_name == "":
            ch_name = channel['name']

        descr = lib.markup.cleaner.html_mrkd_cleaner(descr)
        title = lib.markup.cleaner.html_mrkd_cleaner(title)
        ch_name = lib.markup.cleaner.html_mrkd_cleaner(ch_name)

        duration_sec = send_record_helper.transform_duration(duration)

        # INFO: для тестов
        # if True:  # not server:
        # 	if 6070615 in lastGuidsToUsers[pgd]:
        # 		lastGuidsToUsers[pgd] = [6070615]
        # 		utglangs = {6070615: "ru"}
        # 		print("locale", flush=True)
        # 	else:
        # 		lastGuidsToUsers[pgd] = []
        # 		utglangs = {}

        podcast_info = {
            'id': channel['id'],
            'title': title,
            'descr': descr,
            'itunesLink': itunes_link,
            'channelLink': channel_link,
            'chName': ch_name,
            'pubDate': pubDate,
            'duration_sec': duration_sec,
            'service_name': service_name,
            'service_id': service_id,
            'with_next_ep_button': False,
            'recNum': i,
            'recordUniqId': pgd
        }

        logger.log("Sending automatically...\n", (
                "Channel id: " + str(channel['id'])
                + ", '" + str(podcast_info['title'])
                + "' (itunes id:" + str(channel['itunes_id']) + ") "
                + "to " + str(last_guids_to_users[pgd])
                + " ___ link: " + str(link)
                + " ___ (feed: " + str(feed_url) + ")").encode('utf-8'))

        # !!! Функция отправки
        sender = send_record_helper.Sender(
            thonbot, link, last_guids_to_users[pgd], utg_langs, bitrates_tg,
            podcast_info, with_status_message=False)
        successfully_sent_to = sender.send_record()

        if not manual:
            for user_tg_id in successfully_sent_to:
                if notify_left_tg[user_tg_id] > 0:
                    db_users = SQLighter(db_path)
                    db_users.decrease_notify_count(user_tg_id, 1)
                    db_users.close()
                    notify_left_tg[user_tg_id] -= 1
                if notify_left_tg[user_tg_id] == 0:
                    outer_sender(user_tg_id, [{
                        'type': 'text', 'text': get_message("notificationsEnded", utg_langs[user_tg_id]),
                        'reply_markup': [[{
                            'text': get_message("tariffs", utg_langs[user_tg_id]),
                            'callback_data': {'tp': 'bs_trfs'}
                        }]]
                    }])

        logger.log("SENT AUTOMATICALLY! To: ", successfully_sent_to)

    db_users = SQLighter(db_path)

    pgd = app.service.record.helpers.get_record_uniq_id(last_guid, last_pub_date_strped, last_title)
    # INFO: обновление инф. о последнем обновлении канала
    db_users.update_channel_last_guid_date(channel['id'], pgd, last_date)

    # обновление данных о последнем выпуске для пользователей
    if len(guids) > 0:

        # для пользователей с подпиской
        if len(guids) > 0:
            for user_tg_id in target_chats:

                # если канал, то обновить владельца, если его уже нет в общем списке
                if 'based_on_user_id' in target_chats[user_tg_id] \
                        and target_chats[user_tg_id]['based_on_user_id']:
                    user_tg_id = target_chats[user_tg_id]['based_on_user_id']
                    if user_tg_id in target_chats:
                        continue

                try:
                    db_users.update_sub_last_guid_and_date(
                        user_tg_id, channel['id'], pgd, last_date)
                except Exception as e:
                    logger.err("podacstUpdater/db_after_ops2: ", e)
                    return new_recs_flag

    db_users.close()

    return new_recs_flag


def update_feed(data: ControllerParams):
    db_users = SQLighter(db_path)
    is_user_have_bot_subscription = db_users.is_user_have_bot_subscription(data['chat_id'])
    send_promo_message = not is_user_have_bot_subscription
    user_podcast_count = int(db_users.get_uccs_count_by_tg(data['chat_id']))
    db_users.close()

    if send_promo_message:
        promo_message = get_message('another_projects_text', data['language_code'])
        promo_message += "\n\n" + get_promo_messages(data['language_code'])
        outer_sender(data['chat_id'], [{'type': 'text', 'text': promo_message}])

    # сообщение "необходимо время" + ограничения
    need_time_to_load_message = get_message(
        "needTimeToLoad", data['language_code'])
    if (
            not is_user_have_bot_subscription
            and (user_podcast_count > max_subscriptions_without_tariff)
    ):
        need_time_to_load_message += "\n\n" + get_message(
            'withoutTariffUpdateLimited', data['language_code'])

    notify_as_message = data.get('callback', None) is None or send_promo_message

    # Command or promo message is sent
    if notify_as_message:
        render_messages(
            data['chat_id'],
            [{
                'type': 'text', 'text': need_time_to_load_message, 'disable_web_page_preview': True,
                'reply_markup': go_back_inline_markup(data['language_code'])}],
            resending=True)
        storage.del_user_state(data['chat_id'])
        storage.add_user_state(data['chat_id'], "menu")
    else:
        notify(
            data['callback'], data['message'],
            need_time_to_load_message)

    recsModule.t_podcast_sender.main_queue.put(
        {
            'bot': bot, 'action': 'update', 'user_id': data['chat_id'],
            'func_params': {
                'data': data,
                'is_user_have_bot_subscription': is_user_have_bot_subscription}
        })

    # Don't change state because notified and messages were not sent
    if not notify_as_message:
        return False


def update_feed_thread(input_data, thonbot):
    data: ControllerParams = input_data['func_params']['data']
    is_user_have_bot_subscription = input_data['func_params']['is_user_have_bot_subscription']

    db_users = SQLighter(db_path)
    new_records_check = False
    connections = db_users.get_uccs_by_tg(
        data['chat_id'], is_user_have_bot_subscription=is_user_have_bot_subscription)
    db_users.close()

    for connection in connections:
        db_users = SQLighter(db_path)
        channel = db_users.get_channel(connection['channel_id'])
        db_users.close()
        if channel is not None:
            new_records_check = send_new_records_by_channel(
                channel, [connection], thonbot=thonbot,
                manual=True) or new_records_check

    if not new_records_check:
        render_messages(
            data['chat_id'], [{
                'type': 'text', 'text': get_message("noNewRecords", data['language_code']),
                'reply_markup': go_back_inline_markup(data['language_code'])}])
