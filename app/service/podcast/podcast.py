import json
from typing import TypedDict, Dict, Tuple, Literal
from urllib.parse import unquote, quote

from app.service.podcast.rss import (
    get_rss_root_with_status,
    FeedStatus, FEED_STATUS_GONE, FEED_STATUS_UNAVAILABLE,
    FEED_STATUS_NOT_MODIFIED)
from lib.requests import requesterModule
from lib.tools.logger import logger
from lib.tools.time_tools.general import format_rss_last_date, prepare_date_time_from_formatted

requester = requesterModule.Requester()

ITUNES_REQUEST_TIMEOUT = (5, 15)  # (connect, read)


class RootAdapter:
    def __init__(self):
        self.children: list[RootAdapter] = []

    def getchildren(self):
        return self.children


class PodcastInfoType(TypedDict, total=False):
    lastDate: None | str
    itunesLink: None | str
    feedUrl: str | bool
    collectionName: None | str
    itunesData: Dict | None
    # почему выборка не удалась: FEED_STATUS_GONE | FEED_STATUS_UNAVAILABLE
    failureReason: FeedStatus
    http_etag: str | None
    http_last_modified: str | None
    notModified: bool


def _channel_field(channel, key, default=None):
    try:
        value = channel[key]
    except (KeyError, IndexError, TypeError):
        return default
    if value is None or value == '':
        return default
    return value


def fetch_channel_feed(channel, manual=False):
    """Выборка фида канала для апдейтера.

    Scheduled (manual=False): наш rss_link + сохранённые HTTP-валидаторы.
    iTunes — только если rss_link пустой.
    Ручная кнопка «обновить» оставляет itunes-then-rss, но валидаторы
    всё равно уходят на GET RSS.
    """
    etag = _channel_field(channel, 'http_etag')
    last_modified = _channel_field(channel, 'http_last_modified')
    rss_link = _channel_field(channel, 'rss_link')
    itunes_id = _channel_field(channel, 'itunes_id')

    if not manual and rss_link:
        root, pc_info = podcast_info_query(
            {'rss_link': rss_link}, 'rss',
            etag=etag, last_modified=last_modified)
        return root, pc_info, 'rss', rss_link

    root: RootAdapter | Literal[False] = False
    pc_info: PodcastInfoType = {}
    service_name: str | None = None
    service_id = None

    if itunes_id:
        payload = {'entity': 'podcast', 'id': itunes_id}
        root, pc_info = podcast_info_query(
            payload, etag=etag, last_modified=last_modified)
        service_name = 'itunes'
        service_id = itunes_id
    if (
            root is False
            and not pc_info.get('notModified')
            and rss_link
    ):
        root, pc_info = podcast_info_query(
            {'rss_link': rss_link}, 'rss',
            etag=etag, last_modified=last_modified)
        service_name = 'rss'
        service_id = rss_link

    return root, pc_info, service_name, service_id


