import json
import queue
import re
from hashlib import sha256
from threading import Thread
from typing import TypedDict, Any, cast as typing_cast
from urllib.parse import quote

import app.service.podcast.podcast
import app.service.record.caption
import app.service.record.helpers
import lib.markup.cleaner
import lib.tools.time_tools.general
from app.controller.builders.podcastModule import PodcastStateData
from app.controller.general.notify import notify
from app.controller.types_helpers.recs import RecResult, RecsStateData, RecordsDataType, \
    rec_callback_data_identifier, RecDataType
from app.core.balancers import recordSender
from app.core.message.navigationBuilder import determine_search_query_and_page, get_full_message_navigation, \
    FullMessageNavigation
from app.core.sender import send_record_helper
from app.i18n.messages import get_message, standartSymbols, emojiCodes, get_message_rtd
from app.repository.storage import storage
from app.routes.message_tools import go_back_inline_markup
from app.routes.ptypes import ControllerParams
from app.routes.routes_list import AvailableRoutes
from config import db_path, std_bitrate, maxPodcastDateCallDataHexLen, perPage
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import render_messages, MessageStructuresInterface, \
    InlineButtonData
from lib.tools.logger import logger

PER_PAGE = 5

recordSenderQueue = queue.Queue()
t_podcast_sender = recordSender.RecordBalancer(recordSenderQueue)


def open_recs(data: ControllerParams):
    render_messages(data['chat_id'], [{
        'type': 'text',
        'text': get_message('loading', data['language_code']),
    }], resending=data['callback'] is None)

    podcast_data: PodcastStateData = storage.get_user_state_data(data['chat_id'], 'podcast')

    recs_data = determine_search_query_and_page(data['callback'], data['message'], data['united_data'])
    search_query = recs_data.get('search', None)

    # устанавливаем, показывать ли размер файлов, если он приходит,
    # а если его нет сейчас, то по умолчанию не выбрано
    if 'show_file_sizes' not in recs_data:
        recs_data['show_file_sizes'] = False

    # данные о последнем просмотренном выпуске для отметок о новом
    if 'last_user_guid' not in recs_data or 'last_user_date' not in recs_data:
        recs_data['last_user_guid'] = podcast_data.get('last_user_guid', None)
        recs_data['last_user_date'] = podcast_data.get('last_user_date', None)

    # New episodes mark
    if recs_data.get('last_user_guid', None) is not None and recs_data.get('last_user_date', None) is not None:
        look_for_new_episodes = True
        last_user_date_formatted = lib.tools.time_tools.general.prepare_date_time_from_formatted(
            recs_data['last_user_date'])
    else:
        look_for_new_episodes = False
        last_user_date_formatted = None

    # Load from RSS
    root, podcast_info = load_podcast_root(podcast_data)
    records_info = load_records_data(
        root, curr_page=recs_data['p'], search_query=search_query,
        look_for_new_episodes=look_for_new_episodes, last_user_guid=recs_data['last_user_guid'],
        last_user_date_formatted=last_user_date_formatted,
        take_file_links=recs_data['show_file_sizes'])

    try:
        message_navigation = get_full_message_navigation(
            recs_data['p'], search_query,
            make_query, [podcast_data, recs_data, records_info, search_query,
                         root, look_for_new_episodes, last_user_date_formatted],
            None, None, PER_PAGE, None,
            data['language_code'], data['route_name'],
            back_button_text='goBackMenu', order_builder=None)
    except Exception as e:
        logger.err(e)
        notify(data['callback'], data['message'], text=get_message('parsingError', data['language_code']))
        return False

    if 'error' in message_navigation['page_data']:
        if message_navigation['page_data']['error'] == 'empty':
            error_text_getter = 'empty' if search_query is None else 'empty_when_search'
            error_message = get_message_rtd(
                ['subs', 'errors', 'paging', error_text_getter], data['language_code'])
        else:
            error_message = get_message_rtd(['errors', 'unknown'], data['language_code'])
        notify(data['callback'], data['message'], text=error_message, resending=True)
        return False

    subs_msg = construct_records_message(
        recs_data, podcast_data, data['route_name'], message_navigation, data['language_code'])

    render_messages(data['chat_id'], subs_msg, resending=data['is_command'])

    storage.set_user_state_data(data['chat_id'], data['route_name'],
                                {**recs_data, 'p': message_navigation['page_data']['current_page']})

    # Update last date and pgd
    # Get last date
    if records_info['lastDate'] != "" and podcast_info['lastDate'] is None:
        last_date = records_info['lastDate']
    else:
        last_date = podcast_info['lastDate']
    # не всегда в rss присутствует lastBuildDate
    last_date = app.service.podcast.podcast.set_last_date(last_date, records_info['globalLastPubDate'])
    pgd = app.service.record.helpers.get_record_uniq_id(
        records_info['lastGuid'], records_info['lastPubDate'], records_info['lastRecordTitle'])
    db_users = SQLighter(db_path)
    channel = db_users.get_channel_by_service_tg(
        id, podcast_data["service_id"], podcast_data["service_name"])
    # при открытии записей считать подкаст просмотренным
    if channel is not None and recs_data['p'] == 1:
        db_users.update_sub_last_guid_and_date(
            id, channel['id'], pgd, last_date)
        db_users.update_channel_last_guid_date(
            channel['id'], pgd, last_date)
        podcast_data["have_new_episodes"] = False
        podcast_data["last_user_guid"] = pgd
    db_users.close()
    storage.set_user_state_data(id, 'podcast', podcast_data)


