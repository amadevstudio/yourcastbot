"""Stateless personal feed status and saved-episode screens."""
import json

from app.controller.general.notify import notify, notify_outdated_screen
from app.i18n.messages import get_message
from app.routes.message_tools import go_back_inline_markup
from db import feed_recovery, listening
from lib.markup import telegram_html
from lib.telegram.general.message_master import render_messages

PER_PAGE = 5


def callback_data(data):
    try:
        value = json.loads(data['callback'].data) if data['callback'] else {}
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def page_number(params):
    try:
        return max(1, min(100000, int(params.get('p', 1))))
    except (ValueError, TypeError):
        return 1


def page_buttons(route, page, has_next):
    row = []
    if page > 1:
        row.append({'text': '←', 'callback_data': {'tp': route, 'p': page - 1}})
    if has_next:
        row.append({'text': '→', 'callback_data': {'tp': route, 'p': page + 1}})
    return [row] if row else []


def subscriptions(chat_id, database=None):
    conn = feed_recovery.connect(database)
    try:
        return [dict(r) for r in conn.execute(
            'SELECT c.id,c.name,s.notify FROM user_channel_cs s '
            'JOIN channels c ON c.id=s.channel_id WHERE s.user_telegram_id=? '
            'ORDER BY c.name,c.id', (chat_id,))]
    finally:
        conn.close()


def status_key(state):
    if state and state['paused']:
        return 'feedPaused'
    if state and state['status'] in ('pending', 'leased'):
        return 'feedChecking'
    return 'feedAvailable' if state else 'feedUnchecked'


def construct_feed_status(chat_id, lang, page=1, database=None):
    rows = subscriptions(chat_id, database)
    page = min(page, max(1, (len(rows) + PER_PAGE - 1) // PER_PAGE))
    selected = rows[(page - 1) * PER_PAGE:page * PER_PAGE]
    states = feed_recovery.statuses([r['id'] for r in selected], database)
    text = '<b>' + get_message('deliveryStatus', lang) + '</b>\n\n' + get_message('feedStatusHelp', lang)
    keyboard = []
    for row in selected:
        name = telegram_html.escape(telegram_html.plain_text(row['name'])[:150])
        text += '\n\n' + ('🔔 ' if row['notify'] else '🔕 ') + '<b>' + name + '</b>\n'
        text += get_message(status_key(states.get(row['id'])), lang)
        keyboard.append([{
            'text': telegram_html.plain_text(row['name'])[:70],
            'callback_data': {'tp': 'podcast', 'id': row['id']},
        }, {
            'text': get_message('feedCheck', lang),
            'callback_data': {'tp': 'feedCheck', 'id': row['id']},
        }])
    keyboard += page_buttons('feedStatus', page, page * PER_PAGE < len(rows))
    keyboard += go_back_inline_markup(lang)
    return [{'type': 'text', 'text': text, 'reply_markup': keyboard,
             'disable_web_page_preview': True}]


def open_feed_status(data):
    render_messages(data['chat_id'], construct_feed_status(
        data['chat_id'], data['language_code'], page_number(callback_data(data))),
        resending=data['is_command'])


def check_feed(data):
    params = callback_data(data)
    # Never trust a channel id supplied by a callback, including old/forwarded messages.
    owned = {r['id'] for r in subscriptions(data['chat_id'])}
    if type(params.get('id')) is not int or params['id'] not in owned:
        return notify_outdated_screen(data)
    feed_recovery.enqueue(params['id'], 'manual', manual=True)
    notify(data['callback'], data['message'], get_message('feedCheckQueued', data['language_code']))


def construct_saved(chat_id, lang, page=1, database=None):
    entries = listening.saved(chat_id, database)
    page = min(page, max(1, (len(entries) + PER_PAGE - 1) // PER_PAGE))
    selected = entries[(page - 1) * PER_PAGE:page * PER_PAGE]
    text = '<b>' + get_message('listenLater', lang) + '</b>'
    keyboard = []
    if not entries:
        text += '\n\n' + get_message('savedEmpty', lang)
    for entry in selected:
        text += '\n\n<b>' + telegram_html.escape(telegram_html.plain_text(entry['show_name'])[:100]) + '</b>\n'
        text += telegram_html.escape(telegram_html.plain_text(entry['title'])[:180])
        keyboard.append([{
            'text': get_message('playLater', lang),
            'callback_data': {'tp': 'playLater', 'e': entry['id']},
        }, {
            'text': get_message('removeLater', lang),
            'callback_data': {'tp': 'removeLater', 'e': entry['id'], 'p': page},
        }])
    keyboard += page_buttons('listenLater', page, page * PER_PAGE < len(entries))
    keyboard += go_back_inline_markup(lang)
    return [{'type': 'text', 'text': text, 'reply_markup': keyboard,
             'disable_web_page_preview': True}]


def open_saved(data):
    render_messages(data['chat_id'], construct_saved(data['chat_id'], data['language_code'],
                    page_number(callback_data(data))), resending=data['is_command'])


def save_later(data):
    episode = callback_data(data).get('e')
    if type(episode) is not int:
        return notify_outdated_screen(data)
    result = listening.add_saved(data['chat_id'], episode)
    notify(data['callback'], data['message'], get_message(result, data['language_code']))


def remove_later(data):
    episode = callback_data(data).get('e')
    if type(episode) is not int:
        return notify_outdated_screen(data)
    listening.remove_saved(data['chat_id'], episode)
    open_saved(data)


def play_later(data):
    from app.controller.builders.recsModule import send_record_direct
    wanted = callback_data(data).get('e')
    entry = next((e for e in listening.saved(data['chat_id']) if e['id'] == wanted), None)
    if entry is None:
        return notify_outdated_screen(data)
    callback = json.loads(entry['callback_json'])
    channel = (feed_recovery.channel(callback['id']) if callback.get('id') is not None
               else {'itunes_id': callback['iid']})
    notify(data['callback'], data['message'], get_message('needTimeToLoad', data['language_code']))
    # A feed can grow since this item was saved. Search by hash from the start,
    # not from the old position. Ordinary rec/outbox rules still apply.
    send_record_direct(channel, data['chat_id'], data['language_code'],
                       callback['dh_n'].split('_')[0], 0)
