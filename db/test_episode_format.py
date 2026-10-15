# -*- coding: utf-8 -*-
"""users.episode_format / rich_hint_sent: created on open, default rich, switchable.

Temporary file DB only. Run from the repo root: python db/test_episode_format.py
"""
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.service.record.text_format import RICH, SEPARATE, other_format, user_format  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    path = os.path.join(tempfile.mkdtemp(prefix="yourcast_format_"), "db.sqlite")
    old = sqlite3.connect(path)  # a users table from before the columns
    old.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, telegramId TEXT UNIQUE)")
    old.executemany("INSERT INTO users (telegramId) VALUES (?)", [("101",), ("102",)])
    old.commit()
    old.close()

    db = SQLighter(path)
    try:
        columns = [row[1] for row in db.connection.execute("PRAGMA table_info(users)")]
        _assert_eq('episode_format' in columns and 'rich_hint_sent' in columns, True,
                   "opening the database adds both columns")
        _assert_eq(db.get_episode_formats([101, 102, 999]), {101: (None, False), 102: (None, False)},
                   "existing users: default format, hint not shown; unknown ids are absent")
        db.set_episode_format(101, SEPARATE)
        db.mark_rich_hint_sent(102)
        _assert_eq(db.get_episode_formats([101, 102]), {101: ('separate', False), 102: (None, True)},
                   "switch and hint are stored per user")
    finally:
        db.close()

    db = SQLighter(path)  # a second open: nothing to add, nothing lost
    try:
        _assert_eq(db.get_episode_formats([101])[101][0], 'separate', "survives a reopen")
        _assert_eq(db.get_episode_formats([]), {}, "no ids, no rows")
    finally:
        db.close()

    _assert_eq([user_format(v) for v in (None, '', 'rich', 'junk', 'separate')],
               [RICH, RICH, RICH, RICH, SEPARATE], "stored value to format: rich unless separate")
    _assert_eq((other_format(None), other_format('separate')), (SEPARATE, RICH), "the toggle")
    print("all episode format checks passed")


if __name__ == "__main__":
    main()
