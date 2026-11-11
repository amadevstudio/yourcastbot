# -*- coding: utf-8 -*-
"""The answers to the survey (app/jobs/why_survey.py): why no plan, or why the trial went unused.

A reason's button opens the route `why`: the answer is kept (`users.flags`
`why_answer`, the last one tapped), counted (`survey_answer`) and sent to the
creator, and the question (the tapped message) turns into one asking for a few
words more (the idle trials: what got in the way), with the bot's channel to read
and to write to (`channel_url`, `channel_direct_url`) and Back; it becomes the
chat's screen, so Back and search edit it in turn. A question that cannot be
edited (deleted): the answer comes as a new message.
Only a chat the survey went to answers (a crafted button is a silent tap); its
first answer gives the week of Relay (`why_survey.grant_week`, once) and the
message says so. The next text there goes to the creator as it is and is kept
for the admin page "Product" (`users.flags` `why_text`, the last one;
`survey_text`), and the chat is back at the menu. Half an hour later, or a
link, a text is a search again, as after Ask.
Lock: python app/jobs/test_why_survey.py
"""
import time

from app.controller.builders import summaryModule
from app.controller.builders.adminModule import send_message_to_creator
from app.controller.general.notify import notify, render_outdated_screen
from app.i18n.messages import get_message
from app.jobs.why_survey import ACTION, ANSWERS, GROUP_FLAG, IDLE_ANSWERS, REWARD_HOURS, SURVEY_FLAG, grant_week
from app.repository.storage import storage
from app.routes.message_tools import go_back_inline_markup
from app.routes.screen_state import state_lost
from app.service import analytics_events
from config import channel_direct_url, channel_url, db_path
from lib.telegram.general.message_master import message_editor, render_messages

ANSWER_FLAG = "why_answer"
TEXT_FLAG = "why_text"  # the text after the answer, for the admin page "Product"
IDLE_SECONDS = 30 * 60
TEXT_LIMIT = 2000


def why_route(data):
    """Route `why`: a reason's button, then the user's text."""
    if data['callback'] is not None:
        return answer(data)
    return comment(data)


def _menu_markup(language_code) -> list:
    return [[{'text': get_message('goBackMenu', language_code), 'callback_data': {'tp': 'menu'}}]]


def _replace_question(data, screen) -> None:
    """The answer takes the place of the tapped question and becomes the chat's screen."""
    message_id = getattr(data['message'], 'message_id', None)
    if message_id is not None:
        try:
            message_editor(data['chat_id'], screen, message_id)
            storage.set_user_message_structures(data['chat_id'], [{'id': message_id, 'type': screen['type']}])
            storage.del_user_resend_flag(data['chat_id'])
            return
        except Exception:
            pass
    render_messages(data['chat_id'], [screen], resending=True)


def answer(data):
    language_code = data['language_code']
    choice = (data.get('united_data') or {}).get('a')
    if choice not in ANSWERS:
        notify(data['callback'], data['message'], '')
        return False
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path)
    try:
        if db.get_user_flag(data['chat_id'], SURVEY_FLAG) in (None, 'control'):  # not asked: a crafted button
            notify(data['callback'], data['message'], '')
            return False
        db.set_user_flag(data['chat_id'], ANSWER_FLAG, choice)
        group = db.get_user_flag(data['chat_id'], GROUP_FLAG)
    finally:
        db.close()
    notify(data['callback'], data['message'], get_message("whyThanksToast", language_code))
    hours = grant_week(data['chat_id'])
    analytics_events.track(data['chat_id'], "survey_answer", {"answer": choice, "reward_hours": hours})
    send_message_to_creator("#survey %s (%s) from %s%s" % (
        choice, language_code, data['chat_id'], ", +%d d of Relay" % (hours // 24) if hours else ""))
    storage.set_user_state_data(data['chat_id'], ACTION, {'a': choice, 'at': time.time()})
    text = get_message("whyWrite" if choice == "own" else "whyMoreOld" if group == "old"
                       else "whyMoreIdle" if choice in IDLE_ANSWERS else "whyMore", language_code)
    if hours:
        text = get_message("whyRewardGiven", language_code).format(days=REWARD_HOURS // 24) + "\n\n" + text
    if choice == "pay":  # paying is inconvenient: often a card that does not work in the country
        text += "\n\n" + get_message("payAbroadHint", language_code)
    text += "\n\n" + get_message("whyChannelLine", language_code)
    _replace_question(data, {
        'type': 'text', 'disable_web_page_preview': True, 'text': text,
        'reply_markup': ([[{'text': get_message("whySearch", language_code), 'callback_data': {'tp': 'search'}}]]
                         if group == "old" else [])
        + [[{'text': get_message("whyChannelRead", language_code), 'url': channel_url},
            {'text': get_message("whyChannel", language_code), 'url': channel_direct_url}]]
        + go_back_inline_markup(language_code),
    })


def comment(data):
    language_code = data['language_code']
    state = storage.get_user_state_data(data['chat_id'], ACTION)
    if state_lost(state, 'a', 'at'):
        return render_outdated_screen(data)
    text = str(getattr(data['message'], 'text', '') or '').strip()
    if time.time() - float(state['at'] or 0) > IDLE_SECONDS or summaryModule.is_link(text):
        return summaryModule.search_instead(data)
    if not text:  # a voice message, a photo
        render_messages(data['chat_id'], [{
            'type': 'text', 'text': get_message("whyTextOnly", language_code),
            'reply_markup': go_back_inline_markup(language_code)}], resending=True)
        return
    from db.sqliteAdapter import SQLighter
    db = SQLighter(db_path)
    try:
        db.set_user_flag(data['chat_id'], TEXT_FLAG, text[:TEXT_LIMIT])
        db.set_user_flag(data['chat_id'], TEXT_FLAG + '_at', int(time.time()))
    finally:
        db.close()
    analytics_events.track(data['chat_id'], "survey_text", {"answer": state['a'], "chars": len(text)})
    send_message_to_creator("#survey %s (%s) from %s:\n%s" % (  # plain text: no parse mode
        state['a'], language_code, data['chat_id'], text[:TEXT_LIMIT]))
    storage.add_user_state(data['chat_id'], 'menu')
    render_messages(data['chat_id'], [{
        'type': 'text', 'text': get_message("whyGot", language_code),
        'reply_markup': _menu_markup(language_code)}], resending=True)
    return False
