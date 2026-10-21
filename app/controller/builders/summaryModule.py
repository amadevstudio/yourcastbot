# -*- coding: utf-8 -*-
"""The "Summary" button under an episode (app/service/ai).

A summary someone already made is sent at once, to anyone. A new one is
queued for the jobs process (app/jobs/ai_watcher.py) if the plan's monthly
quota allows; without a plan, or over the quota, the user gets the plans.
"""
import json

from app.controller.general.notify import notify
from app.i18n.messages import get_message
from app.service.ai import summary
from config import ai_summaries_per_month
from db import ai, usage
from lib.markup import telegram_html
from lib.telegram.general.message_master import render_messages

SUMMARY_ACTION = 'sum'


def button(ref, language_code) -> dict:
    return {'text': get_message('summaryButton', language_code),
            'callback_data': {'tp': SUMMARY_ACTION, 'r': ref}}


def summary_message(episode, text) -> dict:
    header = telegram_html.escape(telegram_html.plain_text(episode['show'])) + ' – ' \
        + telegram_html.escape(telegram_html.plain_text(episode['title']))
    return {'type': 'text', 'text': '📝 <b>%s</b>\n\n%s' % (header, telegram_html.escape(text)),
            'disable_web_page_preview': True}


def offer_message(language_code, limit, used) -> dict:
    from app.service.record.free_limit import plans_offer
    if limit:
        text = get_message('summaryQuotaUsed', language_code).format(used=min(used, limit), limit=limit)
    else:
        text = get_message('summaryForPlans', language_code).format(
            relay=ai_summaries_per_month.get(3, 0), silver=ai_summaries_per_month.get(2, 0),
            bronze=ai_summaries_per_month.get(1, 0))
    plans_text, rows = plans_offer(language_code)
    return {'type': 'text', 'text': text + '\n\n' + plans_text.strip(), 'reply_markup': rows,
            'disable_web_page_preview': True}


def request_summary(data):
    language_code = data['language_code']
    if not summary.enabled():
        notify(data['callback'], data['message'], get_message('summaryUnavailable', language_code))
        return
    try:
        ref = str(json.loads(data['callback'].data)['r'])
    except (AttributeError, TypeError, ValueError, KeyError):
        ref = None
    episode = ai.episode(ref) if ref else None
    if episode is None:
        notify(data['callback'], data['message'], get_message('screenOutdated', language_code))
        return

    lang = summary.language_of(language_code)
    cached = ai.summary(ref, lang)
    if cached is not None:
        notify(data['callback'], data['message'], '')
        render_messages(data['chat_id'], [summary_message(episode, cached['text'])])
        usage.record_ai(data['chat_id'], ref, 0.0)
        return

    allowed, limit, used = summary.quota(data['chat_id'])
    if not allowed:
        notify(data['callback'], data['message'], '')
        render_messages(data['chat_id'], [offer_message(language_code, limit, used)])
        return
    ai.enqueue(data['chat_id'], ref, lang)
    notify(data['callback'], data['message'], get_message('summaryPreparing', language_code))
