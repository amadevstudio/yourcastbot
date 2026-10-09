# -*- coding: utf-8 -*-
"""How fast the updater's circle may go: polite to each host, not slow to all.

The circle used to sleep 6 s after every fully fetched feed, whatever the
host. About 550 channels are fetched in full per circle (the other ~1800 answer
304), so ~55 minutes of a circle of ~58 were sleeping. What that pause
protects is a host not being hit again and again; that is a per-host rule:

- a host is fetched in full at most once per HOST_GAP_SECONDS;
- any two full fetches are at least ANY_GAP_SECONDS apart (no burst);
- a circle starts at most once per MIN_CIRCLE_PERIOD_SECONDS, so a faster
  circle does not mean more requests to the feed hosts (the circle was ~58 min
  plus a 10 min rest; a 10 min circle must not be followed by 10 min).

Only a full fetch counts, as before: 304s and channels without recipients
never slept. No imports from the bot: the CD gate runs this bare.
"""
import time
from urllib.parse import urlsplit

HOST_GAP_SECONDS = 6.0
ANY_GAP_SECONDS = 1.0
MIN_CIRCLE_PERIOD_SECONDS = 60 * 60


def feed_host(url) -> str:
    """The host a feed URL is fetched from ('' when there is none)."""
    try:
        return (urlsplit(str(url or "").strip()).hostname or "").lower()
    except ValueError:
        return ""


class HostPacer:
    """wait(url) before touching a feed, fetched(url) after a full fetch."""

    def __init__(self, host_gap=HOST_GAP_SECONDS, any_gap=ANY_GAP_SECONDS,
                 clock=time.monotonic, sleep=time.sleep):
        self.host_gap = host_gap
        self.any_gap = any_gap
        self._clock = clock
        self._sleep = sleep
        self._last_by_host = {}
        self._last_any = None

    def wait(self, url) -> float:
        """Sleep what the host and the burst rule still ask for; returns seconds slept."""
        now = self._clock()
        ready = now
        last_host = self._last_by_host.get(feed_host(url))
        if last_host is not None:
            ready = max(ready, last_host + self.host_gap)
        if self._last_any is not None:
            ready = max(ready, self._last_any + self.any_gap)
        pause = ready - now
        if pause > 0:
            self._sleep(pause)
            return pause
        return 0.0

    def fetched(self, url):
        now = self._clock()
        self._last_by_host[feed_host(url)] = now
        self._last_any = now


def circle_rest_seconds(circle_seconds, interval_minutes,
                        period=MIN_CIRCLE_PERIOD_SECONDS) -> float:
    """The rest after a circle: the old fixed rest, or what is left of the period.

    A circle that did not finish (it raised, or there was nothing to poll) has
    no duration: it is retried after the old rest, not after an hour.
    """
    if not circle_seconds or circle_seconds < 0:
        return interval_minutes * 60
    return max(interval_minutes * 60, period - circle_seconds)
