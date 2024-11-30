# -*- coding: utf-8 -*-
from app.core import controller
from app.routes.routes import RouteMap
from app.routes.routes_list import AvailableRoutes
from app.routes.ptypes import ControllerParams
from app.repository.storage import storage


def go_back(data: ControllerParams, custom_prev: AvailableRoutes = None):
    # try:

    prev, curr = storage.get_user_prev_curr_states(data['chat_id'])

    active_prev = prev if custom_prev is None else custom_prev
    if active_prev is None:
        return

    method = RouteMap.ROUTES[active_prev].get('method', None)
    if method is None:
        # TODO: show error
        return

    method(controller.construct_params(data['callback'], data['message'], active_prev, is_step_back=True))

    all_states = storage.get_user_states(data['chat_id'])
    if all_states is not None:
        for state in reversed(all_states):
            if state == active_prev:
                break
            storage.del_user_curr_state(data['chat_id'])

    for child_route in RouteMap.ROUTES[active_prev].get('routes', []):
        storage.del_user_state_data(data['chat_id'], child_route)

    # except Exception as e:
    #     welcome_controller.menu(call.message)

    # Don't change state after
    return False
