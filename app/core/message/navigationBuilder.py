import copy
import typing
from typing import Any, Callable, TypedDict

import math

from app.routes.router_tools import is_command
from app.routes.routes_list import AvailableRoutes
from app.routes.ptypes import Callback, Message
from lib.telegram.general.message_master import InlineButtonData
from app.i18n.messages import get_message
from lib.tools.logger import logger


class PageData(TypedDict):
    data: Any
    page_count: int | None
    current_page: int
    count: int


def determine_search_query_and_page(
        call: Callback | None,
        message: Message | None, state_data: dict[str, Any],
        numbers_are_pages: bool = True
) -> dict[str, Any]:
    # state_data = state_data | call_data
    local_state_data = copy.deepcopy(state_data)

    # Getting page
    if call is not None:
        local_state_data['p'] = local_state_data.get('p', 1)
    else:
        if message is not None:
            if numbers_are_pages:
                try:
                    local_state_data['p'] = int(message.text)  # Raising ValueError
                except ValueError:
                    # If the message is received but isn't number, search just mode have been started, so page is 1
                    local_state_data['p'] = 1
        if local_state_data.get('p', None) is None:
            local_state_data['p'] = 1

    # If text input, return with new search
    if call is None and message is not None and message.text != '':
        if not is_command(message.text):
            if numbers_are_pages:
                try:
                    int(message.text)
                except ValueError:
                    local_state_data['search'] = message.text
                    return local_state_data
            else:
                local_state_data['search'] = message.text
                return local_state_data
        else:
            message_text = message.text.rstrip()
            search_query = " ".join(message_text.split(" ")[1:])
            if len(search_query) > 0:
                local_state_data['search'] = search_query
                return local_state_data

    # if set as None, delete search query
    if 'search' in local_state_data and local_state_data['search'] is None:
        del local_state_data['search']

    return local_state_data


# возвращает данные из бд на нужной странице и общее количество
def load_page_data(
        data_funct: Callable, data_funct_params: list, count_funct: Callable | None, count_funct_params: list | None,
        current_page: int, per_page: int,
        order_rules: None | str | list[str | dict[str, typing.Literal['ASC', 'DESC']]],
        order_by_builder: Callable | None
) -> PageData | TypedDict('LoadPageDataError', {'error': str}):
    if current_page < 1:
        current_page = 1

    count = count_funct(*count_funct_params)

    if count == 0:
        return {
            'error': 'empty'
        }

    page_count = math.ceil(count / per_page)
    if current_page > page_count:
        current_page = page_count

    order_by = order_by_builder(order_rules) if isinstance(order_by_builder, Callable) else None
    data = data_funct(*data_funct_params, order_by, per_page, per_page * (current_page - 1))

    return {
        'data': data,
        'page_count': page_count,
        'current_page': current_page,
        'count': count
    }


LoadPageDataError = TypedDict('LoadPageDataError', {'error': str})


def load_page_data_with_count(
        data_funct: Callable, data_funct_params: list,
        current_page: int, per_page: int,
        order_rules: None | str | list[str | dict[str, typing.Literal['ASC', 'DESC']]],
        order_by_builder: Callable | None
) -> PageData | LoadPageDataError:
    if current_page < 1:
        current_page = 1

    order_by = order_by_builder(order_rules) if isinstance(order_by_builder, Callable) else None
    data: TypedDict('data', {'results': list, 'count': int}) \
        = data_funct(*data_funct_params, order_by, per_page, per_page * (current_page - 1))

    count = data['count']
    if count == 0:
        return {
            'error': 'empty'
        }

    page_count = math.ceil(count / per_page)
    if current_page > page_count:
        current_page = page_count
        # When we don't know about page count before, get the results again
        if len(data['results']) == 0:
            data = data_funct(*data_funct_params, order_by, per_page, per_page * (current_page - 1))

    return {
        'data': data['results'],
        'page_count': page_count,
        'current_page': current_page,
        'count': count
    }


