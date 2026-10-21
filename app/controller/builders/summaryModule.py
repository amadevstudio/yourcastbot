# -*- coding: utf-8 -*-
"""The "Summary" button under an episode (app/service/ai), and questions about it.

A summary someone already made is sent at once, to anyone. A new one is
queued for the jobs process (app/jobs/ai_watcher.py) if the episode's length
fits what is left of the plan's hours; without a plan, or over the quota,
the user gets the plans (on the top plan only what is left: there is no bigger one).

A summary is a reply to the episode's audio: Telegram turns its times
("12:40 – ...") into links that play the episode from there. Under it,
"Ask" opens the route `ask` (summary.ASK_ACTION): the text the user sends
next is a question, answered from the cached transcript in this worker (one
model call with a short timeout), as a reply to the audio too. A running plan
asks quota.QUESTIONS_PER_DAY a day (a trial fewer); "Done" leaves.
"""
import json

from app.controller.general.notify import notify, render_outdated_screen
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.routes.screen_state import state_lost
from app.service import analytics_events
from app.service.ai import quota as ai_quota, summary
from config import ai_summary_hours_per_month, db_path
from db import ai, usage
from db.sqliteAdapter import SQLighter
from lib.markup import telegram_html
from lib.telegram.general.message_master import outer_sender, render_messages
from lib.tools.logger import logger


def summary_message(episode, text, ref=None, reply_to=None, language_code=None) -> dict:
    """The summary; with `ref` its Ask button, with `reply_to` a reply to the audio message."""
    header = telegram_html.escape(telegram_html.plain_text(episode['show'])) + ' – ' \
        + telegram_html.escape(telegram_html.plain_text(episode['title']))
    message = {'type': 'text', 'text': '📝 <b>%s</b>\n\n%s' % (header, telegram_html.escape(text)),
               'disable_web_page_preview': True}
    if ref:
        message['reply_markup'] = [[{'text': get_message('askButton', language_code or 'en'),
                                     'callback_data': summary.ask_button_data(ref, reply_to)}]]
    if reply_to:
        message['reply_to'] = int(reply_to)
    return message