# Load from external services rss root and itunes info
def load_podcast_root(podcast_data: PodcastStateData) -> tuple[Any, dict]:
    if 'service_name' not in podcast_data:
        podcast_data['service_name'] = 'itunes'

    if podcast_data['service_name'] == 'itunes':
        payload = {'entity': 'podcast', 'id': podcast_data['service_id']}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload)
    elif podcast_data['service_name'] == 'rss':
        payload = {'rss_link': podcast_data['service_id']}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload, 'rss')
    else:
        root = False
        pc_info = {}

    if root is False:
        raise Exception

    return root, pc_info


# Get data for paging in external navigation builder module
def make_query(
        podcast_data: PodcastStateData, recs_data: RecsStateData, records_info: RecordsDataType,
        search_query: str, root: Any, look_for_new_episodes: bool, last_user_date_formatted: str,
        _, per_page: int = PER_PAGE, offset: int = 0
) -> TypedDict('MakeSearch', {'results': list[RecResult], 'count': int}):
    current_page = int(offset / per_page) + 1

    # Input page is wrong
    if current_page != records_info['effective_page']:
        records_info = load_records_data(
            root, curr_page=current_page, search_query=search_query,
            look_for_new_episodes=look_for_new_episodes, last_user_guid=recs_data['last_user_guid'],
            last_user_date_formatted=last_user_date_formatted,
            take_file_links=recs_data['show_file_sizes'])

    # Get page count
    if 'search' not in recs_data:
        rec_count = podcast_data['recCount']
    else:
        rec_count = records_info['itemCounter']

    # получение размеров записей в мультипотоке
    recs_on_this_page = len(records_info['title'])
    file_sizes = [""] * recs_on_this_page
    threads = []

    def get_sizes_prepared(link, sizes, index):
        try:
            sizes[index] = str(round(
                send_record_helper.get_file_size_HTTP(link) / 1048576,  # 1024 * 1024
                2)) \
                           + " MiB | "
        except Exception:
            pass

    if recs_data['show_file_sizes']:
        for i in range(recs_on_this_page):
            threads.append(Thread(target=get_sizes_prepared, args=(records_info['links'][i], file_sizes, i)))
            threads[i].start()
        for i in range(recs_on_this_page):
            threads[i].join()

    # Get recs data
    recs_results: list[RecResult] = []
    for i in range(recs_on_this_page):
        recs_results.append({
            'is_new_episode': records_info['isNewEpisode'][i],
            'file_size': file_sizes[i],
            'title': records_info['title'][i],
            'dh': sha256(records_info['recordUniqIds'][i].encode('utf-8'))
                  .hexdigest()[0:maxPodcastDateCallDataHexLen],
            'num': records_info['rssNumbers'][i]
        })

    return {'results': recs_results, 'count': rec_count}


