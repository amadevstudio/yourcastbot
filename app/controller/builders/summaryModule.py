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
goes and the episode's podcast page comes as a new message at the bottom
(Back on it: the menu); the menu when the podcast is not known or gone (a
plain `menu` tap would redraw the old question screen up the chat). A text after
ASK_IDLE_SECONDS without a question is a search, as it was before Ask.

"Transcript" (summary.TRANSCRIPT_ACTION), under the audio next to Summary and
under a summary next to Ask, sends the episode's transcript as a .txt file
replying to the audio. One made before (for a summary or a transcript) is
free to anyone, as a summary is; so is the one the feed publishes, read at
the tap. Otherwise only the transcript is queued (ai.TRANSCRIPT: no model
call), charged the episode's length like a summary, through the same quota
and offers. A chat charged for an episode's audio once is not charged again
for it (ai.audio_paid): a summary after its transcript, or the reverse.
"""
import io
import json
import re
import time
from types import SimpleNamespace

from app.controller.general.notify import notify, render_outdated_screen
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.routes.screen_state import state_lost
from app.service import analytics_events
from app.service.ai import paid_models, quota as ai_quota, summary, transcript
# the over-quota offer is shared with automatic summaries (app/service/ai/auto.py)
from app.service.ai.offer import offer_message
from config import db_path
from db import ai, usage
from db.sqliteAdapter import SQLighter
from lib.markup import telegram_html
from lib.telegram.general.errors import bot_blocked_reaction, get_timeout_from_error_bot, log_caught
from lib.telegram.general.message_master import message_deleter, message_editor, outer_sender, render_messages
from lib.telegram.telebot.types import ApiException, ApiTelegramException
from lib.tools.logger import logger


def summary_message(episode, text, ref=None, reply_to=None, language_code=None) -> dict:
    """The summary; with `ref` its Ask button, with `reply_to` a reply to the audio message."""
    header = telegram_html.escape(telegram_html.plain_text(episode['show'])) + ' – ' \
        + telegram_html.escape(telegram_html.plain_text(episode['title']))
    message = {'type': 'text', 'text': '📝 <b>%s</b>\n\n%s' % (header, telegram_html.escape(text)),
               'disable_web_page_preview': True}
    if episode.get('owner_chat') is not None:
        message['text'] = '📝 <b>%s</b>\n\n%s' % (get_message('voiceBatchTitle' if episode['ref'].startswith('b_') else 'voiceTitle', language_code), telegram_html.escape(text))
    if ref:
        message['reply_markup'] = [[{'text': get_message('askButton', language_code or 'en'),
                                     'callback_data': summary.ask_button_data(ref, reply_to)},
                                    {'text': get_message('transcriptButton', language_code or 'en'),
                                     'callback_data': summary.transcript_button_data(ref, reply_to)}]]
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
    episode = ai.accessible_episode(ref, data['chat_id']) if ref else None
    if episode is None:
        notify(data['callback'], data['message'], get_message('screenOutdated', language_code))
        return

    if episode.get('owner_chat') is not None:
        from app.service.ai import voice
        lang = voice.language(data['chat_id'], language_code)
    else:
        lang = _summary_language(data['chat_id'], language_code)
    audio = getattr(data['message'], 'message_id', None)  # the button is on the episode's audio
    cached = ai.summary(ref, lang)
    if cached is not None:
        notify(data['callback'], data['message'], '')
        # a reply to the audio, not a screen: the menu the user had stays
        outer_sender(data['chat_id'], [summary_message(episode, cached['text'], ref, audio, language_code)])
        usage.record_ai(data['chat_id'], ref, 0.0)
        return

    quota = ai_quota.check(data['chat_id'], _needed(data['chat_id'], episode))
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


def _needed(chat_id, episode) -> int:
    """The seconds a new summary or transcript takes from the quota: none when this chat's own
    request for the episode was charged its audio already (the transcript is paid for)."""
    if episode.get('owner_chat') is not None and ai.transcript(episode['ref']) is not None:
        return 0
    return 0 if ai.audio_paid(chat_id, episode['ref']) else ai_quota.seconds_needed(episode)


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


_MARK = re.compile(r' (?=\[\d+:\d\d(?::\d\d)?\] )')
_SENTENCE_END = re.compile(r'(?<=[.!?…。؟])\s+')
PARAGRAPH_CHARS = 700


def _paragraphs(text) -> str:
    """A transcript without time marks (one line of up to 45k characters before 2026-10-22, or the
    feed's plain text): paragraphs of about PARAGRAPH_CHARS, broken after a sentence."""
    paragraphs, current = [], ''
    for sentence in _SENTENCE_END.split(text):
        current = (current + ' ' + sentence).strip()
        if len(current) >= PARAGRAPH_CHARS:
            paragraphs.append(current)
            current = ''
    return '\n\n'.join(paragraphs + ([current] if current else []))


def transcript_file(episode, text) -> tuple[str, bytes]:
    """(file name, UTF-8 text) of an episode's transcript: the show, the title and the audio's link,
    then the text with a line for each time mark (paragraphs when it has none)."""
    title = telegram_html.plain_text(episode['title']).strip()
    text = str(text).strip()
    text = _MARK.sub('\n', text) if _MARK.search(text) else _paragraphs(text)
    lines = [telegram_html.plain_text(episode['show']).strip(), title, episode['link'], '', text, '']
    # what a file name cannot hold on some system goes; Telegram keeps any other letter
    name = ' '.join(re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', title).split())[:60].strip(' .') or 'transcript'
    return name + '.txt', '\n'.join(lines).encode('utf-8')


def send_transcript_file(chat_id, episode, text, source, language_code, reply_to=None, over_quota=False) -> bool:
    """The transcript as a .txt file replying to the audio; True if Telegram took it. One we made says it
    may have mistakes; under Whisper's, a chat without a paid plan reads what a paid one's would have."""
    name, body = transcript_file(episode, text)
    caption = '📄 <b>%s – %s</b>' % (telegram_html.escape(telegram_html.plain_text(episode['show'])[:200]),
                                     telegram_html.escape(telegram_html.plain_text(episode['title'])[:300]))
    if episode.get('owner_chat') is not None:
        caption = '📄 <b>%s</b>' % get_message('voiceBatchTitle' if episode['ref'].startswith('b_') else 'voiceTitle', language_code)
    if source in (transcript.WHISPER, transcript.SPEAKERS, 'voice_batch'):
        caption += '\n' + get_message('transcriptMachine', language_code)
    note = paid_models.transcript_note(chat_id, source, language_code, over_quota=over_quota)
    if note:
        caption += '\n\n' + note
    return send_document(chat_id, name, body, caption, reply_to)


# the feed's transcript is read at the tap, in the incoming worker: it must not hang there
FEED_TRANSCRIPT_TIMEOUT = (5, 20)


def _feed_transcript(episode):
    """The transcript the episode's feed publishes (the feed's last copy, feed_cache), cached for
    everyone; None when it has none or it cannot be read now."""
    if episode.get('owner_chat') is not None:
        return None
    from lib.requests import requesterModule
    try:
        found = transcript.from_episode_feed(requesterModule.Requester(attempts=0, total_attempts=0), episode,
                                             cached=True, timeout=FEED_TRANSCRIPT_TIMEOUT)
    except Exception as e:
        logger.warn('transcript/feed:', episode['ref'], type(e).__name__, e)
        return None
    if found is not None:
        ai.save_transcript(episode['ref'], found.text, found.source, found.cost_usd, found.seconds)
    return found


def request_transcript(data):
    """Transcript, under the audio or under a summary: the file at once when it is made or the feed
    has it (free); else the transcript alone is queued for the jobs process (ai_watcher), charged
    the episode's length like a summary; without the hours, the same offer as a summary."""
    language_code = data['language_code']
    if not summary.enabled():
        notify(data['callback'], data['message'], get_message('summaryUnavailable', language_code))
        return
    try:
        call = json.loads(data['callback'].data)
        ref, audio = str(call['r']), int(call.get('m') or 0) or None
    except (AttributeError, TypeError, ValueError, KeyError):
        ref, audio = None, None
    episode = ai.accessible_episode(ref, data['chat_id']) if ref else None
    if episode is None:
        notify(data['callback'], data['message'], get_message('screenOutdated', language_code))
        return
    # under the audio the button is on the audio itself; under a summary it names it ('m')
    audio = audio or getattr(data['message'], 'message_id', None)
    notify(data['callback'], data['message'], '')
    found = ai.transcript(ref)
    if found is None:
        found = _feed_transcript(episode)
        found = dict(found._asdict()) if found is not None else None
    # a paying chat with the better models gets Whisper's transcript made again, with speakers,
    # if its hours and its plan's budget cover it
    wants = (episode.get('owner_chat') is None and found is not None
             and found['source'] == transcript.WHISPER and paid_models.speakers(data['chat_id']))
    upgrade = wants and paid_models.speakers_fit(data['chat_id'], ai_quota.seconds_needed(episode))
    quota = ai_quota.check(data['chat_id'], _needed(data['chat_id'], episode)) if found is None or upgrade else None
    if found is not None and not (upgrade and quota.allowed):  # over its hours a payer gets Whisper's
        if send_transcript_file(data['chat_id'], episode, found['text'], found['source'], language_code, audio,
                                over_quota=wants):
            usage.record_transcript(data['chat_id'], ref, 0.0)
            analytics_events.track(data['chat_id'], 'transcript_ready', {'source': found['source'], 'made': False})
        return

    if not quota.allowed:
        render_messages(data['chat_id'], [offer_message(language_code, quota, transcript=True)])
        return
    # the worker edits it as it goes (downloading, transcribing part n of m) and deletes it with the file
    status = status_line(data['chat_id'], get_message('transcriptStatusQueued', language_code), audio)
    _, new = ai.enqueue(data['chat_id'], ref, '', quota.needed, reply_to=audio, status_message=status,
                        kind=ai.TRANSCRIPT)
    if not new and status:  # a second tap: the first one's line is already there
        try:
            message_deleter(data['chat_id'], status)
        except Exception:
            pass


def send_document(chat_id, name, body, caption, reply_to=None) -> bool:
    """A file to a chat; True if Telegram took it. What it does not take (blocked, a flood) is a WARN,
    as in outer_sender."""
    from agent.bot_telebot import bot
    try:
        bot.send_document(chat_id, io.BytesIO(body), visible_file_name=name, caption=caption, parse_mode='HTML',
                          reply_to_message_id=reply_to, allow_sending_without_reply=True if reply_to else None)
        return True
    except (ApiTelegramException, ApiException) as e:
        if get_timeout_from_error_bot(e) or bot_blocked_reaction(e, chat_id):
            logger.warn('transcript not sent:', e)
            return False
        log_caught(logger, error=e)
    except Exception as e:
        log_caught(logger, error=e)
    return False


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
    if questions.budget:
        from app.service.ai.offer import budget_message
        return budget_message(language_code, questions.level)
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
    episode = ai.accessible_episode(ref, data['chat_id']) if ref else None
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
    episode = ai.accessible_episode(state['ref'], data['chat_id'])
    found = ai.transcript(state['ref']) if episode else None
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
        text, cost = summary.answer(found['text'], episode['title'], episode['show'], question,
                                    model=paid_models.summary_model(data['chat_id']),
                                    **({'voice': True} if episode.get('owner_chat') is not None else {}))
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
    """ "Done": the questions end here; the button goes, the episode's podcast page (else the menu)
    comes at the bottom of the chat."""
    from app.controller.builders.menuModule import construct_menu_message
    from agent.bot_telebot import bot
    notify(data['callback'], data['message'], '')
    try:
        bot.edit_message_reply_markup(data['chat_id'], data['callback'].message.message_id, reply_markup=None)
    except Exception:
        pass  # an old message: the page still comes
    channel_id = _asked_channel(data['chat_id'])
    storage.clear_user_storage(data['chat_id'])
    storage.add_user_state(data['chat_id'], 'menu')
    if channel_id is not None:
        from app.controller.builders.podcastModule import channel_query
        # opened as by a message (as a /start link opens it): a new message, the question stays above
        channel_query(dict(data, callback=None, route_name='podcast', united_data={},
                           message=SimpleNamespace(text=json.dumps({'id': channel_id}))))
        storage.add_user_state(data['chat_id'], 'podcast')
        return
    render_messages(data['chat_id'], construct_menu_message(data['language_code'], data['chat_id']),
                    resending=True)


def _asked_channel(chat_id) -> int | None:
    """The channel of the episode the questions were about, while it is in the database."""
    state = storage.get_user_state_data(chat_id, 'ask')
    episode = ai.accessible_episode(state['ref'], chat_id) if state and state.get('ref') else None
    return episode['channel_found'] if episode else None


def is_link(text) -> bool:
    return text.lower().startswith(('http://', 'https://')) and ' ' not in text


def search_instead(data):
    """A text long after the last question: the user is searching again, as before Ask."""
    from app.controller.builders import searchModule
    storage.add_user_state(data['chat_id'], 'search')
    data['route_name'], data['united_data'] = 'search', {}
    searchModule.search(data)
    return False
