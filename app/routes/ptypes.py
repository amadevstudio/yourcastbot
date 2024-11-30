from typing import Optional, TypedDict, Any, Callable, NotRequired

from app.routes.routes_list import AvailableRoutes, AvailableActions
from lib.python.obj_dict import Serializable


class Chat(object):
    def __init__(self, id: int):
        self.id: int = id


class User(object):
    def __init__(self, language_code: str):
        self.language_code: str = language_code


class ForwardedFrom(object):
    def __init__(self, channel_id: str):
        self.channel_id: str = channel_id


class Message(Serializable):
    def __init__(
            self, message_id: str, chat: Chat, from_user: User, text: str, fwd_from: Optional[ForwardedFrom] = None):
        self.message_id: str = message_id
        self.chat: Chat = chat
        self.from_user: User = from_user
        self.text: str = text
        self.fwd_from: ForwardedFrom | None = fwd_from


class Callback(Serializable):
    def __init__(self, id: str, data: str, user: User, chat: Chat, message: Optional[Message] = None):
        self.id = id
        self.data = data
        self.from_user = user
        self.chat = chat
        self.message = message


class Inline(Serializable):
    def __init__(self, id: str, user_id: int, query: str, offset: int):
        self.id = id
        self.user_id = user_id
        self.query = query
        self.offset = offset


class ControllerParams(TypedDict):
    callback: Callback | None
    message: Message | None

    chat_id: int
    language_code: str

    route_name: AvailableRoutes | None
    action_name: AvailableActions | None
    united_data: dict[str, Any]

    is_step_forward: bool
    is_step_back: bool
    is_command: bool

    go_back_action: Callable

    # User is set in thread processing
    user: NotRequired[Any]


class InlineControllerParams(TypedDict):
    inline: Inline

    # User is set in thread processing
    user: NotRequired[Any]


class HandleInThreadParams(TypedDict, total=False):
    action: Callable
    data: ControllerParams | InlineControllerParams
    special: str
