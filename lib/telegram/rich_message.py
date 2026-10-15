# -*- coding: utf-8 -*-
"""Bot API sendRichMessage (Bot API 10.x): one message with a player and a long text.

The captions of audio are limited to 1024 characters, a rich message to 32768
(Telegram Premium of the bot's owner does not change that). pyTelegramBotAPI
4.11 has no such method, so it is called through its request helper: same
session, timeouts and error classes as every other call.
"""
import json
import time

MEDIA_ID = 'episode'
# Description share of the 32768 characters, the rest is the header and tags.
DESCRIPTION_CHARS = 20000

_FAILURES_TO_PAUSE = 3
_PAUSE_SECONDS = 600
_failures = 0
_paused_until = 0.0


def available() -> bool:
    """False for a while after several unexplained failures in a row (not a user's block)."""
    return time.time() >= _paused_until


def note_success() -> None:
    global _failures, _paused_until
    _failures = 0
    _paused_until = 0.0


def note_failure() -> None:
    """Rich messages not working for this bot: stop trying for a few minutes, use captions."""
    global _failures, _paused_until
    _failures += 1
    if _failures >= _FAILURES_TO_PAUSE:
        _paused_until = time.time() + _PAUSE_SECONDS
        _failures = 0


def audio_html(html: str) -> str:
    """The player block first, then our text."""
    return '<audio src="tg://audio?id=%s"></audio>' % MEDIA_ID + html


def file_id_of(sent) -> str | None:
    """Bot API file_id of the audio in a sent rich message (the result is raw JSON)."""
    node = sent.get('rich_message') if isinstance(sent, dict) else None
    return _find_audio(node)


def _find_audio(node) -> str | None:
    if isinstance(node, dict):
        audio = node.get('audio')
        if node.get('type') == 'audio' and isinstance(audio, dict) and audio.get('file_id'):
            return audio['file_id']
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = _find_audio(child)
        if found:
            return found
    return None


def send_audio(bot, chat_id, audio, html, duration=None, performer=None, title=None,
               reply_markup=None) -> str | None:
    """Sends the episode and its text as one rich message.

    audio: a file_id, an http(s) URL Telegram fetches, or an open file.
    Raises telebot's ApiTelegramException like any other call. Returns the audio's file_id.
    """
    from telebot import apihelper

    media = {'type': 'audio'}
    files = None
    if hasattr(audio, 'read'):
        media['media'] = 'attach://audio'
        files = {'audio': audio}
    else:
        media['media'] = audio
    if duration:
        media['duration'] = duration
    if performer:
        media['performer'] = performer
    if title:
        media['title'] = title

    params = {
        'chat_id': chat_id,
        'rich_message': json.dumps(
            {'html': audio_html(html), 'media': [{'id': MEDIA_ID, 'media': media}]},
            ensure_ascii=False),
    }
    if reply_markup is not None:
        params['reply_markup'] = reply_markup.to_json()
    sent = apihelper._make_request(bot.token, 'sendRichMessage', method='post', params=params, files=files)
    return file_id_of(sent)
