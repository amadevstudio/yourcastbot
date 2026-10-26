# -*- coding: utf-8 -*-
"""Telegram, faked for botsim: the Bot API the bot talks to, and the Telethon side it listens on.

The bot sends everything through pyTelegramBotAPI, whose every call ends in
telebot.apihelper._make_request: FakeBotApi takes its place, keeps each chat
as Telegram would (message ids, text, buttons, edits, deletes) and answers
with what the Bot API would return. Nothing leaves the process.

The bot listens through Telethon: FakeClient collects the handlers
initialize_routes registers, and dispatch() runs them as Telethon does (in
order, by their filters, until StopPropagation) on events shaped like
Telethon's: a user's message, a button tap, a document.
"""
import itertools
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Sent:
    """A message in a chat as the user would see it."""
    message_id: int
    chat_id: int
    kind: str  # text, audio, photo, document, invoice, rich, ...
    text: str = ''
    buttons: list = field(default_factory=list)  # rows of {'text', 'callback_data' | 'url' | ...}
    reply_to: Optional[int] = None
    from_bot: bool = True
    deleted: bool = False
    extra: dict = field(default_factory=dict)

    def button_texts(self) -> list:
        return [button.get('text', '') for row in self.buttons for button in row]


def _buttons(markup) -> list:
    if not markup:
        return []
    if isinstance(markup, str):
        try:
            markup = json.loads(markup)
        except ValueError:
            return []
    return [list(row) for row in (markup.get('inline_keyboard') or [])]


def _param(params, *names, default=None):
    for name in names:
        if params and params.get(name) not in (None, ''):
            return params[name]
    return default


