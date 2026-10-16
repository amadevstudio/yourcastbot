# -*- coding: utf-8 -*-
"""Rich messages: the request, the text, the pause after repeated failures.

A fake request helper stands in for Telegram; nothing touches the network.
Run from the repo root: python lib/telegram/test_rich_message.py
"""
import io
import json
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

calls = []
reply = {}


def _make_request(token, method_name, method='get', params=None, files=None):
    calls.append({'token': token, 'method': method_name, 'http': method, 'params': params, 'files': files})
    return reply


fake_apihelper = types.ModuleType('telebot.apihelper')
fake_apihelper._make_request = _make_request
fake_telebot = types.ModuleType('telebot')
fake_telebot.apihelper = fake_apihelper
sys.modules['telebot'] = fake_telebot
sys.modules['telebot.apihelper'] = fake_apihelper

from app.service.record import caption  # noqa: E402
from lib.telegram import rich_message  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class Bot:
    token = 'TOKEN'


class Markup:
    def to_json(self):
        return '{"inline_keyboard": []}'


SENT = {'message_id': 5, 'rich_message': {'blocks': [
    {'type': 'paragraph', 'text': 'x'},
    {'type': 'audio', 'audio': {'file_id': 'AUDIO_FID', 'duration': 60}},
]}}


def _fields(**kwargs):
    fields = dict(
        lang_code='en', channel_link='https://example.com/show?a=1&b=2', ch_name='R&D Show',
        title='A < B', channel_id=7, pub_date='2026-10-15T10:00:00', descr='', service_name='rss',
        service_id='https://example.com/rss')
    fields.update(kwargs)
    return fields


def main():
    # The request
    reply.clear()
    reply.update(SENT)
    file_id = rich_message.send_audio(
        Bot(), 123, 'https://cdn.example/ep.mp3', '<p>Hi</p>', duration=60,
        performer='Show', title='Ep', reply_markup=Markup())
    call = calls[-1]
    body = json.loads(call['params']['rich_message'])
    _assert(file_id == 'AUDIO_FID', "the file_id comes out of the audio block")
    _assert(call['method'] == 'sendRichMessage' and call['http'] == 'post' and call['token'] == 'TOKEN',
            "sendRichMessage, POST, the bot's token")
    _assert(body['html'].startswith('<audio src="tg://audio?id=episode"></audio>') and body['html'].endswith('<p>Hi</p>'),
            "the player first, then the text")
    _assert(body['media'] == [{'id': 'episode', 'media': {
        'type': 'audio', 'media': 'https://cdn.example/ep.mp3', 'duration': 60,
        'performer': 'Show', 'title': 'Ep'}}], "the audio is declared in media")
    _assert(call['files'] is None and call['params']['reply_markup'] == '{"inline_keyboard": []}',
            "a URL needs no upload; the keyboard rides along")

    rich_message.send_audio(Bot(), 123, io.BytesIO(b'x'), '<p>Hi</p>')
    call = calls[-1]
    body = json.loads(call['params']['rich_message'])
    _assert(body['media'][0]['media']['media'] == 'attach://audio' and list(call['files']) == ['audio'],
            "an open file is uploaded as attach://audio")
    _assert('reply_markup' not in call['params'], "no keyboard, no field")

    reply.clear()
    _assert(rich_message.send_audio(Bot(), 1, 'FILE_ID', '<p>x</p>') is None,
            "an answer without an audio block gives no file_id")

    # The pause: three failures in a row stop rich messages for a while, a success resets
    rich_message.note_success()
    _assert(rich_message.available(), "available at start")
    rich_message.note_failure()
    rich_message.note_failure()
    rich_message.note_success()
    rich_message.note_failure()
    rich_message.note_failure()
    _assert(rich_message.available(), "failures that are not in a row do not pause")
    rich_message.note_failure()
    _assert(not rich_message.available(), "three in a row pause rich messages")
    rich_message._paused_until = 0.0
    _assert(rich_message.available(), "the pause ends")

    # The text
    text = caption.record_rich_html(**_fields(descr='First para.\n\nSecond <b>para</b> & more\nnext line'))
    _assert('\n' not in text, "no raw newline in the HTML")
    _assert('R&amp;D Show' in text and 'A &lt; B' in text, "show and title are escaped")
    _assert('href="https://example.com/show?a=1&amp;b=2"' in text, "the show link stays a link")
    _assert('<p>First para.</p><p>Second para &amp; more<br>next line</p>' in text,
            "description: paragraphs and line breaks, markup of the feed gone")
    _assert('#id7' in text, "the podcast id tag")
    _assert('href="https://t.me/' in text and 'href="t.me/' not in text, "the bot link is absolute")

    text = caption.record_rich_html(**_fields(descr=(
        '<p>Members: <a href="https://example.com/a?x=1&amp;y=2">Click here</a>.</p>'
        '<p><a href=\'https://example.com/b\'><em>Open</em> lesson_1</a> and '
        '<a href="javascript:alert(1)">bad</a> <a href="https://example.com/c"></a></p>')))
    _assert('<a href="https://example.com/a?x=1&amp;y=2">Click here</a>.' in text,
            "description keeps its links, with the visible text")
    _assert('<a href="https://example.com/b">Open lesson 1</a> and bad</p>' in text,
            "single quotes and inner tags in a link")
    _assert('javascript' not in text and 'href="https://example.com/c"' not in text,
            "other schemes and empty links are text only")

    many = ''.join('<p>Item %d <a href="https://example.com/%s">link</a>.</p>' % (i, 'x' * 200)
                   for i in range(400))
    text = caption.record_rich_html(**_fields(descr=many))
    _assert(len(text) < 32768 and 'Item 399' in text,
            "hundreds of links: the text fits a rich message (links dropped, text kept)")

    long_description = 'Sentence number one. ' * 2000  # 42000 characters
    text = caption.record_rich_html(**_fields(descr=long_description))
    _assert(len(text) < 32768, "even a huge description fits a rich message")
    _assert(text.count('Sentence number one.') > 900, "long description is kept, not cut to a caption")

    description = '<p>Intro.</p>' + '<p>' + ('Line of notes. ' * 400) + '</p>'
    quote = caption.record_description_message(description)
    _assert(quote.startswith('<blockquote expandable>') and quote.endswith('</blockquote>')
            and len(quote) < 4096, "separate message: a collapsible quote under 4096")
    _assert(caption.record_description_message('') == '' and caption.record_description_message(None) == '',
            "no description, no message")
    print("all rich message checks passed")


if __name__ == "__main__":
    main()