# Construct message
def construct_records_message(
        recs_data: RecsStateData, podcast_data: PodcastStateData, route_name: AvailableRoutes,
        message_navigation: FullMessageNavigation, language_code: str) -> list[MessageStructuresInterface]:
    # Generate short podcast message
    disk_emodji = emojiCodes.get('disk')
    try:
        descr = podcast_data["descr"]
    except Exception:
        descr = ""
    # первое предложение
    i = [x.start() for x in re.finditer(r'[.?!]\s', descr)]
    try:
        if i[0] > 0:
            descr = descr[:i[0] + 1]
    except Exception:
        pass
    # дополнительная обработка текста
    descr = app.service.record.caption.prepare_message_text(descr)
    # Clean dates
    ch_name = lib.markup.cleaner.html_mrkd_cleaner(podcast_data['title'])
    descr = lib.markup.cleaner.html_mrkd_cleaner(descr)
    last_date = lib.markup.cleaner.html_mrkd_cleaner(podcast_data['lastDate'])
    if ch_name is None or not ch_name:
        ch_name = ''
    if descr is None or not descr:
        descr = ''
    if last_date is None or not last_date:
        last_date = ''
    message_text = "<b>" + ch_name + "</b>\n" + \
                   get_message("lastUpdate", language_code) + " " + \
                   app.service.podcast.podcast.prepare_podcast_update_time(last_date) + "\n\n" + \
                   descr + "\n" + get_message("thereis", language_code) + " " + \
                   str(message_navigation['page_data']['count']) + " " + disk_emodji + "\n" + \
                   message_navigation['routing_helper_message']

    # Keyboard
    records_keyboard: list[list[InlineButtonData]] = []

    res: RecResult
    for res in message_navigation['page_data']['data']:
        new_ep_text = standartSymbols.get("newItem", "") + " " if res['is_new_episode'] else ""
        records_keyboard.append([
            {'text': new_ep_text + res['file_size'] + res['title'],
             'callback_data': rec_callback_data_identifier(podcast_data['id'], podcast_data['service_id'],
                                                           podcast_data['service_name'], res['dh'], res['num'])}
        ])

    # Add 1, last and < > buttons
    records_keyboard.append([
        {'text': f"{get_message('page', language_code)} 1", 'callback_data': {'tp': route_name, 'p': 1}},
        {'text': f"{get_message('page', language_code)} {message_navigation['page_data']['page_count']}",
         'callback_data': {'tp': route_name, 'p': message_navigation['page_data']['page_count']}}])
    records_keyboard.append([
        message_navigation['nav_layout_parts']['navigation_row'][0],
        message_navigation['nav_layout_parts']['navigation_row'][2]])

    modes_row: list[InlineButtonData] = []
    if 'search' in recs_data:
        modes_row += message_navigation['nav_layout_parts']['exit_search_mode_row']
    modes_row.append({
        'text': (
                    emojiCodes.get("whiteHeavyCheckMark")
                    if recs_data["show_file_sizes"]
                    else emojiCodes.get("crossMark")
                ) + " " + get_message("showFileSizes", language_code),
        'callback_data': {'tp': route_name, 'show_file_sizes': not recs_data['show_file_sizes']}
    })
    records_keyboard.append(modes_row)

    button_back = {'text': get_message("backToCHannel", language_code), 'callback_data': {'tp': 'bck'}}
    records_keyboard.append([button_back])

    return [{
        'type': 'text',
        'text': message_text,
        'reply_markup': records_keyboard,
        'disable_web_page_preview': True
    }]


