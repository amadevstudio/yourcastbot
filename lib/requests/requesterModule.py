from urllib.parse import unquote

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning

STD_REQUEST_HEADERS = {
    # 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0)'
    # ' Gecko/20100101 Firefox/45.0'
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:80.0)'
                  ' Gecko/20100101 Firefox/80.0'
}


class Requester:
    def __init__(self, attempts=3, factor=0.005, insecure_warnings=False, request_headers=None):
        if request_headers is None:
            request_headers = STD_REQUEST_HEADERS

        if not insecure_warnings:
            self.__disable_insecure_request_warning()

        retry = Retry(connect=attempts, backoff_factor=factor)
        self.adapter = HTTPAdapter(max_retries=retry)

        self.headers = {
            "User-Agent": request_headers["User-Agent"]
        }

    def __disable_insecure_request_warning(self):
        requests.packages.urllib3.disable_warnings(
            category=InsecureRequestWarning)

    def __get_session(self):
        session = requests.Session()
        session.mount('http://', self.adapter)
        session.mount('https://', self.adapter)
        return session

    def __decide_request_headers(self, headers):
        if headers is not None:
            return headers
        else:
            return self.headers

    # response = requests.get(api_url_base, params=payload)
    def get(self, url_base, params={}, verify=False, headers=None, timeout=None):
        session = self.__get_session()
        session_headers = self.__decide_request_headers(headers)
        return session.get(
            url_base, params=params, verify=verify, headers=session_headers, allow_redirects=True, timeout=timeout)

    def download_chunked(
            self, url_base, destination, verify=False, stream=True, headers=None,
            callback=None, chunk_size=1024):

        #  giving a server 30 seconds before answer and 2 minutes before sending data
        timeout = (30, 120)

        session_headers = self.__decide_request_headers(headers)

        session = self.__get_session()

        r = session.get(
            url_base, headers=session_headers, verify=verify, stream=stream,
            timeout=timeout, allow_redirects=True)

        headers = r.headers
        try:
            file_size = int(headers.get("Content-Length"))
        except Exception as e:
            # The value may be empty (eq None)
            file_size = None

        r.raise_for_status()
        with open(destination, 'wb') as f:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=chunk_size):
                # If you have chunk encoded response uncomment if
                # and set chunk_size parameter to None.
                # if chunk:
                f.write(chunk)

                downloaded += chunk_size
                if callback is not None:
                    callback(downloaded, file_size)
        r.close()

    def get_headers(self, link, verify=False, headers=None):
        # req = urllib.request.Request(link)
        # req.add_header('User-Agent', headers['User-Agent'])
        # site = urllib.request.urlopen(req)
        # meta = site.info()
        session = self.__get_session()
        session_headers = self.__decide_request_headers(headers)
        response = session.head(unquote(link), verify=verify, allow_redirects=True, headers=session_headers)
        return response.headers

    def get_headers_with_pre_download(self, link, verify=False, headers=None):
        timeout = (10, 10)
        session_headers = self.__decide_request_headers(headers)
        session = self.__get_session()
        r = session.get(
            link, headers=session_headers, verify=verify, stream=True,
            timeout=timeout, allow_redirects=True)
        r.close()

        return r.headers