def order_builder_sql(order_rules: str | list[str | dict[str, typing.Literal['ASC', 'DESC']]] | None) -> str | None:
    if order_rules is None:
        return None

    if isinstance(order_rules, str):
        return f"ORDER BY {order_rules}"

    if len(order_rules) == 0:
        return None

    def build_params(watched_order_rules: list[str | dict[str, typing.Literal['ASC', 'DESC']]]) \
            -> typing.Generator[str, None, None]:
        for order_rule in watched_order_rules:
            if isinstance(order_rule, str):
                yield order_rule
            elif isinstance(order_rule, dict):
                for key, value in order_rule.items():
                    yield f"{key} {value}"

    return "ORDER BY " + ",".join(build_params(order_rules))


class NavLayoutParts(TypedDict, total=False):
    exit_search_mode_row: list[InlineButtonData]
    navigation_row: list[InlineButtonData]


# возвращает кнопки переключения страниц
def generate_nav_layout_parts(
        search_query: str | None, current_page, page_count, current_type,
        language_code, back_button_text: str = "goBack", with_exit_search_button: bool = True
) -> NavLayoutParts:
    buttons: NavLayoutParts = {}

    if search_query is not None and with_exit_search_button:
        exit_search_mode_button = {'text': get_message("exitSearchMode", language_code),
                                   'callback_data': {'tp': current_type, 'p': 1, 'search': None}}
        buttons['exit_search_mode_row'] = [exit_search_mode_button]

    cb_data = {"tp": current_type, "p": current_page - 1}
    text = ("❮" if current_page > 1 else "-")
    button_prev = {'text': text, 'callback_data': cb_data}

    b = {'text': get_message(back_button_text, language_code), 'callback_data': {'tp': 'bck'}}

    text = ("❯" if current_page < page_count else "-")
    cb_data = {"tp": current_type, "p": current_page + 1}
    button_next = {'text': text, 'callback_data': cb_data}

    buttons['navigation_row'] = [button_prev, b, button_next]
    return buttons


# возвращает сообщение "x страница из y"
def get_page_of_pages(curr_page, page_count, language_code):
    return str(curr_page) + " " \
        + get_message("page", language_code).lower() + " " \
        + get_message("of", language_code).lower() + " " + str(page_count)


def get_routing_helper(current_page, page_count, language_code, with_pro_tip=True):
    space_const = "                   ."
    if page_count == 1:
        return space_const

    else:
        result = "\n" + get_page_of_pages(current_page, page_count, language_code)
        if with_pro_tip:
            result += "\n\n" + get_message('proTipSendPageNumToGo', language_code)
        result += "\n" + get_message('sendTextToRestartSearch', language_code)
        return result + space_const


class FullMessageNavigation(TypedDict):
    page_data: PageData | LoadPageDataError
    routing_helper_message: str | None
    nav_layout_parts: NavLayoutParts | None


def get_full_message_navigation(page: int | None, search_query: str | None, data_provider: Callable,
                                data_params: list[Any], data_count_provider: Callable | None,
                                data_count_params: list[Any] | None, per_page: int,
                                order_rules: None | str | list[str | dict[str, typing.Literal['ASC', 'DESC']]],
                                language_code: str, current_type: AvailableRoutes, back_button_text: str = 'goBack',
                                order_builder: Callable | None = order_builder_sql, with_pro_tip: bool = True,
                                with_exit_search_button: bool = True
                                ) -> FullMessageNavigation:
    if data_count_provider is not None:
        page_data = load_page_data(
            data_provider, data_params, data_count_provider, data_count_params, page, per_page,
            order_rules, order_builder)
    else:
        page_data = load_page_data_with_count(
            data_provider, data_params, page, per_page, order_rules, order_builder)

    if 'error' in page_data:
        return {
            'page_data': page_data, 'routing_helper_message': None, 'nav_layout_parts': None}

    page_count = page_data['page_count']

    routing_helper_message = get_routing_helper(page_data['current_page'], page_count, language_code,
                                                with_pro_tip=with_pro_tip)
    nav_layout_parts = generate_nav_layout_parts(
        search_query, page_data['current_page'], page_count,
        current_type, language_code, back_button_text, with_exit_search_button)

    return {
        'page_data': page_data,
        'routing_helper_message': routing_helper_message, 'nav_layout_parts': nav_layout_parts}
