# -*- coding: utf-8 -*-
"""An OPML file sent to the bot: its podcasts subscribed to (app/service/podcast/opml.py).

The file arrives in any state (initialize_routes reads it before the routes).
The import fetches every feed it subscribes to, a minute or more for a long
list, so it runs in a thread of its own: the incoming worker and the chat's
other taps are not held. One import per chat at a time. A status message
counts the feeds as it goes; the result names what was added, what the user
had, what did not open and, without a plan, what is over the free limit,
with Relay's invoice one tap away (as at the limit on the podcast page).
add_sub writes the subscribed channel into the podcast screen's state: the
import puts back what was there, so a podcast page left open still acts on
its own podcast.
"""
import threading

from app.controller.builders.onboarding import subscribe_room
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.service import analytics_events
from app.service.podcast import opml
from app.service.podcast.subscription import add_sub
from config import db_path
from db.connection import connect_sqlite
from lib.markup import telegram_html
from lib.telegram.general.message_master import message_editor, outer_sender
from lib.tools.logger import logger

PROGRESS_EVERY = 5
NAMES_SHOWN = 15

_running: set = set()
_lock = threading.Lock()


def _text(language_code, key, **values) -> dict:
    return {'type': 'text', 'text': get_message(key, language_code).format(**values)}


def import_file(data):
    """The handler: `data['opml']` is the file's bytes."""
    chat_id, language_code = data['chat_id'], data['language_code']
    try:
        feeds = opml.parse(data.get('opml') or b'')
    except opml.OpmlError as e:
        logger.warn("opml:", chat_id, e)
        outer_sender(chat_id, [_text(language_code, 'opmlBad')])
        return
    if not feeds:
        outer_sender(chat_id, [_text(language_code, 'opmlEmpty')])
        return
    with _lock:
        if chat_id in _running:
            outer_sender(chat_id, [_text(language_code, 'opmlBusy')])
            return
        _running.add(chat_id)
    try:
        total = min(len(feeds), opml.MAX_FEEDS)
        sent = outer_sender(chat_id, [_text(language_code, 'opmlStarted', count=total)])
        status_id = sent[0].get('message_id') if sent else None
        threading.Thread(target=_run, args=(chat_id, language_code, feeds, status_id),
                         name='opml-%s' % chat_id, daemon=True).start()
    except Exception:
        with _lock:
            _running.discard(chat_id)
        raise


def _run(chat_id, language_code, feeds, status_id):
    try:
        connection = connect_sqlite(db_path)
        try:
            known = opml.known_channels(connection)
            subscribed = {int(row[0]) for row in connection.execute(
                'SELECT channel_id FROM user_channel_cs WHERE user_telegram_id = ?', (int(chat_id),))}
        finally:
            connection.close()

        def progress(number, total):
            if status_id and number > 1 and (number - 1) % PROGRESS_EVERY == 0:
                try:
                    message_editor(chat_id, _text(language_code, 'opmlProgress', done=number - 1, count=total),
                                   status_id)
                except Exception:
                    pass  # a status line: the import goes on

        result = opml.import_feeds(chat_id, feeds, known, subscribed, subscribe_room(chat_id),
                                   subscribe_keeping_screen,
                                   progress=progress)
        if status_id:  # the status line ends at the full count, not where the last edit left it
            total = min(len(feeds), opml.MAX_FEEDS)
            try:
                message_editor(chat_id, _text(language_code, 'opmlProgress', done=total, count=total), status_id)
            except Exception:
                pass
        outer_sender(chat_id, [result_message(language_code, result, len(feeds) > opml.MAX_FEEDS)])
        analytics_events.track(chat_id, 'opml_import', {
            'feeds': len(feeds), 'done': len(result.done), 'had': len(result.had),
            'failed': len(result.failed), 'over': len(result.over)})
    except Exception as e:
        logger.err("opml import:", chat_id, type(e).__name__, e)
        try:
            outer_sender(chat_id, [_text(language_code, 'opmlFailed')])
        except Exception:
            pass
    finally:
        with _lock:
            _running.discard(chat_id)


def subscribe_keeping_screen(chat_id, channel_id, service_id, service_name):
    """add_sub, with the podcast screen's state as it was before it."""
    saved = storage.get_user_state_data(chat_id, 'podcast')
    try:
        return add_sub(chat_id, channel_id, service_id, service_name)
    finally:
        if saved is None:
            storage.del_user_state_data(chat_id, 'podcast')
        else:
            storage.set_user_state_data(chat_id, 'podcast', saved)


def _names(items) -> str:
    shown = ', '.join(telegram_html.escape(telegram_html.plain_text(item)) for item in items[:NAMES_SHOWN])
    return shown + (' …' if len(items) > NAMES_SHOWN else '')


def result_message(language_code, result: opml.Result, cut: bool = False) -> dict:
    parts = []
    if result.done:
        parts.append(get_message('opmlDone', language_code).format(count=len(result.done), names=_names(result.done)))
    if result.had:
        parts.append(get_message('opmlHad', language_code).format(count=len(result.had)))
    if result.failed:
        parts.append(get_message('opmlFailedFeeds', language_code).format(
            count=len(result.failed), names=_names(result.failed)))
    if cut:
        parts.append(get_message('opmlCut', language_code).format(limit=opml.MAX_FEEDS))
    message = {'type': 'text', 'disable_web_page_preview': True}
    if result.over:
        # the next line names the limit
        parts.append(get_message('opmlOver', language_code).format(count=len(result.over), names=_names(result.over)))
        parts.append(get_message('withoutTariffSubscriptionsLimited', language_code))
        from app.service.payment.storefront import relay_nudge_markup
        message['reply_markup'] = relay_nudge_markup(language_code, invoice=True)
    if not parts:
        parts.append(get_message('opmlEmpty', language_code))
    message['text'] = '\n\n'.join(parts)
    return message
