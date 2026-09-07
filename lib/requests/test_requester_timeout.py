# -*- coding: utf-8 -*-
"""HTTP timeouts for rec downloads. A hanging origin must not occupy a worker.

Run from the repo root: python lib/requests/test_requester_timeout.py
"""
import os
import socket
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.requests.requesterModule import Requester  # noqa: E402


def _assert_true(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _hanging_port():
    """Accept TCP, never send an HTTP response."""
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 0))
    sock.listen(5)
    port = sock.getsockname()[1]

    def serve():
        try:
            while True:
                conn, _addr = sock.accept()
                try:
                    time.sleep(30)
                finally:
                    conn.close()
        except Exception:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return sock, port


def test_retry_bounds():
    bounded = Requester(attempts=0, total_attempts=0)
    retry = bounded.adapter.max_retries
    _assert_true(retry.total == 0, "sender requester total retries is 0")
    _assert_true(retry.read == 0, "sender requester read retries is 0")

    unbounded = Requester()
    _assert_true(
        unbounded.adapter.max_retries.total == 10,
        "default urllib3 total retries is still 10 (feed/sender must opt out)")


def test_head_timeout():
    sock, port = _hanging_port()
    try:
        requester = Requester(attempts=0, total_attempts=0)
        started = time.time()
        raised = False
        try:
            requester.get_headers(
                'http://127.0.0.1:%s/hang' % port, timeout=(0.4, 0.4))
        except Exception:
            raised = True
        elapsed = time.time() - started
        _assert_true(raised, "get_headers raises when the origin never answers")
        _assert_true(
            elapsed < 3.0,
            "get_headers returns in under 3s, not hung (got %.2fs)" % elapsed)
    finally:
        sock.close()


def test_download_timeout():
    sock, port = _hanging_port()
    dest = os.path.join(_ROOT, 'lib', 'requests', '_timeout_test.bin')
    try:
        requester = Requester(attempts=0, total_attempts=0)
        started = time.time()
        raised = False
        try:
            requester.download_chunked(
                'http://127.0.0.1:%s/hang' % port,
                dest,
                timeout=(0.4, 0.4))
        except Exception:
            raised = True
        elapsed = time.time() - started
        _assert_true(
            raised, "download_chunked raises when the origin never answers")
        _assert_true(
            elapsed < 3.0,
            "download_chunked returns in under 3s, not hung (got %.2fs)" % elapsed)
    finally:
        sock.close()
        try:
            os.remove(dest)
        except OSError:
            pass


def main():
    test_retry_bounds()
    test_head_timeout()
    test_download_timeout()
    print("all requester timeout tests passed")


if __name__ == '__main__':
    main()
