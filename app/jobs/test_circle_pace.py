# -*- coding: utf-8 -*-
"""The circle is polite to each host, not slow to all. No bot imports: CD gate.

Before: 6 s after every fully fetched feed (about 550 of them per circle = 55
minutes of a ~58 minute circle asleep). Now a host is fetched in full at most
once per 6 s, any two full fetches are 1 s apart, and a circle still starts
about once an hour. Run from the repo root: python app/jobs/test_circle_pace.py
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs.circle_pace import (  # noqa: E402
    ANY_GAP_SECONDS, HOST_GAP_SECONDS, MIN_CIRCLE_PERIOD_SECONDS, HostPacer,
    circle_rest_seconds, feed_host)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


class _Time:
    """A clock the fake sleep moves."""

    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    def work(self, seconds):
        self.now += seconds


def _pacer(world):
    return HostPacer(clock=world.clock, sleep=world.sleep)


def test_feed_host():
    _assert_eq(feed_host("https://Feeds.Example.com:8443/a/b?x=1"), "feeds.example.com", "host, lowercase, no port")
    _assert_eq(feed_host(""), "", "no URL: an empty bucket")
    _assert_eq(feed_host(None), "", "None: an empty bucket")
    _assert_eq(feed_host("not a url"), "", "junk: an empty bucket")


def test_limits_are_the_old_ones():
    _assert_eq((HOST_GAP_SECONDS, ANY_GAP_SECONDS), (6.0, 1.0), "6 s per host, 1 s between any two")


def test_pacer():
    world = _Time()
    pacer = _pacer(world)
    _assert_eq(pacer.wait("http://a.example/feed"), 0.0, "the first fetch of the circle does not wait")
    pacer.fetched("http://a.example/feed")
    # the same host at once: the full 6 s
    _assert_eq(pacer.wait("http://a.example/other"), 6.0, "the same host again: the full 6 s")

    world = _Time()
    pacer = _pacer(world)
    start = world.now
    for host in ("a", "b", "c"):
        pause = pacer.wait("http://%s.example/feed" % host)
        pacer.fetched("http://%s.example/feed" % host)
        _assert_eq(pause, 0.0 if host == "a" else 1.0,
                   "host %s: only the 1 s between two fetches, no 6 s" % host)
    _assert_eq(world.now - start, 2.0, "three hosts cost 2 s of sleeping, not 18")
    _assert_eq(pacer.wait("http://a.example/again"), 4.0,
               "a is asked again 2 s after its fetch: it waits the 4 s it still owes")
    _assert_eq(world.now - start, 6.0, "and is fetched exactly 6 s after its last fetch")


def test_pacer_never_waits_twice_for_time_that_passed():
    world = _Time()
    pacer = _pacer(world)
    pacer.fetched("http://a.example/feed")
    world.work(7.0)
    _assert_eq(pacer.wait("http://a.example/feed"), 0.0, "7 s later the host is free")
    _assert_eq(world.slept, [], "nothing was slept")


def test_304s_do_not_count():
    """Only a full fetch is recorded (as before): wait() without fetched() costs nothing."""
    world = _Time()
    pacer = _pacer(world)
    for _ in range(5):
        _assert_eq(pacer.wait("http://a.example/feed"), 0.0, "a 304 channel is not paced")


def test_unknown_hosts_share_a_bucket():
    world = _Time()
    pacer = _pacer(world)
    pacer.fetched("")
    _assert_eq(pacer.wait(None), 6.0, "channels with no feed URL are paced like one host (the old 6 s)")


def test_circle_rest():
    _assert_eq(circle_rest_seconds(3480, 10), 600, "a circle as long as before: the old 10 min rest")
    _assert_eq(circle_rest_seconds(600, 10), MIN_CIRCLE_PERIOD_SECONDS - 600,
               "a 10 min circle rests until the hour: the hosts are asked as often as before")
    _assert_eq(circle_rest_seconds(3 * 3600, 10), 600, "a very long circle: the old rest")
    _assert_eq(circle_rest_seconds(0, 10), 600, "a circle that raised or had nothing to poll: retried in 10 min")
    _assert_eq(circle_rest_seconds(None, 10), 600, "no duration: the old rest")


def test_updater_uses_it():
    path = os.path.join(_ROOT, "app", "jobs", "podcastsUpdater.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    main = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [(n.lineno, ast.unparse(n.func)) for n in ast.walk(main) if isinstance(n, ast.Call)]
    sleeps = [n for n in ast.walk(main) if isinstance(n, ast.Call) and ast.unparse(n.func) == "time.sleep"
              and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == 6]
    _assert_eq(sleeps, [], "no unconditional 6 s sleep left in the circle")
    wait = next(line for line, name in calls if name == "pacer.wait")
    send = next(line for line, name in calls if name == "send_new_records_by_channel")
    _assert_eq(wait < send, True, "the host is waited for before its feed is fetched")
    fetched = next(n for n in ast.walk(main) if isinstance(n, ast.If) and "pacer.fetched" in ast.unparse(n))
    _assert_eq("'fetched'" in ast.unparse(fetched.test), True, "only a full fetch is recorded")
    source = ast.unparse(main)
    _assert_eq("circle_rest_seconds" in source, True, "the rest after a circle keeps the period")
    first_try = next(i for i, n in enumerate(ast.walk(main)) if isinstance(n, ast.Try))
    _assert_eq("circle_seconds = 0" in source and source.index("circle_seconds = 0") < source.index("try:"),
               True, "circle_seconds is set before the try (a raising circle must not NameError)")
    _assert_eq(first_try >= 0, True, "sanity")


def main():
    for case in (test_feed_host, test_limits_are_the_old_ones, test_pacer,
                 test_pacer_never_waits_twice_for_time_that_passed, test_304s_do_not_count,
                 test_unknown_hosts_share_a_bucket, test_circle_rest, test_updater_uses_it):
        print("-- %s" % case.__name__)
        case()
    print("all circle pace checks passed")


if __name__ == "__main__":
    main()
