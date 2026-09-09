# -*- coding: utf-8 -*-
"""Enclosure (episode file) faults vs a dead feed.

Timeout/DNS is the host. 404 is one file. Do not cool a CDN for a single 404.
"""
from __future__ import annotations

from urllib.parse import urlparse

# After N timeouts from the same host, skip downloads for this long.
COOL_SECONDS = 30 * 60

_HOST_FAULT_SNIPPETS = (
    "read timed out",
    "readtimeout",
    "connecttimeout",
    "connection timed out",
    "max retries exceeded",
    "failed to establish a new connection",
    "name or service not known",
    "no address associated with hostname",
    "temporary failure in name resolution",
    "nodename nor servname",
    "connection refused",
    "network is unreachable",
)


def host_from_url(url) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(str(url)).hostname or "").strip().lower()
    except Exception:
        return None
    return host or None


def enclosure_host_fault(error) -> bool:
    """CDN/DNS/connect died. Host cooldown applies."""
    text = str(error).lower()
    return any(snippet in text for snippet in _HOST_FAULT_SNIPPETS)
