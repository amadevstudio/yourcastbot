# -*- coding: utf-8 -*-
"""Daily circle-finished Telegram, not every pass.

Run from the repo root: python app/jobs/test_circle_health.py
"""
import os
import sys
import tempfile
import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs import circle_health  # noqa: E402
from db import runtime_kv  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def test_first_finish_notifies_later_silent(db_path):
    start = datetime.datetime(2026, 9, 7, 9, 0, 0)
    end = datetime.datetime(2026, 9, 7, 10, 5, 0)
    circle_health.mark_circle_started(now=start, database=db_path)
    first = circle_health.mark_circle_finished(now=end, database=db_path)
    _assert_eq(first['notify'], True, "first finish of the day notifies")
    _assert_eq(first['circles_today'], 1, "first circle counted")
    _assert_eq(first['circles_yesterday'], 0, "no yesterday yet")
    _assert_eq(first['duration_sec'], 3900, "65 minutes")
    _assert_eq(
        first['summary'],
        "duration: 65 min; today: 1; yesterday: 0",
        "first-day summary")

    circle_health.mark_circle_started(
        now=datetime.datetime(2026, 9, 7, 10, 15, 0), database=db_path)
    second = circle_health.mark_circle_finished(
        now=datetime.datetime(2026, 9, 7, 11, 20, 0), database=db_path)
    _assert_eq(second['notify'], False, "later finish stays in the log")
    _assert_eq(second['circles_today'], 2, "second circle counted")

    next_day = circle_health.mark_circle_finished(
        now=datetime.datetime(2026, 9, 8, 10, 0, 0), database=db_path)
    _assert_eq(next_day['notify'], True, "next day notifies again")
    _assert_eq(next_day['circles_today'], 1, "counter resets next day")
    _assert_eq(next_day['circles_yesterday'], 2, "yesterday keeps the full day")
    if "today: 1; yesterday: 2" not in next_day['summary']:
        raise AssertionError(
            "daily Telegram shows yesterday's total: %r" % next_day['summary'])
    print("ok  daily Telegram shows yesterday's total = %r" % next_day['summary'])


def test_users_count_lines(db_path):
    _assert_eq(
        circle_health.format_status_lines(database=db_path),
        '', "no lines before a finish")
    circle_health.mark_circle_started(
        now=datetime.datetime(2026, 9, 7, 16, 0, 0), database=db_path)
    circle_health.mark_circle_finished(
        now=datetime.datetime(2026, 9, 7, 16, 46, 0), database=db_path)
    lines = circle_health.format_status_lines(database=db_path)
    _assert_eq(
        lines,
        "Последний круг: 46 мин (16:46)\n"
        "Кругов сегодня: 1\n"
        "Кругов вчера: 0",
        "usersCount extra lines")


def main():
    tmpdir = tempfile.mkdtemp(prefix="yourcast_circle_health_")
    for index, case in enumerate((
            test_first_finish_notifies_later_silent,
            test_users_count_lines,
    )):
        path = os.path.join(tmpdir, "case_%d.db" % index)
        print("-- %s" % case.__name__)
        runtime_kv.ensure_table(
            runtime_kv._connect(path), database=path)
        case(path)
    print("all circle_health checks passed")


if __name__ == '__main__':
    main()
