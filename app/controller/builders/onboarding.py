# -*- coding: utf-8 -*-
"""The welcome screen: tick several popular podcasts, subscribe in one tap.

Most new users used to end with the one podcast /start gives them (TED
Talks Daily): the old screen opened a podcast page per tap. Now the top
podcasts in the user's language are checkboxes and one button subscribes
to all ticked ones.

The handler cannot read the keyboard back (Telethon callbacks carry only
the data), so every button carries the selection as a bitmask over the
list and a checksum of the list: the list is rebuilt on each tap, and a
list that changed in between is redrawn rather than subscribed to.
"""
import json

from app.i18n.messages import get_message
from app.service.podcast.subscription import add_sub
from config import db_path, max_subscriptions_without_tariff
from db.sqliteAdapter import SQLighter
from lib.markup import telegram_html
from lib.telegram.general.message_master import MessageStructuresInterface

PICKS = 8
PICK_ACTION = 'wPick'
SUBSCRIBE_ACTION = 'wSub'
NAME_LIMIT = 48


def top_podcasts(language_code, count=PICKS, database=None) -> list[dict]:
    """Popular podcasts in the user's language first, then worldwide ones."""
    db_users = SQLighter(db_path if database is None else database)
    try:
        top_list = [dict(row) for row in db_users.select_top(
            None, language_code, True, None, None, count, 0)]
        if len(top_list) < count:
            seen = {row['id'] for row in top_list}
            for row in db_users.select_top(None, language_code, False, None, None, count, 0):
                if len(top_list) >= count:
                    break
                if row['id'] not in seen:
                    top_list.append(dict(row))
                    seen.add(row['id'])
    finally:
        db_users.close()
    return top_list


def list_checksum(top_list) -> int:
    return sum((index + 1) * int(row['id']) for index, row in enumerate(top_list)) % 997


def picked(top_list, mask) -> list[dict]:
    return [row for index, row in enumerate(top_list) if int(mask) >> index & 1]


def welcome_message(language_code, top_list, mask=0) -> list[MessageStructuresInterface]:
    checksum = list_checksum(top_list)
    rows = []
    for index, row in enumerate(top_list):
        ticked = int(mask) >> index & 1
        name = telegram_html.plain_text(row['name'])[:NAME_LIMIT]
        rows.append([{
            'text': ('✅ ' if ticked else '▫️ ') + name,
            'callback_data': {'tp': PICK_ACTION, 'i': index, 'm': int(mask), 'h': checksum},
        }])
    if top_list:
        rows.append([{
            'text': get_message('welcomeSubscribePicked', language_code).format(
                count=len(picked(top_list, mask))),
            'callback_data': {'tp': SUBSCRIBE_ACTION, 'm': int(mask), 'h': checksum},
        }])
    rows.append([{'text': get_message('goToSearch', language_code), 'callback_data': {'tp': 'search'}}])
    rows.append([{'text': get_message('skipWelcome', language_code), 'callback_data': {'tp': 'menu'}}])
    text = get_message('welcomeMessage', language_code)
    if top_list:
        text += '\n\n' + get_message('welcomePickHint', language_code)
    return [{'type': 'text', 'text': text, 'reply_markup': rows}]


def read_tap(callback_data) -> tuple[int | None, int, int | None]:
    """(index or None, mask, checksum or None) from a welcome button."""
    try:
        data = json.loads(callback_data) if isinstance(callback_data, str) else dict(callback_data)
    except (TypeError, ValueError):
        return None, 0, None
    index = data.get('i')
    return (int(index) if index is not None else None), int(data.get('m') or 0), data.get('h')


def subscribe_room(chat_id, database=None):
    """How many more podcasts this chat may add: None when unlimited (a running plan)."""
    db_users = SQLighter(db_path if database is None else database)
    try:
        subscription = db_users.getUserSubscriptionByTg(chat_id)
        if subscription is not None and subscription['tariff_id'] > 0 and subscription['time_left'] > 0:
            return None
        return max(0, max_subscriptions_without_tariff - db_users.get_uccs_count_by_tg(chat_id))
    finally:
        db_users.close()


def subscribe(chat_id, rows, database=None, subscriber=add_sub) -> tuple[list[str], list[str], list[str]]:
    """Subscribe to rows in order: (subscribed names, failed names, names over the free limit)."""
    room = subscribe_room(chat_id, database)
    done, failed, over = [], [], []
    db_users = SQLighter(db_path if database is None else database)
    try:
        channels = {row['id']: db_users.get_channel(row['id']) for row in rows}
    finally:
        db_users.close()
    for row in rows:
        name = telegram_html.plain_text(row['name'])
        if room is not None and len(done) >= room:
            over.append(name)
            continue
        channel = channels.get(row['id'])
        if channel is None:
            failed.append(name)
            continue
        if channel['itunes_id']:
            result, _ = subscriber(chat_id, channel['id'], channel['itunes_id'], 'itunes')
        else:
            result, _ = subscriber(chat_id, channel['id'], channel['rss_link'], 'rss')
        (done if result is not None else failed).append(name)
    return done, failed, over


def result_message(language_code, done, failed, over) -> list[MessageStructuresInterface]:
    def names(items):
        return ', '.join(telegram_html.escape(item) for item in items)

    parts = []
    if done:
        parts.append(get_message('welcomeSubscribed', language_code).format(names=names(done)))
    if failed:
        parts.append(get_message('welcomeSubscribeFailed', language_code).format(names=names(failed)))
    if over:
        parts.append(get_message('freeLimitReached', language_code).format(
            limit=max_subscriptions_without_tariff) + ': ' + names(over))
    rows = [[{'text': get_message('goToSearch', language_code), 'callback_data': {'tp': 'search'}}],
            [{'text': get_message('goBackMenu', language_code), 'callback_data': {'tp': 'menu'}}]]
    return [{'type': 'text', 'text': '\n\n'.join(parts), 'reply_markup': rows}]
