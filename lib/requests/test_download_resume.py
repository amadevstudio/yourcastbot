# -*- coding: utf-8 -*-
"""A big download that stalls resumes from the byte it stopped at; a dead CDN
still fails fast.

A 670 MB TED video timed out once on a 30 s quiet read and the user got
"unavailable", while a 137 MB one from the same CDN had just downloaded.
Loopback server only.

Run from the repo root: python lib/requests/test_download_resume.py
"""
import http.server
import os
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.requests.requesterModule import Requester  # noqa: E402

BODY = bytes(range(256)) * 400          # 102400 bytes
ETAG = '"v1"'
TIMEOUT = (1.0, 0.4)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


class _Server:
    """`script` is a list of behaviours, one per request, in order."""

    def __init__(self, script, honour_range=True):
        outer = self
        self.script = list(script)
        self.requests = []
        self.honour_range = honour_range

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.requests.append(self.headers.get("Range"))
                step = outer.script.pop(0) if outer.script else "full"
                rng = self.headers.get("Range")
                start = 0
                if rng and outer.honour_range:
                    start = int(rng.split("=")[1].split("-")[0])
                    self.send_response(206)
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (
                        start, len(BODY) - 1, len(BODY)))
                else:
                    self.send_response(200)
                body = BODY[start:]
                self.send_header("Content-Length", str(len(body)))
                self.send_header("ETag", ETAG)
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                if step == "full":
                    self.wfile.write(body)
                elif step == "half":              # half the body, then silence
                    self.wfile.write(body[:len(body) // 2])
                    self.wfile.flush()
                    time.sleep(2)
                elif step == "silent":            # headers, then nothing
                    self.wfile.flush()
                    time.sleep(2)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.handle_error = lambda *args: None  # the client hangs up on purpose
        self.url = "http://127.0.0.1:%d/big.mp4" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _download(server):
    path = os.path.join(tempfile.mkdtemp(prefix="yourcast_resume_"), "f.bin")
    seen = []
    error = None
    started = time.time()
    try:
        Requester(attempts=0, total_attempts=0).download_chunked(
            server.url, path, chunk_size=4096, timeout=TIMEOUT,
            callback=lambda done, total: seen.append((done, total)))
    except Exception as e:
        error = e
    data = open(path, "rb").read() if os.path.exists(path) else b""
    return data, error, seen, time.time() - started


def main():
    s = _Server(["half", "full"])
    data, error, seen, _ = _download(s)
    _assert_eq((data == BODY, error), (True, None), "a stall in the middle resumes and the file is whole")
    _assert_eq(len(s.requests), 2, "one resume")
    _assert_eq(s.requests[1].startswith("bytes=") and not s.requests[1].startswith("bytes=0-"),
               True, "the resume is a Range request")
    _assert_eq(seen[-1], (len(BODY), len(BODY)), "progress counts real bytes")
    s.close()

    s = _Server(["half", "half", "full"])
    data, error, _, _ = _download(s)
    _assert_eq((data == BODY, error), (True, None), "two stalls in a row still finish")
    s.close()

    s = _Server(["silent", "full"])
    data, error, _, _ = _download(s)
    _assert_eq((data == BODY, error), (True, None), "silence before the first byte gets one more plain GET")
    _assert_eq(s.requests, [None, None], "that retry is not a Range request")
    s.close()

    s = _Server(["silent", "silent", "full"])
    data, error, _, elapsed = _download(s)
    _assert_eq(error is not None, True, "a CDN silent twice fails")
    _assert_eq(len(s.requests), 2, "no third try")
    _assert_eq(elapsed < 4, True, "and fast (%.1fs)" % elapsed)
    s.close()

    s = _Server(["half", "silent", "full"])
    data, error, _, _ = _download(s)
    _assert_eq(error is not None, True, "a resume that brings no bytes is the last")
    _assert_eq(len(s.requests), 2, "no third try after an empty resume")
    s.close()

    s = _Server(["half", "full"], honour_range=False)
    data, error, _, _ = _download(s)
    _assert_eq(error is not None, True, "a server that ignores Range is not appended to")
    s.close()
    print("all download resume checks passed")


if __name__ == "__main__":
    main()
