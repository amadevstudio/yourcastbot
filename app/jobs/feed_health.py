# -*- coding: utf-8 -*-
"""RSS feed consecutive-failure policy. Survives process restart via sqlite."""
from __future__ import annotations

import time

from app.repository.storage import storage

# Разовый таймаут/503 не должен гасить уведомления.
FEED_FAILURES_BEFORE_NOTIFY_OFF = 5
# 404/410 — фида уже нет, порог ниже.
FEED_GONE_FAILURES_BEFORE_NOTIFY_OFF = 3
# После выключения не дёргать хост каждый круг.
FEED_DEAD_PROBE_SECONDS = 24 * 60 * 60


def failures_threshold(reason: str) -> int:
    if reason == "gone":
        return FEED_GONE_FAILURES_BEFORE_NOTIFY_OFF
    return FEED_FAILURES_BEFORE_NOTIFY_OFF


def should_skip_feed_fetch(
        channel_id, manual=False, now=None, database=None) -> bool:
    if manual:
        return False
    until = storage.get_channel_feed_dead_until(channel_id, database=database)
    if until is None:
        return False
    stamp = time.time() if now is None else float(now)
    return stamp < until


def note_feed_ok(channel_id, database=None):
    storage.clear_channel_feed_dead(channel_id, database=database)


def note_feed_failure(
        channel_id, reason, now=None, database=None) -> str:
    """counting | newly_dead | still_dead"""
    stamp = time.time() if now is None else float(now)
    until = storage.get_channel_feed_dead_until(channel_id, database=database)
    if until is not None and stamp < until:
        return "still_dead"
    if until is not None:
        storage.set_channel_feed_dead_until(
            channel_id, stamp + FEED_DEAD_PROBE_SECONDS, database=database)
        return "still_dead"
    failures = storage.increase_channel_feed_failures(
        channel_id, database=database)
    if failures < failures_threshold(reason):
        return "counting"
    storage.set_channel_feed_dead_until(
        channel_id, stamp + FEED_DEAD_PROBE_SECONDS, database=database)
    return "newly_dead"


def _missing(value) -> bool:
    return value in (None, '', 'None')


def paid_targets_behind(channel, target_connections) -> list:
    """Paid targets a 304 would leave without the latest episode.

    304 means "the feed is what was parsed last time", not "every paid
    listener got it": a manual refresh parses the feed for one chat and
    stores the ETag for the channel. A full parse sends the latest item only
    to a cursor that differs from the channel's by guid and by date (the
    date check drops everyone at the channel's date), so this does the
    same. Empty when the channel has no latest to compare with.
    """
    if channel is None:
        return []
    try:
        latest_guid = channel['last_guid']
        latest_date = channel['last_date']
    except (KeyError, IndexError, TypeError):
        return []
    if _missing(latest_guid):
        return []
    return [
        connection for connection in (target_connections or [])
        if connection['last_guid'] != latest_guid
        and connection['last_date'] != latest_date]
