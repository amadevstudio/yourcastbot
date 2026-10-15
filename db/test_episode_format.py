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

from app.service.record.text_format import CAPTION, META, RICH, SEPARATE, user_format  # noqa: E402
from db.sqliteAdapter import SQLighter  # noqa: E402


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def main():
    path = os.path.join(tempfile.mkdtemp(prefix="yourcast_format_"), "db.sqlite")
    old = sqlite3.connect(path)  # a users table from before the columns
    # The first version had rich_hint_sent as a column of its own: user 103 saw the note then.
    old.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, telegramId TEXT UNIQUE, "
                "episode_format TEXT, rich_hint_sent INTEGER NOT NULL DEFAULT 0)")
    old.executemany("INSERT INTO users (telegramId) VALUES (?)", [("101",), ("102",)])
    old.execute("INSERT INTO users (telegramId, rich_hint_sent) VALUES ('103', 1)")
    old.commit()
    old.close()

    db = SQLighter(path)
    try:
        columns = [row[1] for row in db.connection.execute("PRAGMA table_info(users)")]
        _assert_eq('episode_format' in columns and 'flags' in columns, True,
                   "opening the database adds the flags column")
        _assert_eq(db.get_episode_formats([101, 102, 103, 999]),
                   {101: (None, False), 102: (None, False), 103: (None, True)},
                   "existing users: default format; the old column's flag moved into flags; unknown ids absent")
        db.set_episode_format(101, SEPARATE)
        db.mark_rich_hint_sent(102)
        _assert_eq(db.get_episode_formats([101, 102]), {101: ('separate', False), 102: (None, True)},
                   "switch and hint are stored per user")
        db.set_user_flag(102, 'other', 5)
        db.mark_rich_hint_sent(102)
        flags = db.connection.execute("SELECT flags FROM users WHERE telegramId = '102'").fetchone()[0]
        _assert_eq(__import__('json').loads(flags), {'rich_hint_sent': 1, 'other': 5},
                   "a flag is one key: setting it keeps the others")
    finally:
        db.close()

    db = SQLighter(path)  # a second open: nothing to add, nothing lost
    try:
        _assert_eq(db.get_episode_formats([101])[101][0], 'separate', "survives a reopen")
        _assert_eq(db.get_episode_formats([]), {}, "no ids, no rows")
    finally:
        db.close()

    _assert_eq([user_format(v) for v in (None, '', 'rich', 'junk', 'separate', 'caption', 'meta')],
               [RICH, RICH, RICH, RICH, SEPARATE, CAPTION, META],
               "stored value to format: the four choices, rich for anything else")
    print("all episode format checks passed")


if __name__ == "__main__":
    main()
