# -*- coding: utf-8 -*-
"""The creator hears every start of the bot: the commit, the roles, and whether
the last run stopped cleanly (the updater's mark is read, not taken). Temp DB only.

Run from the repo root: python app/core/test_start_notice.py
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core import start_notice  # noqa: E402
from app.jobs.updater_resume import consume_clean_stop, mark_clean_stop  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def main():
    roles = ("bot", "updater", "jobs", "admin")
    sha, _subject = start_notice.version()
    _assert(sha != '?' and len(sha) >= 7, "the running commit is named")
    _assert(start_notice._head_from_files(_ROOT) == sha[:7], "and read from .git when git refuses the tree")

    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, 'kv.sqlite')
        sent = []

        def send(text, level):
            sent.append((text, level))

        mark_clean_stop(database=db)
        start_notice.announce_start(roles, database=db, send=send, wait=True)
        _assert(sent[-1][1] == 'info' and sent[-1][0].startswith("🔄 Бот запускается: " + sha)
                and "Роли: bot, updater, jobs, admin" in sent[-1][0] and "штатно" in sent[-1][0],
                "a deploy: the commit, the roles, a clean stop")
        _assert(consume_clean_stop(database=db), "the mark is left for the updater (read, not taken)")
        start_notice.announce_start(roles, database=db, send=send, wait=True)
        _assert("Штатной остановки не было" in sent[-1][0], "no mark: a crash, kill or reboot is said")

        def broken(text, level):
            raise RuntimeError("telegram is down")
        start_notice.announce_start(roles, database=db, send=broken, wait=True)
        _assert(True, "a notice that cannot be sent never fails the start")
    print("all start notice checks passed")


if __name__ == "__main__":
    main()
