from app.controller.general.notify import notify
import lib.markup.cleaner
from app.core.message.navigationBuilder import get_full_message_navigation, FullMessageNavigation, \
    determine_search_query_and_page
from lib.python.dict_tools import deep_get
from lib.telegram.general.message_master import message_master, render_messages, MessageStructuresInterface, \
    InlineButtonData
from app.i18n.messages import get_message, standartSymbols, get_message_rtd
from app.repository.storage import storage
from config import db_path, perPage
from db.sqliteAdapter import SQLighter
from app.routes.ptypes import Message, Callback, ControllerParams
from lib.tools.logger import logger

PER_PAGE = 5


def show_subs(data: ControllerParams):
    current_state_data = determine_search_query_and_page(data['callback'], data['message'], data['united_data'])
    search_query = current_state_data.get('search', None)

    db_users = SQLighter(db_path)
    message_navigation = get_full_message_navigation(
        current_state_data.get('p', None), search_query,
        db_users.select_users_subs_name_noty,[data['chat_id'], search_query],
        db_users.select_users_subs_count, [data['chat_id'], search_query],
        PER_PAGE,[{'have_new_episodes': 'DESC'}, 'channels.name'],
        data['language_code'], data['route_name'], back_button_text='goBackMenu')
    db_users.close()

    if 'error' in message_navigation['page_data']:
        if message_navigation['page_data']['error'] == 'empty':
            error_text_getter = 'empty' if search_query is None else 'empty_when_search'
            error_message = get_message_rtd(
                ['subs', 'errors', 'paging', error_text_getter], data['language_code'])
        else:
            error_message = get_message_rtd(['errors', 'unknown'], data['language_code'])
        notify(data['callback'], data['message'], text=error_message, resending=True)
        return False

    subs_msg = construct_subs_message(message_navigation, data['language_code'])

    render_messages(data['chat_id'], subs_msg, resending=data['is_command'])

    storage.set_user_state_data(data['chat_id'], data['route_name'],{
        **current_state_data, 'p': message_navigation['page_data']['current_page']})


def construct_subs_message(message_navigation: FullMessageNavigation, language_code: str) \
        -> list[MessageStructuresInterface]:
    subs_keyboard: list[list[InlineButtonData]] = []

    for sub in message_navigation['page_data']['data']:
        new_eps = standartSymbols.get('newItem', "") + " " \
            if sub['have_new_episodes'] == 1 \
            else ""

        try:
            # if user_subs[str(sub)]["notify"]:
            if sub["notify"]:
                notify_enabled = '\U0001F514'  # sound enabled
            else:
                notify_enabled = '\U0001F515'  # sound disabled
        except Exception:
            notify_enabled = '\U0001F514'  # enabled

        b = {'text': new_eps + " " + notify_enabled + " " + lib.markup.cleaner.html_mrkd_cleaner(sub['name']),
             'callback_data': {'tp': 'podcast', 'id': sub['id']}}
        subs_keyboard.append([b])

    if message_navigation['nav_layout_parts'] is not None:
        if message_navigation['nav_layout_parts'].get('exit_search_mode_row', None) is not None:
            subs_keyboard += [message_navigation['nav_layout_parts']['exit_search_mode_row']]
        subs_keyboard += [message_navigation['nav_layout_parts']['navigation_row']]

    return [{
        'type': 'text',
        'text':
            get_message("subsMessage", language_code) + "\n"
            + message_navigation['routing_helper_message'],
        'reply_markup': subs_keyboard,
    }]
