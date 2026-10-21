# -*- coding: utf-8 -*-
"""The welcome screen: tick several popular podcasts, subscribe in one tap.

Most new users used to end with the one podcast /start gives them (TED
Talks Daily): the old screen opened a podcast page per tap. Now the top
podcasts in the user's language are checkboxes and one button subscribes
to all ticked ones.

The handler cannot read the keyboard back (Telethon callbacks carry only
the data), so every button carries the selection as a bitmask over the
list and a checksum of the list: the list is rebuilt on each tap, and a
list that changed in between is redrawn rather than subscribed to. Telethon
gives the data as bytes.

"Popular in your language" is popular among users whose Telegram has that
language, and many listeners of Persian shows run Telegram in English. A
show whose name is written in a script the language does not use (Arabic
letters for English) is left out: the list stays readable. Podcasts the
user already has are left out too: /start again suggests new ones, and
ticking one they have would only re-fetch its feed and take a free slot.
"""
import json
import unicodedata

from app.i18n.messages import get_message
from app.service.podcast.subscription import add_sub
from config import db_path, max_subscriptions_without_tariff
from db.sqliteAdapter import SQLighter
from lib.markup import telegram_html
from lib.tools.logger import logger
from lib.telegram.general.message_master import MessageStructuresInterface

PICKS = 8
# the scripts a language's own listeners read; other languages are not filtered
SCRIPTS = {'en': {'LATIN'}, 'pt': {'LATIN'}, 'es': {'LATIN'}, 'de': {'LATIN'},
           'ru': {'CYRILLIC', 'LATIN'}, 'he': {'HEBREW', 'LATIN'}}
PICK_ACTION = 'wPick'
SUBSCRIBE_ACTION = 'wSub'
NAME_LIMIT = 48


def name_scripts(name) -> set:
    """The scripts the letters of `name` are written in ({'LATIN', 'ARABIC'}...)."""
    return {unicodedata.name(char, '').split(' ')[0] for char in str(name or '') if char.isalpha()}


def readable(name, language_code) -> bool:
    """Every letter in a script the language's readers read ('پادکست WonderLand' is not English)."""
    scripts = SCRIPTS.get(str(language_code or '').split('-')[0].lower())
    return scripts is None or name_scripts(name) <= scripts


def top_podcasts(language_code, chat_id=None, count=PICKS, database=None) -> list[dict]:
    """Popular podcasts in the user's language first, then worldwide ones, readable names only,
    without the ones this chat is subscribed to."""
    db_users = SQLighter(db_path if database is None else database)
    try:
        seen = set() if chat_id is None else {
            row['channel_id'] for row in db_users.get_uccs_by_tg(chat_id, notifications_enabled=False)}
        top_list, spare = [], count * 2 + len(seen)  # rows left out as unreadable or already subscribed
        for lang_top in (True, False):
            for row in db_users.select_top(None, language_code, lang_top, None, None, count + spare, 0):
                if len(top_list) >= count:
                    break
                if row['id'] not in seen and readable(row['name'], language_code):
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
    text = get_message('welcome', language_code)
    if top_list:
        text += '\n' + get_message('welcomePickHint', language_code)
    return [{'type': 'text', 'text': text, 'reply_markup': rows}]


def read_tap(callback_data) -> tuple[int | None, int, int | None]:
    """(index or None, mask, checksum or None) from a welcome button (str, bytes or dict)."""
    try:
        data = json.loads(callback_data) if isinstance(callback_data, (str, bytes)) else dict(callback_data)
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
        try:
            if channel['itunes_id']:
                result, _ = subscriber(chat_id, channel['id'], channel['itunes_id'], 'itunes')
            else:
                result, _ = subscriber(chat_id, channel['id'], channel['rss_link'], 'rss')
        except Exception as e:  # iTunes or the feed did not answer: name it, go on with the rest
            logger.warn("welcome subscribe:", channel['id'], e)
            result = None
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
