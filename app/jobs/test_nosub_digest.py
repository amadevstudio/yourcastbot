# -*- coding: utf-8 -*-
"""nosub digest helpers. Run from repo root: python app/jobs/test_nosub_digest.py"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs.nosub_digest import (  # noqa: E402
    latest_episode_id, nosub_users_behind, should_skip_item_parse)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    _assert_eq(
        should_skip_item_parse([], "Mon, 01 Jan 2026"),
        False,
        "nosubs-only must parse items")
    _assert_eq(
        should_skip_item_parse(
            [{'last_date': "Mon, 01 Jan 2026"}], "Mon, 01 Jan 2026"),
        True,
        "all paid current skips items")
    _assert_eq(
        should_skip_item_parse(
            [{'last_date': "Sun, 31 Dec 2025"}, {'last_date': "Mon, 01 Jan 2026"}],
            "Mon, 01 Jan 2026"),
        False,
        "one paid behind still parses")
    _assert_eq(
        should_skip_item_parse([{'last_date': "Mon, 01 Jan 2026"}], None),
        False,
        "missing feed date does not skip")

    _assert_eq(
        nosub_users_behind({1001: "old", 1002: "new-ep", 1003: "old"}, "new-ep"),
        [1001, 1003],
        "behind users")
    _assert_eq(
        nosub_users_behind({1001: "new-ep"}, "new-ep"),
        [],
        "already current")
    _assert_eq(
        nosub_users_behind({1001: "old"}, None),
        [],
        "no latest episode")
    _assert_eq(
        nosub_users_behind({1001: None}, "new-ep"),
        [1001],
        "empty saved guid is behind")

    _assert_eq(
        latest_episode_id({'last_guid': "ch-ep"}, [{'last_guid': "paid-ep"}]),
        "ch-ep",
        "prefer channel last_guid")
    _assert_eq(
        latest_episode_id({'last_guid': None}, [{'last_guid': "paid-ep"}]),
        "paid-ep",
        "fallback to paid last_guid")
    _assert_eq(
        latest_episode_id({'last_guid': ""}, []),
        None,
        "missing both")
    print("all nosub_digest checks passed")


if __name__ == "__main__":
    main()
