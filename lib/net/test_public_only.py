# -*- coding: utf-8 -*-
"""Fetches of URLs a feed named reach public addresses only: a feed must not
have our server read a local service or a cloud metadata address
and send the answer to a chat. The check is on the connected socket, so a
name that resolves to a local address is refused too; tests that serve from
127.0.0.1 opt in with allow_private.

Run from the repo root: python lib/net/test_public_only.py
"""
import http.server
import os
import sys
import threading

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import requests  # noqa: E402

from lib.net import public_only  # noqa: E402
from lib.requests.requesterModule import Requester  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"local": "service"}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _refused(call) -> bool:
    try:
        call()
    except requests.exceptions.ConnectionError as e:
        return 'not a public address' in str(e)
    return False


def main():
    for address in ('127.0.0.1', '10.0.0.5', '192.168.1.1', '172.16.0.1', '169.254.169.254', '100.64.0.1',
                    '0.0.0.0', '::1', 'fe80::1', '::ffff:127.0.0.1', '224.0.0.1', 'not an ip', ''):
        _assert(not public_only.is_public(address), "%r is not public" % address)
    for address in ('93.184.216.34', '1.1.1.1', '2606:4700:4700::1111', '::ffff:8.8.8.8'):
        _assert(public_only.is_public(address), "%r is public" % address)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        for url in ('http://127.0.0.1:%d/internal' % port, 'http://localhost:%d/internal' % port):
            _assert(_refused(lambda: Requester(attempts=0, total_attempts=0).get(url, timeout=(2, 2))),
                    "a feed's URL at %s is refused (the requester: feeds, episodes, transcripts)" % url.split('/')[2])
        destination = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.public_only_test.bin')
        _assert(_refused(lambda: Requester(attempts=0, total_attempts=0).download_chunked(
            'http://127.0.0.1:%d/ep.mp3' % port, destination, timeout=(2, 2))) and not os.path.exists(destination),
                "an episode file at a local address is never downloaded")
        _assert(_refused(lambda: public_only.session().get('http://127.0.0.1:%d/cover.jpg' % port, timeout=(2, 2))),
                "nor a cover")
        public_only.allow_private(True)
        try:
            _assert(Requester(attempts=0, total_attempts=0).get(
                'http://127.0.0.1:%d/x' % port, timeout=(2, 2)).status_code == 200, "tests may opt in")
        finally:
            public_only.allow_private(False)
        _assert(requests.get('http://127.0.0.1:%d/x' % port, timeout=(2, 2)).status_code == 200,
                "other HTTP (the bot's own APIs) is untouched")
    finally:
        server.shutdown()

    class Sock:
        def __init__(self, peer):
            self.peer, self.closed = peer, False

        def getpeername(self):
            return (self.peer, 80)

        def close(self):
            self.closed = True
    connection = type('C', (), {'host': 'feeds.example.com'})()
    sock = Sock('169.254.169.254')
    try:
        public_only._checked(connection, sock)
        raise AssertionError("a name that resolved to the metadata address must be refused")
    except Exception as e:
        _assert('not a public address' in str(e) and sock.closed,
                "a public name that resolves to a local address is refused on the socket, which is closed")
    _assert(public_only._checked(connection, Sock('93.184.216.34')) is not None, "a public one goes")
    print("all public-only checks passed")


if __name__ == '__main__':
    main()
