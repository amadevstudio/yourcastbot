# -*- coding: utf-8 -*-
"""Empty cursors ("__") get a quiet start. No bot imports: runs in the CD gate.

Behaviour is tested end to end in app/jobs/test_updater_not_modified.py
(needs the bot's requirements); this locks the rule and where it is used.
Run from the repo root: python app/jobs/test_quiet_start.py
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs.nosub_digest import EMPTY_CURSOR, is_empty_cursor  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _function(tree, name):
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name)


def main():
    _assert_eq(EMPTY_CURSOR, "__", "the id of a feed that parsed to no items")
    for value in ("__", "", None, "None"):
        _assert_eq(is_empty_cursor(value), True, "empty cursor %r" % (value,))
    _assert_eq(is_empty_cursor("guid_Tue, 29 Sep 2026_Title"), False, "real cursor")

    path = os.path.join(_ROOT, "app", "jobs", "podcastsUpdater.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    send = ast.dump(_function(tree, "send_new_records_by_channel"))
    _assert_eq("quiet_start" in send and "is_empty_cursor" in send, True,
               "the circle drops empty cursors from the recipients")
    flag = _function(tree, "flag_nosubs_for_digest")
    first = flag.body[0]
    _assert_eq(isinstance(first, ast.If) and "is_empty_cursor" in ast.dump(first.test)
               and isinstance(first.body[0], ast.Return), True,
               "no reminder when the channel's latest is empty")
    _assert_eq("quiet" in ast.dump(flag), True, "free empty cursors are moved, not reminded")
    print("all quiet start checks passed")


if __name__ == "__main__":
    main()
