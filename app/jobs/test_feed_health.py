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
from lib.net.enclosure import COOL_SECONDS, FAULT_WINDOW_SECONDS  # noqa: E402


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


def test_tracker_link_cools_the_cdn(db_path):
    """A dead CDN behind podtrac must not take podtrac (13% of our links).

    One NBC download timed out and the next two taps were told "unavailable"
    because dts.podtrac.com was cooled; every other podtrac podcast was one
    timeout away from the same.
    """
    now = 4_000_000.0
    nbc = ("https://dts.podtrac.com/redirect.mp3/chrt.fm/track/A1B2/"
           "nbcnews.simplecastaudio.com/audio/ep.mp3")
    other = ("https://dts.podtrac.com/redirect.mp3/tracking.swap.fm/track/UV/"
             "traffic.omny.fm/d/clips/ep.mp3")
    error = ("HTTPSConnectionPool(host='nbcnews.simplecastaudio.com', port=443): "
             "Max retries exceeded with url: /audio/ep.mp3 "
             "(Caused by ReadTimeoutError(Read timed out. (read timeout=15)))")

    host = storage.mark_enclosure_host_cool(
        nbc, error=error, seconds=60, now=now, database=db_path)
    _assert_eq(host, "nbcnews.simplecastaudio.com", "cooled the host that hung")
    _assert_eq(
        storage.enclosure_host_is_cool(other, now=now + 5, database=db_path),
        False, "another podcast behind the same redirector still plays")
    _assert_eq(
        storage.enclosure_host_is_cool(nbc, now=now + 5, database=db_path),
        True, "the dead cdn is still skipped through its tracker link")
    _assert_eq(
        storage.enclosure_host_is_cool(
            "https://nbcnews.simplecastaudio.com/audio/other.mp3",
            now=now + 5, database=db_path),
        True, "and on a direct link to it")
    _assert_eq(
        storage.enclosure_host_is_cool(nbc, now=now + 61, database=db_path),
        False, "cool expires")

    # Telegram refusals and 4xx name no host: fall back to the URL, as before.
    host = storage.mark_enclosure_host_cool(
        other, error="Bad Gateway", seconds=60, now=now + 61, database=db_path)
    _assert_eq(host, "dts.podtrac.com", "no host in the error, use the url")


def test_one_fault_is_a_hiccup(db_path):
    """One timeout counts; the second one within the window cools the CDN.

    The NBC CDN missed one 15 s read and answered in 0.9 s a minute later, yet
    the retaps were refused for 30 minutes. A host that fails again is cooled.
    """
    now = 5_000_000.0
    window = FAULT_WINDOW_SECONDS
    nbc = ("https://dts.podtrac.com/redirect.mp3/chrt.fm/track/A1B2/"
           "nbcnews.simplecastaudio.com/audio/ep.mp3")
    other = ("https://dts.podtrac.com/redirect.mp3/tracking.swap.fm/track/UV/"
             "traffic.omny.fm/d/clips/ep.mp3")
    error = ("HTTPSConnectionPool(host='nbcnews.simplecastaudio.com', port=443): "
             "Read timed out. (read timeout=15)")
    omny = ("HTTPSConnectionPool(host='traffic.omny.fm', port=443): "
            "Read timed out. (read timeout=15)")

    def fault(url, err, at):
        return storage.note_enclosure_host_fault(
            url, error=err, now=at, database=db_path)

    def cool(url, at):
        return storage.enclosure_host_is_cool(url, now=at, database=db_path)

    _assert_eq(fault(nbc, error, now), None, "first fault only counts")
    _assert_eq(cool(nbc, now + 5), False, "a retap after one hiccup is tried")
    _assert_eq(fault(other, omny, now + 10), None, "another cdn keeps its own count")
    _assert_eq(
        fault(nbc, error, now + 60), "nbcnews.simplecastaudio.com",
        "second fault in the window cools the cdn")
    _assert_eq(cool(nbc, now + 65), True, "dead cdn skipped through its tracker link")
    _assert_eq(cool(other, now + 65), False, "the redirector's other podcasts still play")

    # Still dead after the cooldown: its first failure cools it again.
    after = now + 60 + COOL_SECONDS + 1
    _assert_eq(cool(nbc, after), False, "cooldown expires")
    _assert_eq(
        fault(nbc, error, after), "nbcnews.simplecastaudio.com",
        "a host still dead after its cooldown is cooled by one fault")

    # A fault long after the last cooldown is a fresh hiccup again.
    later = after + COOL_SECONDS + window + 1
    _assert_eq(fault(nbc, error, later), None, "recovered host starts from one")
    _assert_eq(
        fault(nbc, error, later + window + 1), None,
        "two faults further apart than the window do not cool")


def test_fault_counter_survives_garbage(db_path):
    from db import runtime_kv
    runtime_kv.set_kv(
        "enclosure_faults_m.cdn.firstory.me", "not-a-counter", database=db_path)
    _assert_eq(
        storage.note_enclosure_host_fault(
            "https://m.cdn.firstory.me/track/a.mp3", error="Read timed out.",
            now=6_000_000.0, database=db_path),
        None, "unreadable counter counts as the first fault")


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_feed_health_")
    cases = (
        test_counts_then_marks_dead,
        test_unavailable_needs_more_failures,
        test_enclosure_host_cool,
        test_tracker_link_cools_the_cdn,
        test_one_fault_is_a_hiccup,
        test_fault_counter_survives_garbage,
    )
    for index, case in enumerate(cases):
        path = os.path.join(tmpdir, "case_%d.db" % index)
        print("-- %s" % case.__name__)
        case(path)
    print("all feed_health checks passed")


if __name__ == "__main__":
    main()