def load_records_data(
        root, curr_page=None, search_query=None, look_for_new_episodes=False, last_user_guid=None,
        last_user_date_formatted=None, take_file_links=None) -> RecordsDataType:
    rd: RecordsDataType = {
        'effective_page': curr_page,
        'perPageLimiter': 0,
        'itemCounter': 0,
        'noSearchItemCounter': 0,

        'channelLink': "",
        'chName': "",
        'title': [],
        'descrs': [],
        'guids': [],
        'pubDates': [],
        'pubDatesFormatted': [],
        'isNewEpisode': [],
        'recordUniqIds': [],
        'links': [],
        'durations': [],
        'rssNumbers': [],

        'lastDate': "",
        'globalLastPubDate': "",

        'lastGuid': "",
        'lastPubDate': "",
        'lastRecordTitle': "",
    }

    for channelDescr in root.getchildren():
        if channelDescr.tag == "link":
            pass
            # try:
            #     channel_link = quote(channelDescr.text, safe=":/?=")
            # except Exception:
            #     channel_link = channelDescr.text

        elif channelDescr.tag == "title":
            rd['chName'] = str(channelDescr.text)

        # получение lastDate из RSS в формате itunes
        elif channelDescr.tag in ["lastBuildDate", "pubDate"]:
            rd['lastDate'] = str(channelDescr.text)

        elif channelDescr.tag == "item":

            record_meta = channelDescr.getchildren()

            # Если поисковый режим, запоминаем оригинальный номер записи,
            # ищем заголовок и сравниваем с поиском
            if search_query is not None:
                rd['noSearchItemCounter'] += 1
                temp_title = None
                for record in record_meta:
                    if record.tag == "title":
                        temp_title = str(record.text)
                if temp_title is None or \
                        (search_query.lower() not in temp_title.lower()):
                    continue

            rd['itemCounter'] += 1

            if curr_page is not None and rd['itemCounter'] <= perPage * (curr_page - 1):  # страница есть и сейчас не та
                if look_for_new_episodes:
                    # проверяем на новизну эпизодов
                    temp_guid = "_"
                    temp_pub_date = ""
                    temp_title = ""
                    for record in record_meta:
                        if record.tag == "title":
                            temp_title = str(record.text)
                        elif record.tag == "pubDate":
                            temp_pub_date = str(record.text)
                            if rd['globalLastPubDate'] == "":
                                rd['globalLastPubDate'] = str(record.text)
                        elif record.tag == "guid":
                            temp_guid = str(record.text)

                    pgd = app.service.record.helpers.get_record_uniq_id(temp_guid, temp_pub_date, temp_title)
                    record_date_formatted = lib.tools.time_tools.general.prepare_date_time_from_formatted(temp_pub_date)
                    if (
                            pgd == last_user_guid
                            or last_user_date_formatted > record_date_formatted
                    ):
                        look_for_new_episodes = False
                continue

            elif (
                    rd['perPageLimiter'] < perPage  # текущая страница
                    or curr_page is None  # страница не установлена
            ):

                rd['title'].append("")
                rd['descrs'].append("")
                rd['guids'].append("")
                rd['pubDates'].append("")
                rd['pubDatesFormatted'].append("")
                rd['links'].append("")
                rd['durations'].append("")
                for record in record_meta:
                    if record.tag == "enclosure" and take_file_links:
                        try:
                            rd['links'][-1] = str(quote(record.attrib["url"], safe=":/?=_"))
                        except Exception:
                            pass
                    elif record.tag == "title":
                        rd['title'][-1] = str(record.text)
                        if rd['lastRecordTitle'] == "":
                            rd['lastRecordTitle'] = str(record.text)
                    elif record.tag == "description":
                        rd['descrs'][-1] = str(record.text)

                    elif record.tag == "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration":
                        rd['durations'][-1] = str(record.text)

                    elif record.tag == "pubDate":
                        rd['pubDates'][-1] = str(record.text)
                        try:
                            rd['pubDatesFormatted'][-1] = lib.tools.time_tools.general.format_rss_last_date(
                                str(record.text))
                        except Exception:
                            rd['pubDatesFormatted'][-1] = str(record.text)
                        if rd['lastPubDate'] == "":
                            # see in podcastUpdater.py
                            rd['lastPubDate'] = str(record.text)
                        if rd['globalLastPubDate'] == "":
                            rd['globalLastPubDate'] = str(record.text)
                    elif record.tag == "guid":
                        rd['guids'][-1] = str(record.text)
                        if rd['lastGuid'] == "":
                            rd['lastGuid'] = str(record.text)

                if search_query is not None:
                    rd['rssNumbers'].append(rd['noSearchItemCounter'])
                else:
                    rd['rssNumbers'].append(rd['itemCounter'])

                rd['recordUniqIds'].append(
                    app.service.record.helpers.get_record_uniq_id(rd['guids'][-1], rd['pubDates'][-1], rd['title'][-1]))
                record_date_formatted = lib.tools.time_tools.general.prepare_date_time_from_formatted(
                    rd['pubDates'][-1])
                # проверяем на новизну эпизодов
                if look_for_new_episodes:
                    if (
                            rd['recordUniqIds'][-1] == last_user_guid
                            or last_user_date_formatted > record_date_formatted
                    ):
                        rd['isNewEpisode'].append(False)
                        look_for_new_episodes = False
                    else:
                        rd['isNewEpisode'].append(True)
                else:
                    rd['isNewEpisode'].append(False)

                rd['perPageLimiter'] += 1
                if rd['perPageLimiter'] == perPage and search_query is None:
                    break

    return rd


