# -*- coding: utf-8 -*-
"""Summaries of new episodes, sent after the file (opt-in: users.flags FLAG, /settings).

When the circle delivers a new episode, each user chat that turned this on
gets its summary queued, charged to the plan's hours as a tap would be. A
chat with no plan running gets none (the plan-off notice told it). A chat
whose plan's hours do not cover the episode gets none either, and once in
QUOTA_DAYS hears so (users.flags NOTICE_FLAG: when), with the offer a tap
over the hours gets: else its summaries just stop. A summary someone already
made is sent at once and costs nothing (the worker's cache). Taps go first
in the queue (db.ai.claim): an automatic one never makes a person wait. The
summary answers the delivered audio when the sender knows its message, so
its times play the episode; otherwise it comes as a message of its own.
Never fails a delivery.
"""
import time

from app.i18n.messages import get_message
from app.service.ai import quota, summary
from app.service.ai.offer import offer_message
from config import db_path
from db import ai
from db.connection import connect_sqlite
from lib.tools.logger import logger

FLAG = 'auto_summary'
TOGGLE_ACTION = 'sumAuto'
NOTICE_FLAG = 'summary_quota_noticed'
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
            check = quota.check(chat_id, needed, database=database)
            if not check.allowed:
                if check.limit:
                    _notice_over_quota(chat_id, check, language_codes.get(chat_id), message_ids.get(chat_id),
                                       database)
                continue
            language = summary.summary_language(preference, language_codes.get(chat_id))
            _, new = ai.enqueue(chat_id, ref, language, needed, database=database,
                                reply_to=message_ids.get(chat_id), auto=True)
            queued += int(new)
        except Exception as e:
            logger.warn("auto summary for", chat_id, type(e).__name__, e)
    return queued


def _notice_over_quota(chat_id, check, language_code, reply_to, database=None, now=None):
    """Once in QUOTA_DAYS: this episode came without its summary, and why (the tap's offer)."""
    now = time.time() if now is None else now
    connection = connect_sqlite(db_path if database is None else database)
    try:
        row = connection.execute("SELECT json_extract(COALESCE(flags, '{}'), '$.%s') FROM users "
                                 "WHERE telegramId = ?" % NOTICE_FLAG, (int(chat_id),)).fetchone()
        if row is None or (row[0] and now - float(row[0]) < quota.QUOTA_DAYS * 86400):
            return
        with connection:  # marked first: a failed send is one missed notice, never one a circle
            connection.execute("UPDATE users SET flags = json_set(COALESCE(flags, '{}'), '$.%s', ?) "
                               "WHERE telegramId = ?" % NOTICE_FLAG, (int(now), int(chat_id)))
    finally:
        connection.close()
    message = offer_message(language_code, check)
    message['text'] = get_message('summaryAutoSkipped', language_code) + '\n\n' + message['text']
    if reply_to:
        message['reply_to'] = int(reply_to)
    _send(chat_id, [message])


def _send(chat_id, messages):
    from lib.telegram.general.message_master import outer_sender
    return outer_sender(chat_id, messages)
