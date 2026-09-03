import time
import typing

import cchardet
from lxml import etree

from lib.requests import requesterModule
from lib.requests.requesterModule import STD_REQUEST_HEADERS

requester = requesterModule.Requester()

# Отдельный реквестер для фидов: свои ретраи мы делаем сами (см. FEED_RETRY_ROUNDS),
# поэтому urllib3-ретраи выключены — иначе одна медленная площадка
# висит по две минуты и тормозит весь круг обновления.
feed_requester = requesterModule.Requester(attempts=0, total_attempts=0)

# (connect, read)
FEED_REQUEST_TIMEOUT = (5, 10)
# сколько раз повторить полный цикл попыток при временной ошибке
FEED_RETRY_ROUNDS = 2
FEED_RETRY_PAUSE_SECONDS = 3

# Статусы выборки фида.
FeedStatus = typing.Literal['ok', 'gone', 'unavailable', 'not_modified']
# фид получен и разобран
FEED_STATUS_OK: FeedStatus = 'ok'
# фид точно больше не существует: сервер ответил 404/410
FEED_STATUS_GONE: FeedStatus = 'gone'
# сеть, таймаут, 5xx, 403/429, битый xml — ошибка может быть временной
FEED_STATUS_UNAVAILABLE: FeedStatus = 'unavailable'
# HTTP 304: тело не менялось, парсить нечего
FEED_STATUS_NOT_MODIFIED: FeedStatus = 'not_modified'

# коды, по которым считаем, что фида больше нет
FEED_GONE_STATUS_CODES = (404, 410)

HEADERS_PARAMS = ['Usual', 'Empty']


class FeedValidators(typing.TypedDict):
    etag: str | None
    last_modified: str | None


def empty_validators(
        etag: str | None = None,
        last_modified: str | None = None) -> FeedValidators:
    return {'etag': etag, 'last_modified': last_modified}


def feed_status_counts_as_failure(status: FeedStatus) -> bool:
    # 304 — фид доступен и не изменился; в счётчик FEED_FAILURES не идёт
    return status in (FEED_STATUS_GONE, FEED_STATUS_UNAVAILABLE)


def get_rss_root(feed_url, etag=None, last_modified=None):
    root, _status, _validators = get_rss_root_with_status(
        feed_url, etag=etag, last_modified=last_modified)
    return root


def get_rss_root_with_status(
        feed_url, etag=None, last_modified=None
) -> typing.Tuple[typing.Any, FeedStatus, FeedValidators]:
    """Возвращает (root, status, validators).

    root — разобранный фид либо False.
    status — ok / gone / unavailable / not_modified.
    validators — ETag и Last-Modified с финального ответа (после редиректов).

    304 не ретраим и не считаем ошибкой: тела нет, парсить нечего.
    Вызывающий код должен различать 'gone' (фида больше нет)
    и 'unavailable' (могло просто моргнуть), чтобы не наказывать
    пользователей за разовый сбой сети.
    """
    errors: list[str] = []
    statuses: list[FeedStatus] = []
    last_validators = empty_validators(etag, last_modified)

    for retry_round in range(FEED_RETRY_ROUNDS):
        if retry_round > 0:
            time.sleep(FEED_RETRY_PAUSE_SECONDS)

        round_statuses: list[FeedStatus] = []

        for headers_code in HEADERS_PARAMS:
            headers = __headers_for_attempt(headers_code, etag, last_modified)

            content_result = __load_rss_root(feed_url, headers, etag, last_modified)
            last_validators = content_result.get('validators') or last_validators
            content = content_result['content']
            load_status = content_result['status']

            if load_status == FEED_STATUS_NOT_MODIFIED:
                return False, FEED_STATUS_NOT_MODIFIED, last_validators

            if content is not False:
                root_result = __parse_rss_root(content)
                root = root_result['root']
                if root is not False:
                    return root, FEED_STATUS_OK, last_validators

                errors.append(root_result['error'])
                # ответ получили, но это не rss: может быть страница-заглушка,
                # капча или временная ошибка площадки
                round_statuses.append(FEED_STATUS_UNAVAILABLE)
            else:
                errors.append(content_result['error'])
                round_statuses.append(load_status)

        statuses += round_statuses

        # сервер явно говорит, что фида больше нет — повторять смысла нет
        if all(status == FEED_STATUS_GONE for status in round_statuses):
            break

    print('; '.join(errors), flush=True)

    if statuses and all(status == FEED_STATUS_GONE for status in statuses):
        return False, FEED_STATUS_GONE, last_validators

    return False, FEED_STATUS_UNAVAILABLE, last_validators


def __headers_for_attempt(headers_code, etag, last_modified) -> dict:
    if headers_code == 'Empty':
        headers = {}
    else:
        headers = dict(STD_REQUEST_HEADERS)

    if etag:
        headers['If-None-Match'] = etag
    if last_modified:
        headers['If-Modified-Since'] = last_modified
    return headers


def __validators_from_response(request, fallback_etag=None, fallback_last_modified=None,
                               keep_fallback=False) -> FeedValidators:
    etag = request.headers.get('ETag')
    last_modified = request.headers.get('Last-Modified')
    if keep_fallback:
        if not etag:
            etag = fallback_etag
        if not last_modified:
            last_modified = fallback_last_modified
    return empty_validators(etag, last_modified)


def __load_rss_root(feed_url, headers=None, etag=None, last_modified=None):
    # запрос
    try:
        request = feed_requester.get(feed_url, headers=headers, timeout=FEED_REQUEST_TIMEOUT)
    except Exception as e:
        return {
            'content': False,
            'status': FEED_STATUS_UNAVAILABLE,
            'validators': empty_validators(etag, last_modified),
            'error': "mainf/parsing_error2: " + str(e) + "; feed_url: " + str(feed_url)
        }

    # 304: requests считает ok (status < 400), но тела нет — не парсим.
    if request.status_code == 304:
        return {
            'content': False,
            'status': FEED_STATUS_NOT_MODIFIED,
            'validators': __validators_from_response(
                request, etag, last_modified, keep_fallback=True),
            'error': None
        }

    # запрос не удался
    if not request.ok:
        if request.status_code in FEED_GONE_STATUS_CODES:
            status = FEED_STATUS_GONE
        else:
            # 5xx, 403, 429 и прочее — площадка может лечь на время
            status = FEED_STATUS_UNAVAILABLE

        return {
            'content': False,
            'status': status,
            'validators': empty_validators(etag, last_modified),
            'error': "mainf/parsing_error3, result is not ok: " + str(request.status_code)
                     + ", feed_url: " + feed_url
        }

    return {
        'content': request.content,
        'status': FEED_STATUS_OK,
        'validators': __validators_from_response(request, keep_fallback=False),
        'error': None
    }


def __parse_rss_root(content):
    # парсинг xml
    try:
        root = etree.fromstring(content).getchildren()[0]
    except Exception:
        try:
            # попытка передекодировать
            result_data = content
            char_coding_desired = 'UTF-8'
            encoding = cchardet.detect(result_data)['encoding']
            if encoding is None:
                encoding = "UTF-8"
            if char_coding_desired != encoding:
                result_data = result_data.decode(encoding).encode(char_coding_desired)
            root = etree.fromstring(result_data).getchildren()[0]
        except Exception as e:
            return {'root': False, 'error': "mainf/parsing_error (fully): " + str(e)}

    return {'root': root}
