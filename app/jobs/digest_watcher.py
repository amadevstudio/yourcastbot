# -*- coding: utf-8 -*-
"""Drain digest_outbox in the jobs process. Do not run this from updater."""
import time

import app.service.user.language
from app.i18n.messages import get_message
from app.jobs.digest_outbox import migrate_from_kv, pending_count, take_one
from app.jobs.nosub_digest import DIGEST_MUTE_ACTION, should_send_nosub_digest
from config import botName, db_path
from db.sqliteAdapter import SQLighter
from lib.telegram.general.message_master import outer_sender
from lib.tools.logger import logger

IDLE_SLEEP_SECONDS = 5
SEND_PAUSE_SECONDS = 1


def send_digest_to_user(user_tg_id, database=None):
    """Send one reminder if the user is still eligible. True if Telegram was called."""
    db_users = SQLighter(db_path if database is None else database)
    try:
        user = db_users.get_user_by_tg(user_tg_id)
        if not should_send_nosub_digest(user):
            return False
        user_language = app.service.user.language.user_language(user['lang'])
        sent = outer_sender(user['telegramId'], [{
            'type': 'text',
            'text': (
                get_message("youHaveNewEpisodes", user_language)
                + " t.me/" + botName + "?start=" + str(user['telegramId'])),
            'reply_markup': [[{
                'text': get_message("nosubDigestMuteButton", user_language),
                'callback_data': {'tp': DIGEST_MUTE_ACTION},
            }]],
        }])
        if sent:
            db_users.mark_nosub_digest_sent(user_tg_id)
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
        pending = pending_count()
    except Exception as e:
        logger.err("digest_watcher/pending:", e)
        pending = "?"
    logger.log("Digest watcher started, pending", pending)
    while True:
        try:
            user_tg_id = take_one()
            if user_tg_id is None:
                time.sleep(IDLE_SLEEP_SECONDS)
                continue
            try:
                did_send = send_digest_to_user(user_tg_id)
            except Exception as e:
                logger.err("digest_watcher/send:", user_tg_id, e)
                did_send = False
            if did_send:
                time.sleep(SEND_PAUSE_SECONDS)
        except Exception as e:
            logger.err("digest_watcher/loop:", e)
            time.sleep(IDLE_SLEEP_SECONDS)
