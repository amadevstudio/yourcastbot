import telethon

from app.repository.storage import storage
from app.routes import router_tools
from app.routes.routes import RouteMap
from app.routes.routes_list import AvailableRoutes, AvailableActions
from app.routes.state_data import get_united_data
from app.routes.ptypes import Callback, Message, ControllerParams
from app.core.navigation import goBackModule
from lib.python import dict_tools


def empty_state_input_state_corrector(event: telethon.events.NewMessage.Event):
    prev, curr = storage.get_user_prev_curr_states(event.chat_id)
    if prev is None:
        return

    empty: AvailableRoutes = 'empty'

    someone_have_state_for_input: bool = False
    for route_params in RouteMap.ROUTES.values():
        if route_params is None:
            continue

        if prev in route_params.get('states_for_input', []):
            someone_have_state_for_input = True
            break

    # (Prev waits for input or someone waits for input when prev is active) and empty is curr
    if (
            (dict_tools.deep_get(RouteMap.ROUTES, prev, 'waits_for_input', default=False)
             or someone_have_state_for_input)
            and curr == empty):
        storage.del_user_curr_state(event.chat_id)


def construct_params(
        callback: Callback | None, message: Message | None,
        route_name: AvailableRoutes | None, action_name: AvailableActions | None = None,
        is_step_back: bool = False
) -> ControllerParams:
    if callback is not None:
        chat_id = callback.chat.id
        language_code = callback.from_user.language_code
    else:
        chat_id = message.chat.id
        language_code = message.from_user.language_code

    current_state = storage.get_user_curr_state(chat_id)
    is_step_forward = (not is_step_back
                       and current_state is not None and route_name is not None
                       and current_state != route_name)
    # If step forward, delete state data
    if is_step_forward and route_name is not None:
        storage.del_user_state_data(chat_id, route_name)

    return {
        'callback': callback,
        'message': message,

        'chat_id': chat_id,
        'language_code': language_code,

        'route_name': route_name,
        'action_name': action_name,
        'united_data': get_united_data(callback, chat_id, route_name, action_name),

        'is_step_forward': is_step_forward,
        'is_step_back': is_step_back,
        'is_command': callback is None and message is not None and router_tools.is_command(message.text),

        'go_back_action': goBackModule.go_back,

        'user': None
    }