def send_record(data: ControllerParams):
    call_data: RecDataType = json.loads(data['callback'].data) if data['callback'] is not None else {}
    if data['callback'] is None or ('dh_n' not in call_data
                                    and 'dh' not in call_data):  # Legacy support, remove later
        notify(data['callback'], data['message'], get_message_rtd(['errors', 'unknown'], data['language_code']))
        return

    try:
        notify(data['callback'], data['message'],
               get_message("needTimeToLoad", data['language_code']), False)
    except Exception:
        pass

    send_next_record = data['action_name'] == 'nrec'

    if 'dh_n' in call_data:
        hash_and_num = call_data['dh_n'].split('_')
        prev_hash = hash_and_num[0]
        from_num = int(hash_and_num[1]) - 1
    else:  # 'dh' in call_data:  # Legacy support, remove later TODO
        hash_and_num = call_data['dh'].split('_')
        prev_hash = hash_and_num[0]
        from_num = int(hash_and_num[1])

    channel: dict | None = None

    # Try to get from button
    if call_data.get('iid', None) is not None:
        channel = {'itunes_id': call_data['iid']}

    elif call_data.get('id', None) is not None:
        # If the podcast was added by rss or subscribed, it'll be in database
        db = SQLighter(db_path)
        channel = dict(db.get_channel(call_data['id']))
        db.close()

    if channel is None:
        podcast_state_data: PodcastStateData | None \
            = typing_cast(PodcastStateData, storage.get_user_state_data(data['chat_id'], 'podcast'))
        if (podcast_state_data is not None and
                podcast_state_data['service_id'] is not None):
            if podcast_state_data.get('service_name', None) == 'itunes':
                channel = {'itunes_id': podcast_state_data['service_id']}
            elif podcast_state_data.get('service_name', None) == 'rss':
                channel = {'rss_link': podcast_state_data['service_id']}

    send_record_direct(
        channel, data['chat_id'], data['language_code'], prev_hash, from_num, next_record=send_next_record)


def send_record_by_hash_using_start(data: ControllerParams, episode_data: dict):
    prev_hash = episode_data['prev_hash']
    from_num = episode_data['from_num']

    if 'service' in episode_data and episode_data['service'] == 'itunes':
        channel = {'itunes_id': episode_data['sId']}
    else:
        db = SQLighter(db_path)
        channel = dict(db.get_channel(episode_data['id']))
        db.close()

    send_record_direct(channel, data['chat_id'], data['language_code'], prev_hash, from_num)


