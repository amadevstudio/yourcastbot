# -*- coding: utf-8 -*-
"""Enclosure (episode file) faults vs a dead feed.

Timeout/DNS is the host. 404 is one file. Do not cool a CDN for a single 404.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse, urlsplit

# After FAULTS_BEFORE_COOL timeouts from the same host, skip downloads for this long.
COOL_SECONDS = 30 * 60

# One timeout is often a hiccup: the NBC CDN missed a 15 s read once and
# answered in 0.9 s a minute later, but the host sat cooled for 30 minutes and
# the user's retaps were told "unavailable". A host is cooled only when it fails
# again, in another job, within the window. The failing job itself is terminal
# either way (audio_source_gone), so no MAX_ATTEMPTS are spent on it.
FAULTS_BEFORE_COOL = 2
FAULT_WINDOW_SECONDS = 10 * 60

# An enclosure URL rarely points at the CDN: dts.podtrac.com, pdst.fm and
# chrt.fm redirect (~13% of our links). Cooling the first host punishes every
# podcast behind that redirector, so cool the host that actually hung.
_ERROR_HOST_PATTERNS = (
    # requests/urllib3: "HTTPSConnectionPool(host='x.simplecastaudio.com', port=443): ..."
    re.compile(r"""host=['"]([^'"\s/]+)['"]"""),
    # urllib3 2.x resolver wording: "Failed to resolve 'x.simplecastaudio.com'"
    re.compile(r"""[Ff]ailed to resolve ['"]([^'"\s/]+)['"]"""),
)

# A tracker carries the target inside the path, plain
# (podtrac.com/pts/redirect.mp3/traffic.omny.fm/d/clips/...) or percent-encoded
# (m.cdn.firstory.me/track/ID/https%3A%2F%2Fcdn.firstory.me/...). These names
# are only used to look a cooldown key up, so a segment that merely looks like a
# host ("redirect.mp3") costs one miss and nothing else.
_HOST_IN_PATH = re.compile(r"(?<![\w.-])([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+)(?![\w-])")
# File names look like hosts ("redirect.mp3"). Keeping them would only cost a
# lookup that always misses, but the check runs per download.
_FILE_SUFFIXES = (
    "mp3", "m4a", "m4b", "mp4", "aac", "ogg", "oga", "opus", "wav", "flac",
    "webm", "mov", "jpg", "jpeg", "png", "webp", "xml", "json", "html",
)
MAX_URL_HOSTS = 8

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


def host_from_error(error) -> str | None:
    """The host that hung, as urllib3 names it in the message.

    A redirected download fails at the CDN, not at the redirector we asked.
    """
    if error is None:
        return None
    text = str(error)
    for pattern in _ERROR_HOST_PATTERNS:
        found = pattern.search(text)
        if found is None:
            continue
        host = found.group(1).strip().lower().rstrip(".")
        if host:
            return host
    return None


def enclosure_hosts(url) -> list[str]:
    """Hosts this URL can end at: its own plus the ones a tracker embedded.

    The cooldown is keyed by the host that died, which for a tracker link is
    not the host we connect to. Without this the 30-minute skip would quietly
    stop applying to every redirected podcast.
    """
    hosts = []
    first = host_from_url(url)
    if first:
        hosts.append(first)
    try:
        parts = urlsplit(str(url))
        rest = unquote(parts.path + ("?" + parts.query if parts.query else ""))
    except Exception:
        return hosts
    for candidate in _HOST_IN_PATH.findall(rest.lower()):
        if candidate.rsplit(".", 1)[-1] in _FILE_SUFFIXES:
            continue
        if candidate not in hosts:
            hosts.append(candidate)
            if len(hosts) >= MAX_URL_HOSTS:
                break
    return hosts


def enclosure_host_fault(error) -> bool:
    """CDN/DNS/connect died. Host cooldown applies."""
    text = str(error).lower()
    return any(snippet in text for snippet in _HOST_FAULT_SNIPPETS)
