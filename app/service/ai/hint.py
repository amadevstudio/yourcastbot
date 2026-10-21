# -*- coding: utf-8 -*-
"""Once per user: what the Summary button under an episode does.

Most users never tapped it (7 summaries on 2026-10-21, against ~60 running
plans). After a delivered episode that carries the button, a user chat with
a plan running (a trial too: it has hours) that never asked for a summary
gets one note, a reply to that audio, and users.flags FLAG is set. Without a
plan the button leads to an invoice: no note for that. The sender never
sends it with the note about the rich message (one note per delivery).
"""
from config import db_path
from db import ai
from db.connection import connect_sqlite

FLAG = 'summary_hint_sent'
CHUNK = 500


def pending(chat_ids, database=None) -> set:
    """The user chats among `chat_ids` that should get the note now."""
    ids = sorted({int(chat_id) for chat_id in chat_ids if str(chat_id).isdigit()})
    if not ids:
        return set()
    database = db_path if database is None else database
    ai.connect(database).close()  # ai_requests exists before its first row
    found = set()
    connection = connect_sqlite(database)
    try:
        for start in range(0, len(ids), CHUNK):
            part = ids[start:start + CHUNK]
            rows = connection.execute(
                "SELECT u.telegramId FROM users u JOIN user_tariff_cs ut ON ut.uid = u.id "
                "WHERE u.telegramId IN (%s) AND ut.tariff_id > 0 AND ut.time_left > 0 "
                "AND json_extract(COALESCE(u.flags, '{}'), '$.%s') IS NULL "
                "AND NOT EXISTS(SELECT 1 FROM ai_requests r WHERE r.chat_id = u.telegramId)"
                % (','.join('?' * len(part)), FLAG), part).fetchall()
            found.update(int(row[0]) for row in rows)
    finally:
        connection.close()
    return found


def mark(chat_id, database=None) -> None:
    connection = connect_sqlite(db_path if database is None else database)
    try:
        with connection:
            connection.execute("UPDATE users SET flags = json_set(COALESCE(flags, '{}'), '$.%s', 1) "
                               "WHERE telegramId = ?" % FLAG, (int(chat_id),))
    finally:
        connection.close()