def length_text(seconds, language_code) -> str:
    """'1 h 30 min', '45 min', '5 h': minutes rounded up."""
    hours, minutes = divmod(-(-int(seconds) // 60), 60)
    parts = [get_message('summaryHours', language_code).format(h=hours)] if hours else []
    if minutes or not hours:
        parts.append(get_message('summaryMinutes', language_code).format(m=minutes))
    return ' '.join(parts)


def offer_message(language_code, quota: ai_quota.Quota) -> dict:
    """No plan: every plan with its Stars invoice, as at the free episode limit. A running plan:
    an invoice would only top it up (storefront rules), so the Stars page and change-plan.
    The top plan: only what is left."""
    from app.service.payment.storefront import relay_nudge_markup
    from app.service.record.free_limit import plans_offer
    if not quota.limit:
        text = get_message('summaryForPlans', language_code).format(
            relay=ai_summary_hours_per_month.get(3, 0), silver=ai_summary_hours_per_month.get(2, 0),
            bronze=ai_summary_hours_per_month.get(1, 0))
        plans_text, rows = plans_offer(language_code)
        return {'type': 'text', 'text': text + '\n\n' + plans_text.strip(), 'reply_markup': rows,
                'disable_web_page_preview': True}
    text = get_message('summaryQuota', language_code).format(
        limit=length_text(quota.limit, language_code),
        left=length_text(quota.left, language_code),
        needed=length_text(quota.needed, language_code))
    if quota.top_plan:
        return {'type': 'text', 'text': text, 'disable_web_page_preview': True}
    more = (get_message('summaryTrialMore', language_code).format(relay=ai_summary_hours_per_month.get(3, 0))
            if quota.trial else get_message('summaryBiggerPlan', language_code))
    return {'type': 'text', 'text': text + ' ' + more,
            'reply_markup': relay_nudge_markup(language_code), 'disable_web_page_preview': True}


def _summary_language(chat_id, language_code) -> str:
    db_users = SQLighter(db_path)
    try:
        preference = db_users.get_user_flag(chat_id, summary.LANGUAGE_FLAG)
    finally:
        db_users.close()
    return summary.summary_language(preference, language_code)


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

    lang = _summary_language(data['chat_id'], language_code)
    audio = getattr(data['message'], 'message_id', None)  # the button is on the episode's audio
    cached = ai.summary(ref, lang)
    if cached is not None:
        notify(data['callback'], data['message'], '')
        # a reply to the audio, not a screen: the menu the user had stays
        outer_sender(data['chat_id'], [summary_message(episode, cached['text'], ref, audio, language_code)])
        usage.record_ai(data['chat_id'], ref, 0.0)
        return

    quota = ai_quota.check(data['chat_id'], ai_quota.seconds_needed(episode))
    if not quota.allowed:
        notify(data['callback'], data['message'], '')
        render_messages(data['chat_id'], [offer_message(language_code, quota)])
        return
    ai.enqueue(data['chat_id'], ref, lang, quota.needed, reply_to=audio)
    notify(data['callback'], data['message'], get_message('summaryPreparing', language_code))


def ask_offer_message(language_code) -> dict:
    """No plan: questions come with one; every plan's invoice, as for summaries."""
    from app.service.record.free_limit import plans_offer
    plans_text, rows = plans_offer(language_code)
    return {'type': 'text', 'disable_web_page_preview': True, 'reply_markup': rows,
            'text': get_message('askForPlans', language_code).format(limit=ai_quota.QUESTIONS_PER_DAY)
            + '\n\n' + plans_text.strip()}


def ask(data):
    """Route `ask`: the Ask button opens it; a message in it is a question."""
    if data['callback'] is not None:
        return open_ask(data)
    return answer_question(data)


def open_ask(data):
    language_code = data['language_code']
    if not summary.enabled():
        notify(data['callback'], data['message'], get_message('summaryUnavailable', language_code))
        return False
    try:
        call = json.loads(data['callback'].data)
        ref, audio = str(call['r']), int(call.get('m') or 0) or None
    except (AttributeError, TypeError, ValueError, KeyError):
        ref, audio = None, None
    episode = ai.episode(ref) if ref else None
    if episode is None:
        notify(data['callback'], data['message'], get_message('screenOutdated', language_code))
        return False
    if ai.transcript(ref) is None:
        notify(data['callback'], data['message'], get_message('askNeedsSummary', language_code), alert=True)
        return False
    questions = ai_quota.questions(data['chat_id'])
    if not questions.limit:
        notify(data['callback'], data['message'], '')
        outer_sender(data['chat_id'], [ask_offer_message(language_code)])
        return False
    if not questions.allowed:
        notify(data['callback'], data['message'],
               get_message('askLimit', language_code).format(limit=questions.limit), alert=True)
        return False
    notify(data['callback'], data['message'], '')
    storage.set_user_state_data(data['chat_id'], 'ask', {'ref': ref, 'audio': audio})
    render_messages(data['chat_id'], [{
        'type': 'text', 'disable_web_page_preview': True,
        'text': get_message('askPrompt', language_code).format(
            title=telegram_html.escape(telegram_html.plain_text(episode['title'])[:150]), left=questions.left),
        'reply_markup': [[{'text': get_message('askDone', language_code), 'callback_data': {'tp': 'menu'}}]],
    }], resending=True)


def answer_question(data):
    language_code = data['language_code']
    state = storage.get_user_state_data(data['chat_id'], 'ask')
    if state_lost(state, 'ref'):
        return render_outdated_screen(data)
    question = str(getattr(data['message'], 'text', '') or '').strip()
    episode, found = ai.episode(state['ref']), ai.transcript(state['ref'])
    if not question or episode is None or found is None:
        return render_outdated_screen(data)
    questions = ai_quota.questions(data['chat_id'])
    if not questions.allowed:
        outer_sender(data['chat_id'], [{'type': 'text', 'text': get_message(
            'askLimit', language_code).format(limit=questions.limit) if questions.limit
            else get_message('askForPlans', language_code).format(limit=ai_quota.QUESTIONS_PER_DAY)}])
        return
    try:
        from agent.bot_telebot import bot
        bot.send_chat_action(data['chat_id'], 'typing')
    except Exception:
        pass
    try:
        text, cost = summary.answer(found['text'], episode['title'], episode['show'], question)
    except Exception as e:
        logger.warn('ask: no answer', state['ref'], type(e).__name__, str(e)[:200])
        outer_sender(data['chat_id'], [{'type': 'text', 'text': get_message('askFailed', language_code)}])
        return
    usage.record_ask(data['chat_id'], state['ref'], cost)
    analytics_events.track(data['chat_id'], 'question_answered', {'left': questions.left - 1})
    answer = {'type': 'text', 'disable_web_page_preview': True,
              'text': '❓ <i>%s</i>\n\n%s' % (telegram_html.escape(question[:300]), telegram_html.escape(text)),
              'reply_markup': [[{'text': get_message('askDone', language_code), 'callback_data': {'tp': 'menu'}}]]}
    if state.get('audio'):
        answer['reply_to'] = int(state['audio'])
    outer_sender(data['chat_id'], [answer])
