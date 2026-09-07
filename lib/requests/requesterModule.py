import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning

STD_REQUEST_HEADERS = {
    # 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0)'
    # ' Gecko/20100101 Firefox/45.0'
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:80.0)'
                  ' Gecko/20100101 Firefox/80.0'
}


class Requester:
    def __init__(self, attempts=3, factor=0.005, insecure_warnings=False, request_headers=None,
                 total_attempts=None):
        if request_headers is None:
            request_headers = STD_REQUEST_HEADERS

        if not insecure_warnings:
            self.__disable_insecure_request_warning()

        retry_params = {'connect': attempts, 'backoff_factor': factor}
        # By default urllib3 allows up to 10 retries in total, which turns a slow
        # host into a multi-minute hang. Callers that need a bounded worst case
        # (e.g. the feed fetcher) pass total_attempts explicitly.
        if total_attempts is not None:
            retry_params['total'] = total_attempts
            retry_params['read'] = total_attempts

        retry = Retry(**retry_params)
        self.adapter = HTTPAdapter(max_retries=retry)

        self.headers = {
            "User-Agent": request_headers["User-Agent"]
        }

    def __disable_insecure_request_warning(self):
        urllib3.disable_warnings(category=InsecureRequestWarning)

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
            callback=None, chunk_size=1024, timeout=None):

        # Connect vs stall-between-chunks. A dead CDN must not occupy a rec
        # worker for minutes: urllib3 Retry(total=10) * 120s was 20+ minutes.
        if timeout is None:
            timeout = (10, 30)

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

    def get_headers(self, link, verify=False, headers=None, timeout=None):
        # HEAD with no timeout hangs a rec worker forever: heartbeat keeps the
        # lease, new clicks stay pending, and the user never gets a status
        # message (that is sent only after prepare() returns).
        if timeout is None:
            timeout = (10, 10)
        session = self.__get_session()
        session_headers = self.__decide_request_headers(headers)
        response = session.head(
            link, verify=verify, allow_redirects=True,
            headers=session_headers, timeout=timeout)
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
