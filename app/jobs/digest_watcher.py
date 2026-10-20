# -*- coding: utf-8 -*-
"""Drain digest_outbox in the jobs process. Do not run this from updater."""
import time
import json

import app.service.user.language
from app.core.sender.outbox import OutboxRetryableError
from app.i18n.messages import get_message
from app.jobs import digest_outbox
from app.jobs.digest_outbox import migrate_from_kv, pending_count
from app.jobs.nosub_digest import DIGEST_MUTE_ACTION, should_send_nosub_digest
from app.jobs.relay_remind import relay_nudge_markup
from config import db_path
from db.sqliteAdapter import SQLighter
from db import listening
from lib.markup import telegram_html
from lib.telegram.general.message_master import outer_sender
from lib.tools.logger import logger

IDLE_SLEEP_SECONDS = 5
SEND_PAUSE_SECONDS = 1


def digest_message(entries, language):
    text = get_message('youHaveNewEpisodes', language)
    rows = []
    if entries:
        text += '\n\n<b>' + get_message('digestEpisodes', language) + '</b>'
    for index, entry in enumerate(entries, 1):
        text += '\n\n' + str(index) + '. <b>' + telegram_html.escape(
            telegram_html.plain_text(entry['show_name'])[:90]) + '</b>\n'
        text += telegram_html.escape(telegram_html.plain_text(entry['title'])[:150])
        callback = json.loads(entry['callback_json'])
        # Saved old positions can no longer be trusted; hash lookup starts at 0.
        callback['dh_n'] = callback['dh_n'].split('_')[0] + '_1'
        rows.append([{'text': str(index) + ' · ' + get_message('playLater', language),
                      'callback_data': callback},
                     {'text': get_message('saveLater', language),
                      'callback_data': {'tp': 'saveLater', 'e': entry['id']}}])
    rows += relay_nudge_markup(language, extra_row=[{
        'text': get_message('nosubDigestMuteButton', language),
        'callback_data': {'tp': DIGEST_MUTE_ACTION},
    }])
    return {'type': 'text', 'text': text, 'reply_markup': rows, 'disable_web_page_preview': True}


def send_digest_to_user(user_tg_id, database=None):
    """Send one reminder if the user is still eligible.

    True if Telegram was called. False if skipped. 429 raises
    OutboxRetryableError so the row stays queued.
    """
    db_users = SQLighter(db_path if database is None else database)
    try:
        user = db_users.get_user_by_tg(user_tg_id)
        if not should_send_nosub_digest(
                user,
                has_tariff=db_users.is_user_have_bot_subscription(user_tg_id)):
            return False
        user_language = app.service.user.language.user_language(user['lang'])
        entries = listening.digest(user_tg_id, database)
        if not entries and listening.has_digest(user_tg_id, database):
            # Every queued show was muted/unsubscribed. Do not replace the
            # suppressed episodes with a generic reminder of those same shows.
            return False
        sent = outer_sender(user['telegramId'], [digest_message(entries, user_language)], on_flood='raise')
        if sent:
            db_users.mark_nosub_digest_sent(user_tg_id)
            listening.ack_digest(user_tg_id, entries, database)
            return True
        return False
    finally:
        db_users.close()


def digest_watcher():
    try:
        migrate_from_kv()
    except Exception as e:
        logger.err("digest_watcher/migrate:", e)
    try:
        digest_outbox.reclaim(force=True)
    except Exception as e:
        logger.err("digest_watcher/reclaim:", e)
    try:
        pending = pending_count()
    except Exception as e:
        logger.err("digest_watcher/pending:", e)
        pending = "?"
    logger.log("Digest watcher started, pending", pending)
    while True:
        try:
            try:
                digest_outbox.reclaim(force=False)
            except Exception as e:
                logger.err("digest_watcher/reclaim-loop:", e)
            job = digest_outbox.claim()
            if job is None:
                time.sleep(IDLE_SLEEP_SECONDS)
                continue
            user_tg_id = job["user_telegram_id"]
            attempts = job["attempts"]
            try:
                did_send = send_digest_to_user(user_tg_id)
            except OutboxRetryableError as e:
                logger.warn("digest_watcher/flood:", user_tg_id, e)
                digest_outbox.fail_or_retry(
                    user_tg_id, error=e, attempts=attempts)
                continue
            except Exception as e:
                logger.err("digest_watcher/send:", user_tg_id, e)
                digest_outbox.fail_or_retry(
                    user_tg_id, error=e, attempts=attempts)
                continue
            digest_outbox.mark_done(user_tg_id, attempts=attempts)
            if did_send:
                time.sleep(SEND_PAUSE_SECONDS)
        except Exception as e:
            logger.err("digest_watcher/loop:", e)
            time.sleep(IDLE_SLEEP_SECONDS)
