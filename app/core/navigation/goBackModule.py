# -*- coding: utf-8 -*-
from app.core import controller
from app.routes.routes import RouteMap
from app.routes.routes_list import AvailableRoutes
from app.routes.ptypes import ControllerParams
from app.repository.storage import storage
from lib.tools.logger import logger


def is_screen(route, routes) -> bool:
    """A route "Back" can open: known, and with a method.

    A stored stack outlives the code. About a third of them (3.9k of 11.7k
    on 15 Oct 2026) hold names from the bot before its rewrite ('pc', 'srch',
    'welc'), and 'empty' is a route with no screen at all.
    """
    return bool((routes.get(route) or {}).get('method'))


def go_back(data: ControllerParams, custom_prev: AvailableRoutes = None):
    # try:

    prev, curr = storage.get_user_prev_curr_states(data['chat_id'])

    active_prev = prev if custom_prev is None else custom_prev
    if active_prev is None:
        return

    if not is_screen(active_prev, RouteMap.ROUTES):
        # Nothing to go back to: the main menu, on a clean stack (as a command does)
        logger.warn("Back to a screen that does not exist:", active_prev)
        storage.clear_user_storage(data['chat_id'])
        storage.add_user_state(data['chat_id'], 'menu')
        RouteMap.ROUTES['menu']['method'](controller.construct_params(
            data['callback'], data['message'], 'menu', is_step_back=True))
        return False

    method = RouteMap.ROUTES[active_prev]['method']

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
