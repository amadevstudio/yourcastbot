import time
import typing

import cchardet
from lxml import etree

from lib.requests import requesterModule
from lib.tools.logger import logger

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
FeedStatus = typing.Literal['ok', 'gone', 'unavailable']
# фид получен и разобран
FEED_STATUS_OK: FeedStatus = 'ok'
# фид точно больше не существует: сервер ответил 404/410
FEED_STATUS_GONE: FeedStatus = 'gone'
# сеть, таймаут, 5xx, 403/429, битый xml — ошибка может быть временной
FEED_STATUS_UNAVAILABLE: FeedStatus = 'unavailable'

# коды, по которым считаем, что фида больше нет
FEED_GONE_STATUS_CODES = (404, 410)

HEADERS_PARAMS = ['Usual', 'Empty']


def get_rss_root(feed_url):
    root, _status = get_rss_root_with_status(feed_url)
    return root


def get_rss_root_with_status(feed_url) -> typing.Tuple[typing.Any, FeedStatus]:
    """Возвращает (root, status).

    root — разобранный фид либо False.
    status — FEED_STATUS_OK / FEED_STATUS_GONE / FEED_STATUS_UNAVAILABLE.
    Вызывающий код должен различать 'gone' (фида больше нет)
    и 'unavailable' (могло просто моргнуть), чтобы не наказывать
    пользователей за разовый сбой сети.
    """
    errors: list[str] = []
    statuses: list[FeedStatus] = []

    for retry_round in range(FEED_RETRY_ROUNDS):
        if retry_round > 0:
            time.sleep(FEED_RETRY_PAUSE_SECONDS)

        round_statuses: list[FeedStatus] = []

        for headers_code in HEADERS_PARAMS:
            headers: None | dict
            if headers_code == 'Empty':
                headers = {}
            else:
                headers = None

            content_result = __load_rss_root(feed_url, headers)
            content = content_result['content']
            if content is not False:
                root_result = __parse_rss_root(content)
                root = root_result['root']
                if root is not False:
                    return root, FEED_STATUS_OK

                errors.append(root_result['error'])
                # ответ получили, но это не rss: может быть страница-заглушка,
                # капча или временная ошибка площадки
                round_statuses.append(FEED_STATUS_UNAVAILABLE)
            else:
                errors.append(content_result['error'])
                round_statuses.append(content_result['status'])

        statuses += round_statuses

        # сервер явно говорит, что фида больше нет — повторять смысла нет
        if all(status == FEED_STATUS_GONE for status in round_statuses):
            break

    print('; '.join(errors), flush=True)

    if statuses and all(status == FEED_STATUS_GONE for status in statuses):
        return False, FEED_STATUS_GONE

    return False, FEED_STATUS_UNAVAILABLE


def __load_rss_root(feed_url, headers=None):
    # запрос
    try:
        request = feed_requester.get(feed_url, headers=headers, timeout=FEED_REQUEST_TIMEOUT)
    except Exception as e:
        return {
            'content': False,
            'status': FEED_STATUS_UNAVAILABLE,
            'error': "mainf/parsing_error2: " + str(e) + "; feed_url: " + str(feed_url)
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
            'error': "mainf/parsing_error3, result is not ok: " + str(request.status_code)
                     + ", feed_url: " + feed_url
        }

    return {'content': request.content, 'status': FEED_STATUS_OK}


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