def send_record_direct(
        channel: dict | None, chat_id: int, lang_code: str, prev_hash: str, from_num: int | None,
        next_record: bool = False
):
    if channel is None:
        render_messages(chat_id, [{
            'type': 'text', 'text': get_message('parsingError', lang_code),
            'reply_markup': go_back_inline_markup(lang_code)}])
        logger.warn("Channel is None for chat", chat_id)
        return

    if channel.get('itunes_id', None) is not None:
        payload = {'entity': 'podcast', 'id': channel['itunes_id']}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload)
        service_name = 'itunes'
        service_id = channel['itunes_id']
    elif channel.get('rss_link', None) is not None:
        payload = {'rss_link': channel['rss_link']}
        root, pc_info = app.service.podcast.podcast.podcast_info_query(payload, 'rss')
        service_name = 'rss'
        service_id = channel['rss_link']
    else:
        root = False
        pc_info = {}
        service_name = ""
        service_id = ""

    if root is False:
        logger.warn("PARSING ERROR! In recsModule/sendRecord2")
        render_messages(chat_id, [{
            'type': 'text', 'text': get_message("parsingError", lang_code)}])
        return

    i = 0
    record_info = {}
    newer_record_info = {}
    ch_name = ""
    channel_link = ""

    for channelDescr in root.getchildren():
        if channelDescr.tag == "item":
            i += 1

            # пропускаем первые x, чтобы не считать их хэш
            if from_num is not None and i < from_num:
                continue

            record_info = collect_record_info(channelDescr.getchildren())
            date_hash = sha256(
                record_info['recordUniqId'].encode('utf-8')
            ).hexdigest()[0:maxPodcastDateCallDataHexLen]
            # пока хэш отличается, пропускаем
            if date_hash != prev_hash:
                newer_record_info = record_info
                record_info = {}
                continue
            else:
                break
        elif channelDescr.tag == "link":
            try:
                channel_link = quote(channelDescr.text, safe=":/?=")
            except Exception:
                channel_link = channelDescr.text
        elif channelDescr.tag == "title":
            ch_name = str(channelDescr.text)

    if (
            (next_record and newer_record_info == {})  # берём следующую, но запись первая или данных нет
            or (not next_record and record_info == {})  # берём текущую, но данных нет
    ):
        render_messages(chat_id, [{
            'type': 'text', 'text': get_message("notFoundOrFuture", lang_code)}])
        return

    i -= 1
    if next_record:  # следующая запись
        record_info = newer_record_info

    itunes_link = pc_info['itunesLink']
    if itunes_link is None or itunes_link == "None":
        itunes_link = ""
    if channel_link is None or channel_link == "None":
        channel_link = ""

    link = record_info['link']

    if record_info['descr'] is None or record_info['descr'] == "None":
        record_info['descr'] = ""
    if record_info['title'] is None or record_info['title'] == "None":
        record_info['title'] = ""
    if record_info['pubDate'] is None or record_info['pubDate'] == "None":
        record_info['pubDate'] = ""

    descr = lib.markup.cleaner.html_mrkd_cleaner(record_info['descr'])
    title = lib.markup.cleaner.html_mrkd_cleaner(record_info['title'])
    pub_date = record_info['pubDate']
    ch_name = lib.markup.cleaner.html_mrkd_cleaner(ch_name)

    duration = record_info['duration']
    duration_sec = send_record_helper.transform_duration(duration)
    utglangs = {chat_id: lang_code}
    record_uniq_id = record_info['recordUniqId']

    bitratestg = {}
    db_users = SQLighter(db_path)
    user = db_users.get_user_by_tg(chat_id)
    db_users.close()
    if user['bitrate'] is not None:
        bitratestg[chat_id] = int(user['bitrate'])
    else:
        bitratestg[chat_id] = std_bitrate

    try:
        podcast_id = channel['id']
    except Exception:
        podcast_id = None

    podcast_info = {
        'id': podcast_id,
        'title': title,
        'descr': descr,
        'itunesLink': itunes_link,
        'channelLink': channel_link,
        'chName': ch_name,
        'pubDate': pub_date,
        'duration_sec': duration_sec,
        'service_name': service_name,
        'service_id': service_id,
        'with_next_ep_button': True,
        'recNum': i,
        'recordUniqId': record_uniq_id
    }

    t_podcast_sender.main_queue.put(
        {
            'action': 'rec', 'user_id': chat_id,
            'func_params': {
                'link': link, 'chat_ids': {chat_id: {}}, 'utglangs': utglangs,
                'bitratestg': bitratestg, 'podcastInfo': podcast_info}
        })


def send_record_thread(input_data, thonbot):
    sender = send_record_helper.Sender(
        thonbot,
        input_data['func_params']['link'],
        input_data['func_params']['chat_ids'],
        input_data['func_params']['utglangs'],
        input_data['func_params']['bitratestg'],
        input_data['func_params']['podcastInfo'], )
    sender.send_record()


def collect_record_info(channel_descr_children):
    result = {
        'link': '', 'descr': '', 'title': '',
        'pubDate': '', 'recordUniqId': '', 'duration': 0
    }
    guid = ""
    full_pub_date = ""
    for record in channel_descr_children:
        if record.tag == "enclosure":
            result['link'] = str(quote(record.attrib["url"], safe=":/?="))
        # link = record.attrib["url"]
        elif record.tag == "description":
            try:
                result['descr'] = str(record.text)
            except Exception:
                result['descr'] = record.text
        elif record.tag == "title":
            result['title'] = str(record.text)
        elif record.tag == "pubDate":
            try:
                result['pubDate'] = lib.tools.time_tools.general.format_rss_last_date(str(record.text))
            except Exception:
                result['pubDate'] = record.text
            full_pub_date = str(record.text)

        elif record.tag == "guid":
            guid = str(record.text)

        elif record.tag == "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration":
            result['duration'] = record.text
    # if link != "" and descr != "" and title != "":
    # 	flag = 1
    # needed to be set to 0. Don't know...

    result['recordUniqId'] = app.service.record.helpers.get_record_uniq_id(
        guid, full_pub_date, result['title'])

    return result
