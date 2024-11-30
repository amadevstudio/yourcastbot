import json
import threading
from functools import partial
from typing import Callable, Tuple

import telethon.events
from telethon import events

import config
from agent.bot_telethon import thonbot
from app.controller.builders import welcomeModule, searchModule
from app.core.balancers import telebotAnswerer
from app.core.balancers.telebotAnswerer import TelebotBalancer
from app.core.controller import construct_params, empty_state_input_state_corrector
from app.core.navigation import goBackModule
from app.jobs.podcastsUpdater import logger
from app.repository.storage import storage
from app.routes import router_tools
from app.routes.routes_list import AvailableActions
from app.routes.ptypes import Chat, User, ForwardedFrom, Message, Callback, HandleInThreadParams, Inline
from app.routes.routes import AvailableRoutes, RouteMap
from lib.python import dict_tools

# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# HELPERS
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!


def get_tp(data):
    try:
        return json.loads(data)['tp']
    except Exception as e:
        logger.err(e, flush=True)
        return ""


async def get_call_and_message(event: telethon.events.NewMessage.Event | telethon.events.CallbackQuery.Event) \
        -> Tuple[Callback | None, Message | None]:
    if hasattr(event, 'data'):
        callback = await get_callback(event)
        return callback, callback.message
    else:
        message = await get_message(event)
        return None, message


async def get_message(event: telethon.events.NewMessage.Event) -> Message | None:
    sender: telethon.types.User = await event.get_sender()
    user: User = User(sender.lang_code)

    chat: Chat = Chat(event.chat_id)

    message: Message = Message(event.message.id, chat, user, event.text, event.message.fwd_from)

    # если переслано, получает id, откуда
    if event.message.fwd_from:
        if hasattr(event.message.fwd_from.from_id, "channel_id"):
            # В наборе данных указано без -100
            message.fwd_from = ForwardedFrom(f"-100{event.message.fwd_from.from_id.channel_id}")

    return message


async def get_callback(event: telethon.events.CallbackQuery.Event) -> Callback:
    sender: telethon.types.User = await event.get_sender()
    user: User = User(sender.lang_code)
    chat: Chat = Chat(event.chat_id)

    callback: Callback = Callback(event.original_update.query_id, event.data, user, chat)

    event_message: telethon.events.NewMessage.Event.Message | None = await event.get_message()
    if event_message:
        event_message_sender = await event_message.get_sender()
        callback.message = Message(
            event_message.id, Chat(event_message.chat_id), User(event_message_sender.lang_code),
            event_message.text, event_message.fwd_from)

    return callback


async def get_inline(event: telethon.events.InlineQuery.Event) -> Inline:
    return Inline(
        event.original_update.query_id, event.original_update.user_id,
        event.original_update.query, event.original_update.offset)


# TODO: remove
# Проверка на соответствие состояния
def test_message(event, state):
    pass


def test_call(event, state):
    if not (hasattr(event, 'query')):
        return False

    try:
        chat_id = event.chat_id
        return storage.get_user_curr_state(chat_id) == state

    except Exception:
        return False


t_answer_sender: TelebotBalancer | None = None