class FakeBotApi:
    """telebot.apihelper._make_request, answered in memory. `log` lists every call."""

    BOT = {'id': 100000001, 'is_bot': True, 'first_name': 'Yourcast (sim)', 'username': 'yourcast_sim_bot'}
    MEDIA = {'sendAudio': 'audio', 'sendPhoto': 'photo', 'sendDocument': 'document', 'sendVideo': 'video',
             'sendVoice': 'voice', 'sendAnimation': 'animation'}

    def __init__(self):
        self.lock = threading.RLock()
        self.messages: dict = {}  # (chat id, message id) -> Sent
        self.log: list = []  # (method, params) in order
        self.toasts: list = []  # (text, alert) of answered taps
        self._ids = itertools.count(1001)
        self._files = itertools.count(1)
        # parts of photo URLs Telegram will not fetch ("failed to get HTTP URL content", cdn.mave.digital);
        # an uploaded file always goes
        self.refused_urls: set = set()

    # --- the chat ---------------------------------------------------------
    def next_id(self) -> int:
        with self.lock:
            return next(self._ids)

    def add(self, sent: Sent) -> Sent:
        with self.lock:
            self.messages[(sent.chat_id, sent.message_id)] = sent
        return sent

    def chat(self, chat_id) -> list:
        """The chat's messages in order, deleted ones left out."""
        with self.lock:
            return [m for (c, _), m in sorted(self.messages.items(), key=lambda kv: kv[0][1])
                    if c == int(chat_id) and not m.deleted]

    # --- the Bot API --------------------------------------------------------
    def __call__(self, token, method_name, method='get', params=None, files=None):
        params = dict(params or {})
        with self.lock:
            self.log.append((method_name, params, sorted((files or {}).keys())))
            self._refuse_url(method_name, params)
            handler = getattr(self, '_' + method_name, None)
            if handler is not None:
                return handler(params, files or {})
            if method_name in self.MEDIA:
                return self._media(method_name, params, files or {})
            if method_name.startswith('send') and method_name != 'sendChatAction':
                return self._send(method_name[4:].lower(), params, text=str(_param(params, 'text', 'caption',
                                                                                     default='')))
            return True  # setMyCommands, sendChatAction, pinChatMessage, ...

    def _refuse_url(self, method_name, params):
        if method_name == 'sendPhoto':
            url = params.get('photo')
        elif method_name == 'editMessageMedia':
            media = params.get('media')
            url = (json.loads(media) if isinstance(media, str) else (media or {})).get('media')
        else:
            return
        if isinstance(url, str) and url.startswith('http') and any(part in url for part in self.refused_urls):
            from telebot.apihelper import ApiTelegramException
            raise ApiTelegramException(method_name, None, {
                'error_code': 400, 'description': 'Bad Request: failed to get HTTP URL content'})

    def _message_json(self, sent: Sent) -> dict:
        data = {'message_id': sent.message_id, 'date': int(time.time()), 'from': self.BOT,
                'chat': {'id': sent.chat_id, 'type': 'private' if sent.chat_id > 0 else 'channel'}}
        if sent.kind == 'text' or sent.kind == 'rich':
            data['text'] = sent.text
        elif sent.text:
            data['caption'] = sent.text
        if sent.buttons:
            data['reply_markup'] = {'inline_keyboard': sent.buttons}
        if sent.kind == 'rich' and sent.extra.get('source'):  # rich_message.file_id_of reads this
            file_id = sent.extra.setdefault('file_id', 'sim-file-%d' % next(self._files))
            data['rich_message'] = {'blocks': [{'type': 'audio', 'audio': {'file_id': file_id,
                                                                          'file_unique_id': file_id}}]}
        if sent.kind in self.MEDIA.values():
            file_id = sent.extra.setdefault('file_id', 'sim-file-%d' % next(self._files))
            body = {'file_id': file_id, 'file_unique_id': file_id}
            if sent.kind == 'audio':
                body['duration'] = int(_param(sent.extra, 'duration', default=0) or 0)
            data[sent.kind] = [dict(body, width=1, height=1)] if sent.kind == 'photo' else body
        return data

    def _send(self, kind, params, text='', extra=None) -> dict:
        reply_to = _param(params, 'reply_to_message_id')
        sent = self.add(Sent(self.next_id(), int(params['chat_id']), kind, text,
                             _buttons(params.get('reply_markup')), int(reply_to) if reply_to else None,
                             extra=dict(extra or {})))
        return self._message_json(sent)

    def _sendMessage(self, params, files):
        return self._send('text', params, str(params.get('text', '')))

    def _sendRichMessage(self, params, files):
        rich = params.get('rich_message')
        rich = json.loads(rich) if isinstance(rich, str) else (rich or {})
        media = [item.get('media') or {} for item in rich.get('media') or []]
        audio = next((item for item in media if item.get('type') == 'audio'), {})
        source = '<upload audio>' if str(audio.get('media', '')).startswith('attach://') else audio.get('media')
        return self._send('rich', params, str(rich.get('html', '')),
                          {'source': source, 'title': audio.get('title'), 'performer': audio.get('performer'),
                           'duration': audio.get('duration')})

    def _media(self, method, params, files):
        kind = self.MEDIA[method]
        source = params.get(kind) or ('<upload %s>' % kind if kind in files else None)
        return self._send(kind, params, str(params.get('caption', '')),
                          {'source': source, 'title': params.get('title'), 'performer': params.get('performer'),
                           'duration': params.get('duration')})

    def _sendInvoice(self, params, files):
        return self._send('invoice', params, '%s: %s' % (params.get('title'), params.get('description')),
                          {'payload': params.get('payload'), 'prices': params.get('prices'),
                           'currency': params.get('currency')})

    def _createInvoiceLink(self, params, files):
        return 'https://t.me/$sim-invoice'

    def _target(self, params) -> Optional[Sent]:
        key = (int(params.get('chat_id', 0) or 0), int(params.get('message_id', 0) or 0))
        return self.messages.get(key)

    def _not_found(self):
        from telebot.apihelper import ApiTelegramException
        raise ApiTelegramException('sim', None, {'error_code': 400, 'description':
                                                 'Bad Request: message to edit not found'})

    def _editMessageText(self, params, files):
        sent = self._target(params)
        if sent is None or sent.deleted:
            self._not_found()
        if sent.kind not in ('text', 'rich'):  # Telegram: a photo's caption is not its text
            from telebot.apihelper import ApiTelegramException
            raise ApiTelegramException('sim', None, {'error_code': 400, 'description':
                                                     'Bad Request: there is no text in the message to edit'})
        new_buttons = _buttons(params.get('reply_markup'))
        if sent.text == params.get('text') and sent.buttons == new_buttons:
            from telebot.apihelper import ApiTelegramException
            raise ApiTelegramException('sim', None, {'error_code': 400, 'description':
                                                     'Bad Request: message is not modified: specified new message content and reply '
                                                     'markup are exactly the same as a current content and reply '
                                                     'markup of the message'})
        sent.text, sent.buttons = str(params.get('text', '')), new_buttons
        sent.kind = 'text' if sent.kind == 'rich' else sent.kind
        return self._message_json(sent)

    def _editMessageCaption(self, params, files):
        sent = self._target(params)
        if sent is None or sent.deleted:
            self._not_found()
        sent.text, sent.buttons = str(params.get('caption', '')), _buttons(params.get('reply_markup'))
        return self._message_json(sent)

    def _editMessageReplyMarkup(self, params, files):
        sent = self._target(params)
        if sent is None or sent.deleted:
            self._not_found()
        sent.buttons = _buttons(params.get('reply_markup'))
        return self._message_json(sent)

    def _editMessageMedia(self, params, files):
        sent = self._target(params)
        if sent is None or sent.deleted:
            self._not_found()
        media = params.get('media')
        media = json.loads(media) if isinstance(media, str) else (media or {})
        sent.kind = media.get('type', sent.kind)
        sent.text = str(media.get('caption', ''))
        sent.buttons = _buttons(params.get('reply_markup'))
        return self._message_json(sent)

    def _deleteMessage(self, params, files):
        sent = self._target(params)
        if sent is None or sent.deleted:
            from telebot.apihelper import ApiTelegramException
            raise ApiTelegramException('sim', None, {'error_code': 400, 'description':
                                                     'Bad Request: message to delete not found'})
        sent.deleted = True
        return True

    def _answerCallbackQuery(self, params, files):
        self.toasts.append((params.get('text'), bool(params.get('show_alert'))))
        return True

    def _getMe(self, params, files):
        return dict(self.BOT)

    def _getChat(self, params, files):
        chat_id = int(params.get('chat_id', 0) or 0)
        return {'id': chat_id, 'type': 'private' if chat_id > 0 else 'channel', 'title': 'sim chat'}


