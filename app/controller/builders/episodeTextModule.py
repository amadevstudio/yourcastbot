# -*- coding: utf-8 -*-
""""Show notes" under a brief episode (text_format.BRIEF): the feed's description on a tap.

The brief format sends the audio with its header only; the description the
sender kept with the episode (db/ai.py, by the button's ref) comes as a
collapsible quote replying to the audio, as the separate format sends it.
State independent: the button stays usable on any old episode in the chat.
"""
import json

from app.controller.general.notify import notify
from app.i18n.messages import get_message
from app.service.record.caption import record_description_message
from db import ai
from lib.telegram.general.message_master import outer_sender


def show_description(data):
    language_code = data['language_code']
    try:
        ref = str(json.loads(data['callback'].data)['r'])
    except (AttributeError, TypeError, ValueError, KeyError):
        ref = None
    episode = ai.episode(ref) if ref else None
    if episode is None:
        notify(data['callback'], data['message'], get_message('screenOutdated', language_code))
        return
    text = record_description_message(episode.get('descr') or '')
    if not text:
        notify(data['callback'], data['message'], get_message('descriptionMissing', language_code))
        return
    notify(data['callback'], data['message'], '')
    message = {'type': 'text', 'text': text, 'disable_web_page_preview': True}
    audio = getattr(data['message'], 'message_id', None)  # the button is on the episode's audio
    if audio:
        message['reply_to'] = int(audio)
    outer_sender(data['chat_id'], [message])
