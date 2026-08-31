"""Bot API long-polling receive path.

Telegram MTProto (Telethon) is blocked on some networks while HTTPS Bot API
still works. Incoming updates are converted to the same ptypes used by the
Telethon handlers and dispatched through the existing worker queue.
"""
from typing import Any, Iterator

from agent.bot_telebot import bot
import config
from app.core.controller import empty_state_input_state_corrector
from app.repository.storage import storage
from app.routes.initialize_routes import (
    dispatch_action, dispatch_go_back, dispatch_inline, dispatch_maintenance,
    dispatch_route, get_tp)
from app.routes.ptypes import Callback, Chat, ForwardedFrom, Inline, Message, User
from app.routes.routes import RouteMap
from app.routes.routes_list import AvailableRoutes
from app.service.payment import starsPaymentModule
from lib.python import dict_tools
from lib.tools.logger import logger


def command_name(text: str) -> str | None:
    if not text or not text.startswith('/'):
        return None
    token = text[1:].split()[0]
    if '@' in token:
        token = token.split('@', 1)[0]
    return token or None


def is_channel_chat(chat: Any) -> bool:
    return getattr(chat, 'type', None) == 'channel'


def iter_command_routes(command: str) -> Iterator[AvailableRoutes]:
    for route, params in RouteMap.ROUTES.items():
        if params is None:
            continue
        if 'command' not in params.get('available_from', []):
            continue
        names = list(params.get('commands') or [route])
        if command in names:
            yield route


def message_from_telebot(msg: Any) -> Message:
    lang = ''
    if getattr(msg, 'from_user', None) is not None and msg.from_user.language_code:
        lang = msg.from_user.language_code
    user = User(lang)
    chat = Chat(msg.chat.id)
    fwd = None
    fwd_chat = getattr(msg, 'forward_from_chat', None)
    if fwd_chat is not None and getattr(fwd_chat, 'id', None) is not None:
        fwd = ForwardedFrom(str(fwd_chat.id))
    return Message(msg.message_id, chat, user, msg.text or '', fwd)


def callback_from_telebot(call: Any) -> tuple[Callback, Message | None]:
    lang = ''
    if getattr(call, 'from_user', None) is not None and call.from_user.language_code:
        lang = call.from_user.language_code
    user = User(lang)
    if call.message is not None:
        chat = Chat(call.message.chat.id)
        message = message_from_telebot(call.message)
    else:
        chat = Chat(call.from_user.id)
        message = None
    data = call.data if call.data is not None else ''
    return Callback(call.id, data, user, chat, message), message


def inline_from_telebot(query: Any) -> Inline:
    offset = 0
    try:
        offset = int(query.offset or 0)
    except Exception:
        offset = 0
    return Inline(query.id, query.from_user.id, query.query or '', offset)


def _action_matches(route: str, action: str, chat_id: int, tp: str) -> bool:
    if tp != action:
        return False
    return (
        storage.get_user_curr_state(chat_id) == route
        or dict_tools.deep_get(
            RouteMap.ROUTES, route, 'actions', action, 'state_independent') is True
    )


def on_botapi_message(message: Any) -> None:
    if is_channel_chat(message.chat):
        return

    empty_state_input_state_corrector(message.chat.id)
    pmsg = message_from_telebot(message)
    text = pmsg.text or ''
    cmd = command_name(text)
    if cmd is not None:
        for route in iter_command_routes(cmd):
            dispatch_route(route, None, pmsg)
        return

    for route, params in RouteMap.ROUTES.items():
        if params is None:
            continue
        if 'message' not in params.get('available_from', []):
            continue
        states = params.get('states_for_input', [route])
        if storage.get_user_curr_state(message.chat.id) in states:
            dispatch_route(route, None, pmsg)


def on_botapi_callback(call: Any) -> None:
    if call.message is not None and is_channel_chat(call.message.chat):
        return

    callback, message = callback_from_telebot(call)
    tp = get_tp(callback.data)
    if tp == 'bck':
        dispatch_go_back(callback, message)
        return

    for route, params in RouteMap.ROUTES.items():
        if params is None:
            continue
        if 'call' in params.get('available_from', []) and tp == route:
            dispatch_route(route, callback, message)
        actions = params.get('actions')
        if actions:
            for action in actions:
                if _action_matches(route, action, callback.chat.id, tp):
                    dispatch_action(
                        route, action, callback, message)


def _on_precheckout(query: Any) -> None:
    try:
        success, error = starsPaymentModule.validate_precheckout_payload(
            query.invoice_payload, query.from_user.id, query.currency, query.total_amount)
    except Exception as e:
        logger.err(e)
        success, error = False, "Invalid payment payload"
    try:
        bot.answer_pre_checkout_query(
            query.id, ok=success, error_message=error if not success else None)
    except Exception as e:
        logger.err(e)


def _on_successful_payment(message: Any) -> None:
    payment = message.successful_payment
    if payment is None:
        return
    starsPaymentModule.process_successful_payment(
        message.chat.id,
        payment.currency,
        payment.total_amount,
        payment.invoice_payload,
        payment.telegram_payment_charge_id,
        payment.provider_payment_charge_id)


def initialize_botapi_routes() -> None:
    if config.maintenance:
        @bot.message_handler(func=lambda _m: True)
        def maintenance_messages(message: Any) -> None:
            dispatch_maintenance(None, message_from_telebot(message))

        @bot.callback_query_handler(func=lambda _c: True)
        def maintenance_callbacks(call: Any) -> None:
            callback, message = callback_from_telebot(call)
            dispatch_maintenance(callback, message)
        return

    @bot.pre_checkout_query_handler(func=lambda _q: True)
    def precheckout(query: Any) -> None:
        _on_precheckout(query)

    @bot.message_handler(content_types=['successful_payment'])
    def successful_payment(message: Any) -> None:
        _on_successful_payment(message)

    @bot.inline_handler(func=lambda _q: True)
    def inline_queries(query: Any) -> None:
        dispatch_inline(inline_from_telebot(query))

    @bot.callback_query_handler(func=lambda _c: True)
    def callbacks(call: Any) -> None:
        on_botapi_callback(call)

    @bot.message_handler(content_types=['text'])
    def texts(message: Any) -> None:
        on_botapi_message(message)


def run_botapi_polling() -> None:
    bot.remove_webhook()
    logger.log("Receiving via Bot API long polling")
    bot.infinity_polling(
        skip_pending=True,
        timeout=20,
        long_polling_timeout=20,
        allowed_updates=[
            'message', 'callback_query', 'inline_query', 'pre_checkout_query',
        ],
        restart_on_change=False)
