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
asks quota.QUESTIONS_PER_DAY a day (a trial fewer). "Done" leaves: its button
goes and the menu comes as a new message at the bottom (a plain `menu` tap
would redraw the old question screen up the chat). A text after
ASK_IDLE_SECONDS without a question is a search, as it was before Ask.
"""
import json
import time

from app.controller.general.notify import notify, render_outdated_screen
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.routes.screen_state import state_lost
from app.service import analytics_events
from app.service.ai import quota as ai_quota, summary
# the over-quota offer is shared with automatic summaries (app/service/ai/auto.py)
from app.service.ai.offer import offer_message
from config import db_path
from db import ai, usage
from db.sqliteAdapter import SQLighter
from lib.markup import telegram_html
from lib.telegram.general.message_master import message_deleter, message_editor, outer_sender, render_messages
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
    notify(data['callback'], data['message'], '')
    # a status line under the audio, edited by the worker as it goes and into the summary (ai_watcher)
    status = status_line(data['chat_id'], get_message('summaryStatusQueued', language_code), audio)
    _, new = ai.enqueue(data['chat_id'], ref, lang, quota.needed, reply_to=audio, status_message=status)
    if not new and status:  # a second tap: the first one's line is already there
        try:
            message_deleter(data['chat_id'], status)
        except Exception:
            pass


def status_line(chat_id, text, reply_to=None) -> int | None:
    """A status message (a reply to the audio when known); its id, None if it did not go."""
    structure = {'type': 'text', 'text': text}
    if reply_to:
        structure['reply_to'] = int(reply_to)
    try:
        sent = outer_sender(chat_id, [structure])
        return int(sent[0]['id']) if sent and sent[0].get('id') else None  # message_master's result
    except Exception as e:
        logger.warn('summary status:', type(e).__name__, e)
        return None


def ask_offer_message(language_code) -> dict:
    """No plan: questions come with one; every plan's invoice, as for summaries."""
    from app.service.record.free_limit import plans_offer
    plans_text, rows = plans_offer(language_code)
    return {'type': 'text', 'disable_web_page_preview': True, 'reply_markup': rows,
            'text': get_message('askForPlans', language_code).format(limit=ai_quota.QUESTIONS_PER_DAY)
            + '\n\n' + plans_text.strip()}


def limit_message(language_code, questions) -> dict:
    """The day's questions are used up; a trial hears what paying gives, with the Stars page
    and change-plan (a running plan: an invoice would only top it up, as for summaries)."""
    text = get_message('askLimit', language_code).format(limit=questions.limit)
    if not questions.trial:
        return {'type': 'text', 'text': text}
    from app.service.payment.storefront import relay_nudge_markup
    return {'type': 'text', 'disable_web_page_preview': True, 'reply_markup': relay_nudge_markup(language_code),
            'text': text + ' ' + get_message('askTrialMore', language_code).format(limit=ai_quota.QUESTIONS_PER_DAY)}


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
        notify(data['callback'], data['message'], '')
        outer_sender(data['chat_id'], [limit_message(language_code, questions)])
        return False
    notify(data['callback'], data['message'], '')
    storage.set_user_state_data(data['chat_id'], 'ask', {'ref': ref, 'audio': audio, 'at': time.time()})
    render_messages(data['chat_id'], [{
        'type': 'text', 'disable_web_page_preview': True,
        'text': get_message('askPrompt', language_code).format(
            title=telegram_html.escape(telegram_html.plain_text(episode['title'])[:150]), left=questions.left),
        'reply_markup': done_markup(language_code),
    }], resending=True)


def answer_question(data):
    language_code = data['language_code']
    state = storage.get_user_state_data(data['chat_id'], 'ask')
    if state_lost(state, 'ref'):
        return render_outdated_screen(data)
    question = str(getattr(data['message'], 'text', '') or '').strip()
    if time.time() - float(state.get('at') or 0) > summary.ASK_IDLE_SECONDS or is_link(question):
        # long after the last question, or a podcast link: the user is searching, as before Ask
        return search_instead(data)
    if not question:  # a voice message, a photo
        outer_sender(data['chat_id'], [{'type': 'text', 'text': get_message('askTextOnly', language_code)}])
        return
    episode, found = ai.episode(state['ref']), ai.transcript(state['ref'])
    if episode is None or found is None:
        return render_outdated_screen(data)
    questions = ai_quota.questions(data['chat_id'])
    if not questions.allowed:
        outer_sender(data['chat_id'], [limit_message(language_code, questions) if questions.limit
                                       else ask_offer_message(language_code)])
        return
    # "Thinking...": a reply to the audio, edited into the answer (or into "could not")
    status = status_line(data['chat_id'], get_message('askThinking', language_code), state.get('audio'))
    try:
        text, cost = summary.answer(found['text'], episode['title'], episode['show'], question)
    except Exception as e:
        logger.warn('ask: no answer', state['ref'], type(e).__name__, str(e)[:200])
        show_result(data['chat_id'], {'type': 'text', 'text': get_message('askFailed', language_code)}, status)
        return
    usage.record_ask(data['chat_id'], state['ref'], cost)
    storage.set_user_state_data(data['chat_id'], 'ask', dict(state, at=time.time()))
    analytics_events.track(data['chat_id'], 'question_answered', {'left': questions.left - 1})
    answer = {'type': 'text', 'disable_web_page_preview': True,
              'text': '❓ <i>%s</i>\n\n%s' % (telegram_html.escape(question[:300]), telegram_html.escape(text)),
              'reply_markup': done_markup(language_code)}
    if state.get('audio'):
        answer['reply_to'] = int(state['audio'])
    show_result(data['chat_id'], answer, status)


def show_result(chat_id, message, status=None):
    """The status line edited into `message`; a new message when there is none or it is gone."""
    if status:
        try:
            message_editor(chat_id, message, status)
            return
        except Exception as e:
            logger.warn('ask status:', type(e).__name__, e)
    outer_sender(chat_id, [message])


def done_markup(language_code):
    return [[{'text': get_message('askDone', language_code), 'callback_data': {'tp': summary.ASK_DONE_ACTION}}]]


def finish_ask(data):
    """ "Done": the questions end here; the button goes, the menu comes at the bottom of the chat."""
    from app.controller.builders.menuModule import construct_menu_message
    from agent.bot_telebot import bot
    notify(data['callback'], data['message'], '')
    try:
        bot.edit_message_reply_markup(data['chat_id'], data['callback'].message.message_id, reply_markup=None)
    except Exception:
        pass  # an old message: the menu still comes
    storage.clear_user_storage(data['chat_id'])
    storage.add_user_state(data['chat_id'], 'menu')
    render_messages(data['chat_id'], construct_menu_message(data['language_code'], data['chat_id']),
                    resending=True)


def is_link(text) -> bool:
    return text.lower().startswith(('http://', 'https://')) and ' ' not in text


def search_instead(data):
    """A text long after the last question: the user is searching again, as before Ask."""
    from app.controller.builders import searchModule
    storage.add_user_state(data['chat_id'], 'search')
    data['route_name'], data['united_data'] = 'search', {}
    searchModule.search(data)
    return False
