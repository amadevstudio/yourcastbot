# -*- coding: utf-8 -*-
"""Free listeners are reminded of a later episode, not of a new id. Stdlib only.

End to end (a host re-dating an episode, the 304 after it, junk dates):
app/jobs/test_updater_not_modified.py. Run from the repo root:
python app/jobs/test_nosub_rule.py
"""
import ast
import datetime
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs.nosub_digest import nosub_users_behind  # noqa: E402

UTC = datetime.timezone.utc
TUE = datetime.datetime(2026, 9, 29, 23, 0, tzinfo=UTC)
WED = datetime.datetime(2026, 9, 30, 23, 0, tzinfo=UTC)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    cursors = {1: "ep2_Tue +0000", 2: "ep1_Mon", 3: "ep2_Tue GMT"}
    _assert_eq(nosub_users_behind(cursors, "ep2_Tue GMT"), [1, 2],
               "no dates: ids decide, as before")
    _assert_eq(nosub_users_behind(cursors, "ep2_Tue GMT",
                                  seen_at={1: TUE, 2: TUE - datetime.timedelta(days=1)},
                                  latest_at=TUE),
               [2], "same instant under a new id is not new; an older cursor is")
    _assert_eq(nosub_users_behind({1: "ep2"}, "ep3", seen_at={1: TUE}, latest_at=WED),
               [1], "a later episode is new")
    _assert_eq(nosub_users_behind({1: "ep2"}, "ep3", seen_at={1: None}, latest_at=WED),
               [1], "unknown cursor date: ids decide")
    _assert_eq(nosub_users_behind({1: "ep2"}, "ep3", seen_at={1: TUE}, latest_at=None),
               [1], "unknown channel date: ids decide")
    _assert_eq(nosub_users_behind({1: "ep2"}, None), [], "no latest: nobody")

    path = os.path.join(_ROOT, "app", "jobs", "podcastsUpdater.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, "id", None) == "flag_nosubs_for_digest"]
    _assert_eq(len(calls), 3, "the 304, early-skip and full-parse paths remind")
    _assert_eq(all({k.arg for k in c.keywords} >= {"cursor_dates", "latest_at"} for c in calls),
               True, "every path passes the dates")
    print("all nosub rule checks passed")


if __name__ == "__main__":
    main()
