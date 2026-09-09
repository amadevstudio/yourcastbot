# -*- coding: utf-8 -*-
"""Feed dead cooldown. Uses a temp sqlite, never production.

Run: python app/jobs/test_feed_health.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs import feed_health  # noqa: E402
from app.repository.storage import storage  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def test_counts_then_marks_dead(db_path):
    now = 1_000_000.0
    for _ in range(feed_health.FEED_GONE_FAILURES_BEFORE_NOTIFY_OFF - 1):
        _assert_eq(
            feed_health.note_feed_failure(7, "gone", now=now, database=db_path),
            "counting", "below gone threshold")
        now += 60
    _assert_eq(
        feed_health.note_feed_failure(7, "gone", now=now, database=db_path),
        "newly_dead", "gone threshold marks dead")
    _assert_eq(
        feed_health.should_skip_feed_fetch(
            7, now=now + 10, database=db_path),
        True, "skip fetch during cooldown")
    _assert_eq(
        feed_health.should_skip_feed_fetch(
            7, manual=True, now=now + 10, database=db_path),
        False, "manual update still fetches")
    _assert_eq(
        feed_health.note_feed_failure(
            7, "gone", now=now + 20, database=db_path),
        "still_dead", "another fail during cooldown is not a new warn")
    later = now + feed_health.FEED_DEAD_PROBE_SECONDS + 1
    _assert_eq(
        feed_health.should_skip_feed_fetch(7, now=later, database=db_path),
        False, "probe after cooldown")
    _assert_eq(
        feed_health.note_feed_failure(7, "gone", now=later, database=db_path),
        "still_dead", "failed probe extends dead, does not re-disable")
    feed_health.note_feed_ok(7, database=db_path)
    _assert_eq(
        feed_health.should_skip_feed_fetch(7, now=later + 5, database=db_path),
        False, "success clears dead")
    _assert_eq(
        storage.get_channel_feed_failures(7, database=db_path),
        0, "success resets counter")


def test_unavailable_needs_more_failures(db_path):
    now = 2_000_000.0
    for i in range(feed_health.FEED_FAILURES_BEFORE_NOTIFY_OFF - 1):
        _assert_eq(
            feed_health.note_feed_failure(
                9, "unavailable", now=now + i, database=db_path),
            "counting", "unavailable below 5")
    _assert_eq(
        feed_health.note_feed_failure(
            9, "unavailable", now=now + 10, database=db_path),
        "newly_dead", "unavailable threshold 5")


def test_enclosure_host_cool(db_path):
    url = "https://m.cdn.firstory.me/track/a.mp3"
    now = 3_000_000.0
    _assert_eq(
        storage.enclosure_host_is_cool(url, now=now, database=db_path),
        False, "cold at start")
    host = storage.mark_enclosure_host_cool(
        url, seconds=60, now=now, database=db_path)
    _assert_eq(host, "m.cdn.firstory.me", "cool key is host")
    _assert_eq(
        storage.enclosure_host_is_cool(url, now=now + 10, database=db_path),
        True, "cool during window")
    _assert_eq(
        storage.enclosure_host_is_cool(
            "https://m.cdn.firstory.me/other.mp3", now=now + 10,
            database=db_path),
        True, "same host other file is cool")
    _assert_eq(
        storage.enclosure_host_is_cool(url, now=now + 61, database=db_path),
        False, "cool expires")


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_feed_health_")
    cases = (
        test_counts_then_marks_dead,
        test_unavailable_needs_more_failures,
        test_enclosure_host_cool,
    )
    for index, case in enumerate(cases):
        path = os.path.join(tmpdir, "case_%d.db" % index)
        print("-- %s" % case.__name__)
        case(path)
    print("all feed_health checks passed")


if __name__ == "__main__":
    main()
