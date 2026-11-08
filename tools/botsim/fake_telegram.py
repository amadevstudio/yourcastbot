# -*- coding: utf-8 -*-
"""Telegram, faked for botsim: the Bot API the bot talks to, and the Telethon side it listens on.

The Bot API is tgsim's (github.com/amadevstudio/tgsim): a Telegram kept in memory that answers as Telegram does,
refusals included (HTML it cannot parse, a text over 4096 characters, an edit that changes nothing). The bot sends
everything through pyTelegramBotAPI, whose every call ends in telebot.apihelper._make_request: BotApi takes its
place and hands the call to tgsim.

The bot listens through Telethon: FakeClient collects the handlers initialize_routes registers, and dispatch()
runs them as Telethon does (in order, by their filters, until StopPropagation) on events shaped like Telethon's:
a user's message, a button tap, a document.
"""
import itertools
import os

import tgsim


def _upload(name, value) -> tuple:
    """telebot's file field (an open file, bytes, (filename, file)) as tgsim takes it: (filename, bytes, mime)."""
    filename, data, mime = None, value, None
    if isinstance(value, tuple):
        filename, data = value[0], value[1]
        mime = value[2] if len(value) > 2 else None
    elif hasattr(value, 'name'):
        filename = value.name
    if hasattr(data, 'read'):
        data = data.read()
    if isinstance(data, str):
        data = data.encode('utf-8')
    return os.path.basename(str(filename)) if filename else name, bytes(data or b''), mime


class BotApi:
    """telebot.apihelper._make_request, answered by tgsim. A refusal is telebot's ApiTelegramException."""

    def __init__(self, tg: tgsim.Telegram):
        self.tg = tg

    def __call__(self, token, method_name, method='get', params=None, files=None):
        uploads = {name: _upload(name, value) for name, value in (files or {}).items()}
        try:
            return self.tg.call(method_name, params, uploads)
        except tgsim.ApiError as e:
            from telebot.apihelper import ApiTelegramException
            raise ApiTelegramException(method_name, None, e.json())

    @property
    def messages(self) -> dict:
        """(chat id, message id) -> tgsim.Message"""
        return self.tg.messages

    @property
    def log(self) -> list:
        """(method, params, upload names) of every call, in order."""
        return [(call.method, call.params, call.files) for call in self.tg.calls]

    def refuse_url(self, part: str):
        """Telegram will not fetch a picture whose URL has `part` ("failed to get HTTP URL content"); an upload
        always goes."""
        def names(params):
            media = params.get('media') if isinstance(params.get('media'), dict) else {}
            url = params.get('photo') or media.get('media')
            return isinstance(url, str) and url.startswith('http') and part in url
        error = tgsim.bad_request('failed to get HTTP URL content')
        self.tg.fail('sendPhoto', error, names, times=None)
        self.tg.fail('editMessageMedia', error, names, times=None)


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
        self.voice = None

    async def get_sender(self):
        return _Sender(self._sender_lang)

    async def download_media(self, file=None, progress_callback=None):
        if file is bytes:
            return self._data
        if hasattr(file, 'write'):
            file.write(self._data)
            if progress_callback:
                progress_callback(len(self._data), len(self._data))
            return file
        return None


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

    def __init__(self, chat_id, data: bytes, message: FakeMessage, lang_code, query_id=None, answer=None):
        self.chat_id, self.data, self._message, self._lang = chat_id, data, message, lang_code
        self._answer = answer
        self.chat = _Chat(chat_id)
        self.query = object()
        self.is_private, self.is_channel, self.is_group = True, False, False
        query_id = next(self.query_counter) if query_id is None else query_id
        self.original_update = type('U', (), {'query_id': query_id, 'user_id': chat_id})()

    async def get_sender(self):
        return _Sender(self._lang)

    async def get_message(self):
        return self._message

    async def answer(self, message=None, cache_time=0, *, url=None, alert=False):
        """Telethon's answer to the tap (MTProto), told to tgsim as the Bot API's answerCallbackQuery."""
        if self._answer is not None:
            self._answer(message, alert)


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
