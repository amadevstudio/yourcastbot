# -*- coding: utf-8 -*-
"""Questions about a whole podcast (app/service/ai/show_ask.py): the button on its page.

The button opens the route `showAsk`, a screen with Back to the page; the
texts the user sends there are questions. Each one gets one text answer, a
new message: the episodes it is based on as numbers, a download button per
episode (the ordinary rec button) and Back. The next question is typed
right away. Same daily count as questions about an episode
(quota.QUESTIONS_PER_DAY, a trial fewer, a running plan only); it is
answered in the incoming worker, like those.
"""
import time

from app.controller.builders import summaryModule
from app.controller.general.notify import notify, render_outdated_screen
from app.controller.types_helpers.recs import rec_callback_data_identifier
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.routes.message_tools import go_back_inline_button, go_back_inline_markup
from app.routes.screen_state import state_lost
from app.service import analytics_events
from app.service.ai import quota as ai_quota, show_ask, summary
from db import ai, usage
from lib.markup import telegram_html
from lib.telegram.general.message_master import render_messages
from lib.tools.logger import logger

PODCAST_KEYS = ('id', 'service_id', 'service_name', 'title')


def button(language_code) -> dict:
    """The podcast page's button; none while AI is off."""
    return {'text': get_message('showAskButton', language_code), 'callback_data': {'tp': show_ask.ACTION}}


def show_ask_route(data):
    """Route `showAsk`: the page's button opens it; a message in it is a question."""
    if data['callback'] is not None:
        return open_screen(data)
    return answer_question(data)


def open_screen(data):
    language_code = data['language_code']
    if not summary.enabled():
        notify(data['callback'], data['message'], get_message('summaryUnavailable', language_code))
        return False
    podcast = storage.get_user_state_data(data['chat_id'], 'podcast')
    if state_lost(podcast, *PODCAST_KEYS) or podcast.get('unavailable'):
        return render_outdated_screen(data)
    questions = ai_quota.questions(data['chat_id'])
    if not questions.allowed:
        notify(data['callback'], data['message'], '')
        render_messages(data['chat_id'], [summaryModule.limit_message(language_code, questions) if questions.limit
                                          else summaryModule.ask_offer_message(language_code)], resending=True)
        return False
    notify(data['callback'], data['message'], '')
    storage.set_user_state_data(data['chat_id'], show_ask.ACTION, {'at': time.time()})
    render_messages(data['chat_id'], [{
        'type': 'text', 'disable_web_page_preview': True,
        'text': get_message('showAskPrompt', language_code).format(
            title=telegram_html.escape(telegram_html.plain_text(podcast['title'])[:150]), left=questions.left),
        'reply_markup': go_back_inline_markup(language_code),
    }])


def answer_question(data):
    language_code = data['language_code']
    state = storage.get_user_state_data(data['chat_id'], show_ask.ACTION)
    podcast = storage.get_user_state_data(data['chat_id'], 'podcast')
    if state_lost(state, 'at') or state_lost(podcast, *PODCAST_KEYS):
        return render_outdated_screen(data)
    question = str(getattr(data['message'], 'text', '') or '').strip()
    if time.time() - float(state['at'] or 0) > summary.ASK_IDLE_SECONDS or summaryModule.is_link(question):
        # long after the last question, or a podcast link: the user is searching, as before
        return summaryModule.search_instead(data)
    if not question:  # a voice message, a photo
        render_messages(data['chat_id'], [_with_back(
            {'type': 'text', 'text': get_message('askTextOnly', language_code)}, language_code)], resending=True)
        return
    questions = ai_quota.questions(data['chat_id'])
    if not questions.allowed:
        render_messages(data['chat_id'], [summaryModule.limit_message(language_code, questions) if questions.limit
                                          else summaryModule.ask_offer_message(language_code)], resending=True)
        return
    status = summaryModule.status_line(data['chat_id'], get_message('askThinking', language_code))
    try:
        context = _context(podcast)
        if not context.episodes:
            raise summary.SummaryUnavailable('no episodes in the feed')
        text, cost = show_ask.answer(context, telegram_html.plain_text(podcast['title']), question)
    except Exception as e:
        logger.warn('show ask: no answer', podcast.get('id'), type(e).__name__, str(e)[:200])
        summaryModule.show_result(data['chat_id'], _with_back(
            {'type': 'text', 'text': get_message('askFailed', language_code)}, language_code), status)
        return
    text, cited = show_ask.cite(text, context.episodes)
    usage.record_ask(data['chat_id'], 'show:%s' % (podcast['id'] or podcast['service_id']), cost)
    storage.set_user_state_data(data['chat_id'], show_ask.ACTION, dict(state, at=time.time()))
    analytics_events.track(data['chat_id'], 'question_answered', {
        'scope': 'show', 'left': questions.left - 1, 'cited': len(cited),
        'transcripts': context.transcripts, 'descriptions': context.descriptions})
    summaryModule.show_result(data['chat_id'], answer_message(
        question, text, cited, context, podcast, language_code), status)


def answer_message(question, text, cited, context, podcast, language_code) -> dict:
    basis = get_message('showAskBasis', language_code).format(
        transcripts=context.transcripts, descriptions=context.descriptions)
    rows = [[{'text': ('⬇️ %d. %s' % (number, episode.title or episode.date))[:60],
              'callback_data': rec_callback_data_identifier(
                  podcast['id'], podcast['service_id'], podcast['service_name'], episode.dh, 1)}]
            for number, episode in enumerate(cited, 1)]
    return _with_back({
        'type': 'text', 'disable_web_page_preview': True, 'reply_markup': rows,
        'text': '❓ <i>%s</i>\n\n%s\n\n<i>%s</i>' % (
            telegram_html.escape(question[:300]), telegram_html.escape(text), telegram_html.escape(basis))},
        language_code)


def _with_back(message, language_code) -> dict:
    message['reply_markup'] = list(message.get('reply_markup') or []) + [[go_back_inline_button(language_code)]]
    return message


def _context(podcast) -> show_ask.Context:
    from app.controller.builders.recsModule import load_podcast_root
    root, _ = load_podcast_root(dict(podcast))  # the copy feed_cache keeps: no download each question
    transcripts = ai.channel_transcripts(podcast['id']) if podcast['id'] is not None else []
    return show_ask.build(show_ask.feed_episodes(root), transcripts)