def podcast_info_query(
        payload, service_name='itunes', direct_link=False,
        etag=None, last_modified=None) \
        -> Tuple[RootAdapter | Literal[False], PodcastInfoType]:
    if service_name == 'itunes':
        api_url_base = 'https://itunes.apple.com/lookup'
        try:
            response = requester.get(api_url_base, params=payload, timeout=ITUNES_REQUEST_TIMEOUT)
        except Exception as e:
            # сеть до itunes могла моргнуть; раньше исключение улетало наверх
            # и роняло поток апдейтера
            logger.warn("Itunes request failed: ", payload, "; error: ", e)
            return False, {'failureReason': FEED_STATUS_UNAVAILABLE}

        # if response.status_code == 200:
        # 	return json.loads(response.content.decode('utf-8'))
        # else:
        # 	return None

        # firstResult = json.loads(response.content.decode('utf-8'))["results"][0]
        # Получение первого результата с feedUrl для выборки по id
        try:
            itunes_json = json.loads(response.content.decode('utf-8'))["results"]
        except Exception as e:
            print("mainf/parsing_error1: ", e, "; payload: ", payload, flush=True)
            return False, {'failureReason': FEED_STATUS_UNAVAILABLE}

        feed_url: str | bool = ""
        collection_name = ""
        last_date = None
        itunes_link = None

        itunes_podcast_data = None
        for result in itunes_json:
            if "feedUrl" in result:
                result["feedUrl"] = unquote(result["feedUrl"])

                collection_name = result["collectionName"]
                feed_url = result["feedUrl"]
                last_date = result.get("releaseDate", None)
                itunes_link = quote(result["collectionViewUrl"], safe=":/")

                itunes_podcast_data = result
                break

    elif service_name == 'rss':
        last_date = None
        itunes_link = None
        feed_url = payload["rss_link"]
        collection_name = None
        itunes_podcast_data = None

    else:
        last_date = None
        itunes_link = None
        feed_url = False
        collection_name = None
        itunes_podcast_data = None

    if not feed_url or feed_url == "":
        logger.warn("Feed url is empty: ", payload)
        # itunes ответил, но подкаста в выдаче нет. Это может быть и снятие
        # подкаста с публикации, и временный сбой выдачи, поэтому — unavailable:
        # решение о выключении уведомлений принимается по счётчику неудач.
        return False, {
            "collectionName": collection_name,
            'failureReason': FEED_STATUS_UNAVAILABLE}

    feed_url = str(feed_url)

    root, feed_status, validators = get_rss_root_with_status(
        feed_url, etag=etag, last_modified=last_modified)
    if (
            root is False
            and feed_status != FEED_STATUS_NOT_MODIFIED
            and "www." in feed_url
            and not direct_link
    ):
        feed_url = feed_url.replace("www.", "")
        root, feed_status, validators = get_rss_root_with_status(
            feed_url, etag=etag, last_modified=last_modified)

    http_etag = validators.get('etag') if validators else None
    http_last_modified = validators.get('last_modified') if validators else None

    if feed_status == FEED_STATUS_NOT_MODIFIED:
        return False, {
            'lastDate': last_date,
            'itunesLink': itunes_link,
            'feedUrl': feed_url,
            'collectionName': collection_name,
            'itunesData': itunes_podcast_data,
            'http_etag': http_etag,
            'http_last_modified': http_last_modified,
            'notModified': True}

    if root is False:
        logger.warn("Error payload info: ", payload, "; reason: ", feed_status)
        return False, {
            'collectionName': collection_name,
            'failureReason': (
                FEED_STATUS_GONE if feed_status == FEED_STATUS_GONE
                else FEED_STATUS_UNAVAILABLE),
            'http_etag': http_etag,
            'http_last_modified': http_last_modified}

    return root, {
        'lastDate': last_date, 'itunesLink': itunes_link,
        'feedUrl': feed_url, 'collectionName': collection_name,
        'itunesData': itunes_podcast_data,
        'http_etag': http_etag,
        'http_last_modified': http_last_modified}


def set_last_date(last_date, last_pub_date) -> str:  # strings: itunes, rss; not formatted
    if last_date:
        last_date = format_rss_last_date(last_date)
        if not last_pub_date:
            return last_date
    if last_pub_date:
        last_pub_date = format_rss_last_date(last_pub_date)
        if not last_date:
            return last_pub_date

    if last_date and last_pub_date:
        if prepare_date_time_from_formatted(last_date) \
                < prepare_date_time_from_formatted(last_pub_date):
            return last_pub_date
        else:
            return last_date

    return ''


def prepare_podcast_update_time(input_date) -> str:
    return (input_date.split('T'))[0]


def prepare_string_from_rss(rss_string) -> str:
    result = ""
    try:
        result = rss_string.replace("\n", "").strip()
    except Exception:
        result = rss_string
    return result
