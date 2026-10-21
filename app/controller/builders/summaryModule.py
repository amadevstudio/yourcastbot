# -*- coding: utf-8 -*-
"""The "Summary" button under an episode (app/service/ai).

A summary someone already made is sent at once, to anyone. A new one is
queued for the jobs process (app/jobs/ai_watcher.py) if the episode's length
fits what is left of the plan's hours; without a plan, or over the quota,
the user gets the plans (on the top plan only what is left: there is no bigger one).
"""
import json

from app.controller.general.notify import notify
from app.i18n.messages import get_message
from app.service.ai import quota as ai_quota, summary
from config import ai_summary_hours_per_month
from db import ai, usage
from lib.markup import telegram_html
from lib.telegram.general.message_master import render_messages


def summary_message(episode, text) -> dict:
    header = telegram_html.escape(telegram_html.plain_text(episode['show'])) + ' – ' \
        + telegram_html.escape(telegram_html.plain_text(episode['title']))
    return {'type': 'text', 'text': '📝 <b>%s</b>\n\n%s' % (header, telegram_html.escape(text)),
            'disable_web_page_preview': True}


def length_text(seconds, language_code) -> str:
    """'1 h 30 min', '45 min', '5 h': minutes rounded up."""
    hours, minutes = divmod(-(-int(seconds) // 60), 60)
    parts = [get_message('summaryHours', language_code).format(h=hours)] if hours else []
    if minutes or not hours:
        parts.append(get_message('summaryMinutes', language_code).format(m=minutes))
    return ' '.join(parts)


def offer_message(language_code, quota: ai_quota.Quota) -> dict:
    from app.service.record.free_limit import plans_offer
    if not quota.limit:
        text = get_message('summaryForPlans', language_code).format(
            relay=ai_summary_hours_per_month.get(3, 0), silver=ai_summary_hours_per_month.get(2, 0),
            bronze=ai_summary_hours_per_month.get(1, 0))
    else:
        text = get_message('summaryQuota', language_code).format(
            limit=length_text(quota.limit, language_code),
            left=length_text(quota.left, language_code),
            needed=length_text(quota.needed, language_code))
        if quota.top_plan:
            return {'type': 'text', 'text': text, 'disable_web_page_preview': True}
        text += ' ' + get_message('summaryBiggerPlan', language_code)
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

    quota = ai_quota.check(data['chat_id'], ai_quota.seconds_needed(episode))
    if not quota.allowed:
        notify(data['callback'], data['message'], '')
        render_messages(data['chat_id'], [offer_message(language_code, quota)])
        return
    ai.enqueue(data['chat_id'], ref, lang, quota.needed)
    notify(data['callback'], data['message'], get_message('summaryPreparing', language_code))
