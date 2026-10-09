# -*- coding: utf-8 -*-
"""A deploy restart is silent and loses no channel; a crash skips and alerts.

Run from the repo root: python app/jobs/test_updater_resume.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs.updater_resume import (  # noqa: E402
    consume_clean_stop, mark_clean_stop, resume_point)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    _assert_eq(resume_point(1, crashed=False, clean_stop=False), (1, None),
               "circle finished before the stop: start over, quietly")
    _assert_eq(resume_point(6975, crashed=False, clean_stop=True), (6975, None),
               "deploy mid-circle: same channel again, no alert")
    start, alert = resume_point(6975, crashed=True, clean_stop=True)
    _assert_eq(start, 6976, "crash skips the channel that may have killed it")
    _assert_eq(alert.startswith("#restarted") and "6975" in alert, True, "crash alerts")
    start, alert = resume_point(6975, crashed=False, clean_stop=False)
    _assert_eq(start, 6976, "stop without SIGTERM skips the channel")
    _assert_eq(alert is not None, True, "stop without SIGTERM alerts")

    db = os.path.join(tempfile.mkdtemp(prefix="yourcast_resume_"), "kv.sqlite")
    _assert_eq(consume_clean_stop(database=db), False, "no marker at first start")
    mark_clean_stop(database=db)
    _assert_eq(consume_clean_stop(database=db), True, "SIGTERM leaves a marker")
    _assert_eq(consume_clean_stop(database=db), False, "the marker is used once")
    print("all updater resume checks passed")


if __name__ == "__main__":
    main()
