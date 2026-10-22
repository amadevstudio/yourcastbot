# -*- coding: utf-8 -*-
"""HTTP that reaches the public internet only: feeds, episode files, covers, transcripts.

Those URLs come from feeds, and anyone can publish a feed (an RSS link, a
show listed on Apple or the Podcast Index). A feed naming a local service or
a cloud metadata address would have our server fetch it and send the answer
to a chat as an "episode". The check is on the
address the socket actually connected to, so a redirect or a name that
resolves to a private address once checked is refused too: every hop of a
redirect opens its own connection through these pools.

Refused: every address that is not global (private, loopback, link-local,
shared 100.64/10, reserved, multicast), IPv4 mapped into IPv6 included. The
refusal is a connection error, as a dead host is. Tests that serve feeds
from 127.0.0.1 call allow_private(True).
"""
import ipaddress

from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError

_allow_private = False


def allow_private(allowed: bool = True) -> None:
    """Tests only: let connections to local addresses through."""
    global _allow_private
    _allow_private = bool(allowed)


def is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(str(address).split('%', 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, 'ipv4_mapped', None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


def _checked(connection, sock):
    if _allow_private:
        return sock
    try:
        address = sock.getpeername()[0]
    except OSError:
        address = ''
    if not is_public(address):
        sock.close()
        raise NewConnectionError(connection, 'refused: %s is not a public address (%s)' % (
            address or 'unknown', connection.host))
    return sock


class _PublicHTTPConnection(HTTPConnection):
    def _new_conn(self):
        return _checked(self, super()._new_conn())


class _PublicHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        return _checked(self, super()._new_conn())


class _PublicHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PublicHTTPConnection


class _PublicHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PublicHTTPSConnection


class PublicOnlyAdapter(HTTPAdapter):
    """An HTTPAdapter whose connections reach public addresses only."""

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {'http': _PublicHTTPPool, 'https': _PublicHTTPSPool}


def session(**adapter_kwargs):
    """A requests.Session for URLs a feed named."""
    import requests
    public = requests.Session()
    adapter = PublicOnlyAdapter(**adapter_kwargs)
    public.mount('http://', adapter)
    public.mount('https://', adapter)
    return public