# --- Telethon, the listening side ------------------------------------------------

class FakeClient:
    """Collects the handlers initialize_routes registers on thonbot."""

    def __init__(self):
        self.handlers = []

    def on(self, builder):
        def register(callback):
            self.handlers.append((builder, callback))
            return callback
        return register

    def add_event_handler(self, callback, builder=None):
        self.handlers.append((builder, callback))

    def disconnect(self):
        pass


class _Sender:
    def __init__(self, lang_code):
        self.lang_code = lang_code


class _Chat:
    def __init__(self, chat_id):
        self.id = chat_id


class FakeMessage:
    """Enough of telethon's Message: what the handlers and get_message read."""

    def __init__(self, message_id, chat_id, text='', lang_code=None, document=None, file=None, data=None,
                 sender_lang=None):
        self.id, self.chat_id, self.text, self.raw_text = message_id, chat_id, text, text
        self.fwd_from, self.document, self.file, self._data = None, document, file, data
        self._sender_lang = sender_lang

    async def get_sender(self):
        return _Sender(self._sender_lang)

    async def download_media(self, file=None):
        return self._data if file is bytes else None


class FakeFile:
    def __init__(self, name, mime_type, size):
        self.name, self.mime_type, self.size = name, mime_type, size


class NewMessageEvent:
    """A user's message in the private chat with the bot."""

    def __init__(self, chat_id, message: FakeMessage, lang_code):
        self.chat_id, self.message, self.text, self.raw_text = chat_id, message, message.text, message.text
        self.chat = _Chat(chat_id)
        self.file = message.file
        self.is_private, self.is_channel, self.is_group = True, False, False
        self.out, self._lang = False, lang_code

    async def get_sender(self):
        return _Sender(self._lang)


class CallbackEvent:
    """A tap on an inline button of one of the bot's messages."""

    query_counter = itertools.count(1)

    def __init__(self, chat_id, data: bytes, message: FakeMessage, lang_code):
        self.chat_id, self.data, self._message, self._lang = chat_id, data, message, lang_code
        self.chat = _Chat(chat_id)
        self.query = object()
        self.is_private, self.is_channel, self.is_group = True, False, False
        self.original_update = type('U', (), {'query_id': next(self.query_counter), 'user_id': chat_id})()

    async def get_sender(self):
        return _Sender(self._lang)

    async def get_message(self):
        return self._message


def _builder_takes(builder, event) -> bool:
    from telethon import events
    if isinstance(event, CallbackEvent):
        if not isinstance(builder, events.CallbackQuery):
            return False
        match = getattr(builder, 'match', None)
        if match is not None and not match(event.data):
            return False
    else:
        if not isinstance(builder, events.NewMessage) or getattr(builder, 'outgoing', False):
            return False
        pattern = getattr(builder, 'pattern', None)
        if pattern is not None and not pattern(event.text or ''):
            return False
    func = getattr(builder, 'func', None)
    return func is None or bool(func(event))


async def dispatch(client: FakeClient, event) -> list:
    """Run the handlers that take `event`, as Telethon does. Their names, in order."""
    from telethon import events
    ran = []
    for builder, callback in list(client.handlers):
        if builder is None or not _builder_takes(builder, event):
            continue
        name = _name(callback)
        try:
            await callback(event)
            ran.append(name)
        except events.StopPropagation:
            ran.append(name + ' (stop)')
            break
        except Exception as e:  # Telethon logs it and goes on with the next handler
            ran.append('%s raised %s: %s' % (name, type(e).__name__, e))
    return ran


def _name(callback) -> str:
    """'opml_file', or 'processor(search)' for a route's partial."""
    func = getattr(callback, 'func', None)
    if func is not None:
        return '%s(%s)' % (getattr(func, '__name__', '?'), ', '.join(str(arg) for arg in callback.args))
    return getattr(callback, '__name__', '?')
