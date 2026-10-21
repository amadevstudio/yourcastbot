# -*- coding: utf-8 -*-
"""Summaries of new episodes, sent after the file (opt-in: users.flags FLAG, /settings).

When the circle delivers a new episode, each user chat that turned this on
gets its summary queued, charged to the plan's hours as a tap would be. A
chat whose hours do not cover the episode, or with no plan running, gets
none and no notice: it did not ask for this one. A summary someone already
made is sent at once and costs nothing (the worker's cache). Taps go first
in the queue (db.ai.claim): an automatic one never makes a person wait. The
summary answers the delivered audio when the sender knows its message, so
its times play the episode; otherwise it comes as a message of its own.
Never fails a delivery.
"""
from app.service.ai import quota, summary
from config import db_path
from db import ai
from db.connection import connect_sqlite
from lib.tools.logger import logger

FLAG = 'auto_summary'
TOGGLE_ACTION = 'sumAuto'
CHUNK = 500


def wanted(chat_ids, database=None) -> dict:
    """{chat id: its summary language preference} for the chats that turned this on."""
    ids = [int(chat_id) for chat_id in chat_ids if str(chat_id).isdigit()]
    found = {}
    connection = connect_sqlite(db_path if database is None else database)
    try:
        for start in range(0, len(ids), CHUNK):
            part = ids[start:start + CHUNK]
            rows = connection.execute(
                "SELECT telegramId, json_extract(COALESCE(flags, '{}'), '$.%s'), "
                "json_extract(COALESCE(flags, '{}'), '$.%s') FROM users WHERE telegramId IN (%s)"
                % (FLAG, summary.LANGUAGE_FLAG, ','.join('?' * len(part))), part).fetchall()
            found.update({int(row[0]): row[2] for row in rows if row[1]})
    finally:
        connection.close()
    return found


def queue(chat_ids, ref, seconds, language_codes=None, message_ids=None, database=None) -> int:
    """Queue the episode's summary for the chats that want one and can pay for it; how many."""
    if not ref or not summary.enabled():
        return 0
    language_codes, message_ids = language_codes or {}, message_ids or {}
    queued = 0
    try:
        chats = wanted(chat_ids, database)
    except Exception as e:
        logger.warn("auto summary:", type(e).__name__, e)
        return 0
    needed = int(seconds or 0) or quota.UNKNOWN_SECONDS
    for chat_id, preference in chats.items():
        try:
            if not quota.check(chat_id, needed, database=database).allowed:
                continue
            language = summary.summary_language(preference, language_codes.get(chat_id))
            _, new = ai.enqueue(chat_id, ref, language, needed, database=database,
                                reply_to=message_ids.get(chat_id), auto=True)
            queued += int(new)
        except Exception as e:
            logger.warn("auto summary for", chat_id, type(e).__name__, e)
    return queued
