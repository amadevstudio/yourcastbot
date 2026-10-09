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

    # A stall in the middle of a big file (a 670 MB video from a CDN that
    # went quiet for 30 s) is resumed from the byte it stopped at, not failed.
    # Bounded: a retry that brought no bytes is the last one, and a stall
    # before the first byte gets exactly one more plain GET, so a CDN that is
    # really dead still ends the job after two quiet read-timeouts.
    MAX_RESUMES = 3

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

        try:
            file_size = int(r.headers.get("Content-Length"))
        except Exception:
            # The value may be empty (eq None)
            file_size = None
        # Same file or no resume: If-Range makes the server answer 200 (the
        # whole file) when it changed, and that is not appended.
        validator = r.headers.get("ETag") or r.headers.get("Last-Modified")
        can_resume = "bytes" in str(r.headers.get("Accept-Ranges", "")).lower() \
            and file_size is not None and r.headers.get("Content-Encoding") is None

        r.raise_for_status()
        downloaded = 0
        resumes = 0
        with open(destination, 'wb') as f:
            while True:
                before = downloaded
                try:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback is not None:
                            callback(downloaded, file_size)
                    r.close()
                    return
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.Timeout):
                    r.close()
                    progressed = downloaded > before
                    first_quiet_start = downloaded == 0 and resumes == 0
                    if resumes >= self.MAX_RESUMES or not (progressed or first_quiet_start):
                        raise
                    if downloaded == 0:
                        # Not a byte yet: one more plain GET, same as the first.
                        r = self.__reopen(session, url_base, session_headers, verify, timeout)
                    elif can_resume and validator and downloaded < file_size:
                        r = self.__reopen(
                            session, url_base, session_headers, verify, timeout,
                            offset=downloaded, validator=validator)
                    else:
                        raise
                    resumes += 1
                    if r is None:
                        raise

    def __reopen(self, session, url, base_headers, verify, timeout, offset=0, validator=None):
        """GET again (from `offset` when given). None unless the answer is the one
        wanted: 206 starting at `offset`, or 200 for a restart from zero."""
        headers = dict(base_headers)
        if offset:
            headers["Range"] = "bytes=%d-" % offset
            headers["If-Range"] = validator
        try:
            r = session.get(
                url, headers=headers, verify=verify, stream=True,
                timeout=timeout, allow_redirects=True)
        except requests.exceptions.RequestException:
            return None
        if offset:
            ok = r.status_code == 206 and str(r.headers.get("Content-Range", "")).startswith(
                "bytes %d-" % offset)
        else:
            ok = r.status_code == 200
        if not ok:
            r.close()
            return None
        return r

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