def initialize_routes(t_answer_sender_outer: TelebotBalancer, answer_sender_queue, threads_to_watch):
    global t_answer_sender
    t_answer_sender = t_answer_sender_outer

    def handle_event_in_thread(params: HandleInThreadParams):
        global t_answer_sender
        if isinstance(t_answer_sender, threading.Thread):
            if not t_answer_sender.is_alive():
                t_answer_sender = telebotAnswerer.TelebotBalancer(
                    answer_sender_queue, threads_to_watch)
            t_answer_sender.main_queue.put(params)

    # Outer middlewares
    # Catch all message when under maintenance
    if config.maintenance:
        async def maintenance_catcher(event: telethon.events.NewMessage.Event | telethon.events.CallbackQuery.Event):
            callback, message = await get_call_and_message(event)
            method_params = construct_params(callback, message, None)
            handle_event_in_thread(
                {'action': welcomeModule.maintenance, 'data': method_params})

        thonbot.add_event_handler(maintenance_catcher, events.NewMessage(incoming=True))
        thonbot.add_event_handler(maintenance_catcher, events.CallbackQuery())
        return

    # If status is 'empty' and previous waits for text, goback to previously and process
    async def process_empty_state_input(event: telethon.events.NewMessage.Event):
        empty_state_input_state_corrector(event)
    thonbot.add_event_handler(process_empty_state_input, events.NewMessage(incoming=True))

    # /Outer middlewares

    # -----
    # MAIN PROCESSOR

    async def processor(route_name: AvailableRoutes,
                        event: telethon.events.NewMessage.Event | telethon.events.CallbackQuery.Event):

        # ---
        # Inner middlewares
        # Access filter, bot is blocked for channels (group is channel type)
        if event.is_channel and not event.is_group:
            return
        # ---

        call, message = await get_call_and_message(event)

        menu_route: AvailableRoutes = 'menu'
        method_params = construct_params(call, message, route_name)

        # Validate access
        validator = dict_tools.deep_get(RouteMap.ROUTES, route_name, 'validator')
        if validator is not None:
            valid = validator(method_params)
            if not valid:
                return

        if call is None and message is not None:
            # Clear state on commands
            if router_tools.is_command(message.text):
                storage.clear_user_storage(event.chat.id)
                storage.add_user_state(method_params['chat_id'], menu_route)
            # Set resend on message
            storage.set_user_resend_flag(message.chat.id)

        method: Callable = dict_tools.deep_get(RouteMap.ROUTES, route_name, 'method')

        # succeed = await method(method_params)
        handle_event_in_thread(
            {'action': method, 'data': method_params}
        )
        # if succeed is not False:  # returns None by default
        #     storage.add_user_state(method_params['chat_id'], route_name)

    async def action_processor(
            route_name: AvailableRoutes, action_name: AvailableActions, call: telethon.events.CallbackQuery.Event):
        call, message = await get_call_and_message(call)
        method_params = construct_params(call, message, route_name, action_name)
        method: Callable = dict_tools.deep_get(RouteMap.ROUTES, route_name, 'actions', action_name, 'method')
        handle_event_in_thread({'action': method, 'data': method_params})

    # Goback module
    @thonbot.on(events.CallbackQuery(func=lambda call: get_tp(call.data) == 'bck'))
    async def go_back(event: events.CallbackQuery.Event):
        callback, message = await get_call_and_message(event)
        method_params = construct_params(callback, message, None)
        handle_event_in_thread(
            {'action': goBackModule.go_back, 'data': method_params})

    def commands_list_validator(commands: list[str], incoming_command: str):
        return incoming_command[1:] in commands

    def message_validator(states: list[str], message: telethon.events.NewMessage.Event):
        if message.text != '' and message.text[0] == '/':
            return False

        return storage.get_user_curr_state(message.chat_id) in states

    def callback_validator(tested_route: str, call: telethon.events.CallbackQuery.Event):
        return get_tp(call.data) == tested_route

    def action_validator(tested_route: str, tested_action: str, call: telethon.events.CallbackQuery.Event):
        return (
                    # Current state
                    storage.get_user_curr_state(call.chat_id) == tested_route
                    # or state independent action
                    or dict_tools.deep_get(
                            RouteMap.ROUTES, tested_route, 'actions', tested_action, 'state_independent'
                    ) is True
                    # And current callback
                ) and callback_validator(tested_action, call)

    route: AvailableRoutes
    for route in RouteMap.ROUTES:
        route_params = RouteMap.ROUTES[route]
        if route_params is None:
            continue

        handler = partial(processor, route)

        if 'command' in route_params.get('available_from', []):
            # Custom commands
            if 'commands' in route_params:
                commands_list_validator_partial = partial(commands_list_validator, route_params['commands'])
                thonbot.add_event_handler(handler, events.NewMessage(
                    incoming=True, pattern=commands_list_validator_partial))
            # Default commands – route name
            else:
                thonbot.add_event_handler(handler, events.NewMessage(incoming=True, pattern=f"/{route}"))

        if 'message' in route_params.get('available_from', []):
            message_validator_partial = partial(message_validator, route_params.get('states_for_input', [route]))
            thonbot.add_event_handler(handler, events.NewMessage(incoming=True, func=message_validator_partial))

        if 'call' in route_params.get('available_from', []):
            callback_validator_partial = partial(callback_validator, route)
            thonbot.add_event_handler(handler, events.CallbackQuery(func=callback_validator_partial))

        if 'actions' in route_params and route_params['actions'] is not None:
            for action in route_params['actions']:
                action_handler = partial(action_processor, route, action)
                action_validator_partial = partial(action_validator, route, action)
                thonbot.add_event_handler(action_handler, events.CallbackQuery(func=action_validator_partial))

    # TODO: realize the methods
    # # настройки
    # @thonbot.on(events.NewMessage(incoming=True, pattern="/settings"))
    # @thonbot.on(events.CallbackQuery(
    #     func=lambda call: get_tp(call.data) == 'setts'))
    # async def settings(event):
    #     data = await get_call_and_message(event)
    #     handle_event_in_thread({'action': settingsModule.openSettings, 'data': data})
    #
    # # страница настроек битрейта
    # @thonbot.on(events.CallbackQuery(
    #     func=lambda call: get_tp(call.data) == 's_btrt'))
    # async def bitrate_page(event):
    #     data = await get_call_and_message(event)
    #     handle_event_in_thread({'action': settingsModule.bitrateSettings, 'data': data})
    #
    # # изменения битрейта
    # @thonbot.on(events.CallbackQuery(
    #     func=lambda call: get_tp(call.data) == 'chbtrt'))
    # async def change_bitrate(event):
    #     data = await get_call_and_message(event)
    #     handle_event_in_thread({'action': settingsModule.changeBitrate, 'data': data})

    # Переписано на бота-агента!
    # обработка аудио до 2 гигов
    # @bot.message_handler(content_types=['document', 'audio'])
    # def agent_processing(message):
    # 	recsModule.catch_big_record(bot, message)

    # Ответ на сообщения, если не прошло верхнее, заглушка
    # @thonbot.on(events.NewMessage(incoming=True))
    # async def answer_on_message(event):
    #     # не команда
    #     if event.text != '' and event.text[0] != '/':
    #         chat_id = event.chat_id
    #         # если не принимающее текст состояние
    #         if storage.get_user_curr_state(chat_id) not in config.waitForTextStates:
    #             data = await get_message(event)
    #             handle_event_in_thread({'action': helpModule.shortHelp, 'data': data})

    # !!!!!!!!!!!
    # INLINE MODES
    @thonbot.on(events.InlineQuery)
    async def inline_queries_handler(event):
        inline = await get_inline(event)
        handle_event_in_thread({
            'action': searchModule.inline_podcast_searcher,
            'data': {'inline': inline}, 'special': 'inline'})
