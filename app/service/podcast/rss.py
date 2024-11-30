import cchardet
from lxml import etree

from lib.requests import requesterModule
from lib.tools.logger import logger

requester = requesterModule.Requester()


def get_rss_root(feed_url):
    headers_params = ['Usual', 'Empty']
    errors = []
    headers: None | dict
    for headers_code in headers_params:
        if headers_code == 'Usual':
            headers = None
        elif headers_code == 'Empty':
            headers = {}
        else:
            headers = None

        content_result = __load_rss_root(feed_url, headers)
        content = content_result['content']
        if content is not False:
            root_result = __parse_rss_root(content)
            root = root_result['root']
            if root is not False:
                return root

            errors.append(root_result['error'])
        else:
            errors.append(content_result['error'])

    print('; '.join(errors), flush=True)
    return False


def __load_rss_root(feedUrl, headers=None):
    # запрос
    try:
        request = requester.get(feedUrl, headers=headers, timeout=5)
    except Exception as e:
        return {'content': False, 'error': "mainf/parsing_error2: " + str(e) + "; feed_url: " + str(feedUrl)}

    # запрос не удался
    if not request.ok:
        return {
            'content': False,
            'error': "mainf/parsing_error3, result is not ok: " + str(request.status_code)
                     + ", feed_url: " + feedUrl
        }

    return {'content': request.content}


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
