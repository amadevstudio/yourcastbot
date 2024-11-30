import json
import typing
from typing import TypedDict, Literal, Required

import requests
import queue
import threading
import hashlib

from app.routes.ptypes import ControllerParams, Inline, InlineControllerParams
from app.routes.router_tools import is_command
from lib.python.singletonBase import Singleton


class SpecialEventDataNewUserType(TypedDict, total=False):
    mode: Required[Literal['new_user']]
    is_referred: bool


class SpecialEventDataPodcastOpenedByLink(TypedDict):
    mode: Literal['podcast_opened_by_link']
    action: str


class SmartEventTelegramProcessingType(TypedDict):
    tgData: ControllerParams | InlineControllerParams
    userSystemId: int
    actionName: str
    language_code: str
    specialEventData: SpecialEventDataNewUserType | SpecialEventDataPodcastOpenedByLink | None


class Analytics(metaclass=Singleton):

    def __init__(self, adapter=None, test_mode=False):

        if adapter is None:
            raise AttributeError

        self.__adapter = adapter
        self.__save_analytics = not test_mode

        self.queue = queue.Queue()

        senderThread = threading.Thread(target=self.__thread_processor)
        senderThread.daemon = True
        senderThread.start()

    def __thread_processor(self):
        while True:
            items = self.queue.get()
            func = items[0]
            args = items[1]

            func(args)

    def event(self, args):

        user_id = args["user_id"]
        event_type = args["command"]
        platform = None if "platform" not in args else args["platform"]
        user_properties = {} if "user_properties" not in args \
            else args["user_properties"]
        event_properties = {} if "event_properties" not in args \
            else args["event_properties"]

        if self.__save_analytics:
            self.__adapter.event(
                user_id, event_type, platform=platform,
                user_properties=user_properties,
                event_properties=event_properties)

    # Telegram related
    def smart_event_telegram_processing(self, analytics_data: SmartEventTelegramProcessingType):
        event_properties: dict = {}
        command: str | None

        if analytics_data['specialEventData'] is not None:
            command = str(analytics_data['specialEventData']['mode'])

            if analytics_data['specialEventData']['mode'] == "search_inline":
                user_lang = analytics_data['language_code']
                user_telegram_id = analytics_data['tgData']['user_id']

                request_type = "inline"

            # особые случаи при старте: refered, podcast_opened_by_link
            else:
                user_lang = analytics_data['language_code']
                user_telegram_id = analytics_data['tgData']['chat_id']

                request_type = "start_special"

        else:
            controller_params = typing.cast(ControllerParams, analytics_data['tgData'])
            if analytics_data['tgData'].get('callback', None) is not None:
                request_type = 'call'
                message = controller_params.get('message', None)
                command = controller_params['route_name']
            else:
                request_type = 'message'
                if analytics_data['specialEventData'] is not None:
                    command = str(analytics_data['specialEventData']['mode'])
                else:
                    command = controller_params['route_name']

            user_lang = controller_params['language_code']
            user_telegram_id = controller_params['chat_id']

            if 'specialEventData' in analytics_data and analytics_data['specialEventData'] is not None:
                event_properties = analytics_data["specialEventData"]

        if command is None:
            return

        event_properties["original_command"] = command
        event_properties["request_type"] = request_type
        command = command.split(" ")[0]

        # объединить команды из сообщения и из inline
        same_actions = {
            'botSub': 'subscription',
            'another': 'another_projects',
            'subs': 'subscriptions',
            'topGnrs': 'genres',  # топ жанров + общий топ в виде кнопок внутри
            'top_ch': 'top'
        }
        command = same_actions.get(command, command)

        self.queue.put((
            self.event,
            {
                "user_id": analytics_data['userSystemId'], "command": command,
                "user_properties": {
                    "lang": user_lang,
                    "telegram_id": user_telegram_id},
                "event_properties": event_properties}))


class AmplitudeAnalytics:

    def __init__(
            self, api_key, endpoint="https://api.amplitude.com/2/httpapi"
    ):
        self.__api_key = api_key
        self.__endpoint = endpoint

    def __make_request(self, event):
        headers = {
            'Content-Type': 'application/json',
            'Accept': '*/*'
        }

        try:
            _ = requests.post(self.__endpoint, data=json.dumps({
                'api_key': self.__api_key,
                'events': [event],
            }), headers=headers)

        except Exception:
            # Unavailable
            pass

    def event(
            self, user_id, event_type, platform="Telegram",
            user_properties={}, event_properties={}
    ):

        m = hashlib.sha256()
        m.update(str(user_id).encode('utf-8'))
        hashed_user_id = m.hexdigest()
        # id must be at least 5 length
        prepared_id = f"{user_id}_{hashed_user_id[:5]}"

        event = {
            "user_id": prepared_id,  # unique user identifier
            "event_type": event_type,  # the name of event
            "platform": "Telegram" if platform is None else platform,
            # user-related info to tract and filter in Amplitude web UI
            "language": (
                None if not user_properties['lang']
                else user_properties['lang']),
            "user_properties": user_properties,
            # set any additional information about this action
            "event_properties": event_properties
        }

        self.__make_request(event)
