# -*- coding: utf-8 -*-
"""Sticky incoming slot assignment. No Telegram.

Run from the repo root: python app/core/balancers/test_sticky.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.balancers.sticky import (  # noqa: E402
    StickySlotAssigner, incoming_user_id)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


class _Inline:
    def __init__(self, user_id):
        self.user_id = user_id


def test_incoming_user_id():
    _assert_eq(
        incoming_user_id({'data': {'chat_id': 42}}), 42, "chat_id")
    _assert_eq(
        incoming_user_id({'data': {'inline': _Inline(99)}}), 99, "inline")
    _assert_eq(
        incoming_user_id({'user_id': 7, 'action': 'rec'}), 7, "rec user_id")
    _assert_eq(incoming_user_id({'data': {}}), None, "empty data")


def test_same_user_stays_on_slot():
    pool = StickySlotAssigner()
    first = pool.choose(1001, [0, 0, 0, 0])
    second = pool.choose(1001, [10, 0, 0, 0])
    _assert_eq(first, second, "sticky ignores later load")
    other = pool.choose(1002, [10, 0, 0, 0])
    _assert_eq(other in (1, 2, 3), True, "new user avoids the loaded slot")
    _assert_eq(other == first, False, "new user is not stuck on the busy slot")


def test_tie_rotates_off_slot_zero():
    pool = StickySlotAssigner()
    seen = set()
    for user_id in range(8):
        seen.add(pool.choose(user_id, [0, 0, 0, 0]))
    _assert_eq(seen, {0, 1, 2, 3}, "ties rotate across all slots")


def test_release_idle_allows_rebalance():
    pool = StickySlotAssigner()
    slot = pool.choose(5, [0, 0])
    pool.release_idle([True, True])
    _assert_eq(pool.user_slots, {}, "idle booking dropped")
    again = pool.choose(5, [5, 0])
    _assert_eq(again, 1, "released user follows least-loaded")
    _assert_eq(slot in (0, 1), True, "original slot was valid")


def main():
    test_incoming_user_id()
    test_same_user_stays_on_slot()
    test_tie_rotates_off_slot_zero()
    test_release_idle_allows_rebalance()
    print("all sticky checks passed")


if __name__ == "__main__":
    main()
