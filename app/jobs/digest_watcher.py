# -*- coding: utf-8 -*-
"""Drain digest_outbox in the jobs process. Do not run this from updater.

The digest's A/B (2026-10-30: ~5.2k digests a week, 25 Listen taps, 0.5%):
variant "a" is the digest as it was; "b" (digest_variant) leads with the
episodes, says Relay in one line under them and, to a chat that never paid
and has not spent the win-back offer, offers the first month of Relay at its
discount (plan_end.trial_offer, the invoice above the Stars page). Both carry
`s` on the pay buttons and `variant` on digest_sent, so Amplitude tells them
apart. Lock: python app/jobs/test_digest_episodes.py
"""
import time
import json

import app.service.user.language
from app.core.sender.outbox import OutboxRetryableError
from app.i18n.messages import get_message
from app.jobs import digest_outbox
from app.jobs.digest_outbox import migrate_from_kv, pending_count
from app.jobs.nosub_digest import DIGEST_MUTE_ACTION, should_send_nosub_digest
from app.jobs.relay_remind import relay_nudge_markup
from app.service import analytics_events
from app.service.payment import plan_end
from app.service.payment.storefront import SHOWCASE_TARIFF_LEVEL
from config import db_path
from db.sqliteAdapter import SQLighter
from db import ai, listening
from lib.markup import telegram_html
from lib.telegram.general.message_master import outer_sender
from lib.tools.logger import logger

IDLE_SLEEP_SECONDS = 5
SEND_PAUSE_SECONDS = 1
LISTEN_PER_ROW = 3  # five episodes: two rows, not five


def _gist(entry):
    """A summary's gist line when one was made of this episode; never fails the digest."""
    try:
        return ai.gist(entry['channel_id'], entry['title'])
    except Exception as e:
        logger.warn("digest gist:", type(e).__name__, e)
        return None


def digest_variant(telegram_id) -> str:
    """'a' or 'b', by the tens digit: the own-show nudge splits by parity, the two must not overlap."""
    return 'b' if (abs(int(telegram_id)) // 10) % 2 else 'a'


def digest_message(entries, language, gist=_gist, variant='a', offer=('', None)):
    """offer: (line, invoice row) of plan_end.trial_offer, shown in variant b."""
    lead = variant == 'b' and entries
    text = '' if lead else get_message('youHaveNewEpisodes', language)
    listen = []
    if entries:
        text += ('' if lead else '\n\n') + '<b>' + get_message('digestEpisodes', language) + '</b>'
    for index, entry in enumerate(entries, 1):
        text += '\n\n' + str(index) + '. <b>' + telegram_html.escape(
            telegram_html.plain_text(entry['show_name'])[:90]) + '</b>\n'
        text += telegram_html.escape(telegram_html.plain_text(entry['title'])[:150])
        line = gist(entry) if 'channel_id' in entry else None
        if line:
            # someone's summary of it: free to show, and what Relay gives
            text += '\n📝 <i>' + telegram_html.escape(line) + '</i>'  # the model's plain text, as in summaries
        callback = json.loads(entry['callback_json'])
        # Saved old positions can no longer be trusted; hash lookup starts at 0.
        callback['dh_n'] = callback['dh_n'].split('_')[0] + '_1'
        # tapped from a digest (Amplitude: source); compact JSON keeps it in 64 bytes
        callback['s'] = analytics_events.DIGEST_SOURCE
        listen.append({'text': str(index) + ' · ' + get_message('playLater', language),
                       'callback_data': json.dumps(callback, separators=(',', ':'))})
    offer_line, offer_row = offer if lead else ('', None)
    if lead:
        text += '\n\n' + get_message('digestRelayLine', language)
        if offer_line:
            text += '\n' + offer_line
    rows = [listen[i:i + LISTEN_PER_ROW] for i in range(0, len(listen), LISTEN_PER_ROW)]
    if offer_row:
        rows.append(offer_row)  # the discounted month in one tap, the Stars page of every plan next
    rows += relay_nudge_markup(language, extra_row=[{
        'text': get_message('nosubDigestMuteButton', language),
        'callback_data': {'tp': DIGEST_MUTE_ACTION},
    }], source=analytics_events.DIGEST_SOURCE)
    return {'type': 'text', 'text': text, 'reply_markup': rows, 'disable_web_page_preview': True}


def _relay_price(db_users) -> int:
    """Relay's price in cents now (the offer's discount is taken from it)."""
    for tariff in db_users.getTariffs():
        if int(tariff['level']) == SHOWCASE_TARIFF_LEVEL:
            return int(tariff['price'])
    return 500


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
        variant = digest_variant(user_tg_id)
        offer = ('', None)
        if variant == 'b' and entries:
            offer = plan_end.trial_offer(user_tg_id, SHOWCASE_TARIFF_LEVEL, _relay_price(db_users), user_language,
                                         analytics_events.DIGEST_SOURCE, database=database)
        sent = outer_sender(user['telegramId'], [digest_message(entries, user_language, variant=variant, offer=offer)],
                            on_flood='raise')
        if sent:
            db_users.mark_nosub_digest_sent(user_tg_id)
            listening.ack_digest(user_tg_id, entries, database)
            analytics_events.track(user_tg_id, 'digest_sent', {'episodes': len(entries), 'variant': variant,
                                                               'offer': bool(offer[1])}, database)
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
