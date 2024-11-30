import json
import threading
import time
from typing import Any, Mapping

import app.service.podcast.subscription
import config
from app.routes.ptypes import Message, Callback, ControllerParams, Inline, InlineControllerParams
from lib.telegram.general.message_master import message_master
from app.controller.builders import podcastModule, adminModule, recsModule
from app.i18n.messages import get_message
from app.repository.storage import storage
from app.service.payment import paymentSafeModule
from db.sqliteAdapter import SQLighter
from lib.analytics.analytics import Analytics, SpecialEventDataNewUserType, SmartEventTelegramProcessingType, \
    SpecialEventDataPodcastOpenedByLink
from lib.tools.logger import logger
from scripts import restart_bot


def get_user(user_id: int) -> Any:
    db_users = SQLighter(config.db_path)
    user = db_users.get_user_by_tg(user_id)
    db_users.close()
    return user


def check_threads(threads_to_watch: list[threading.Thread]):
    # чекаем поток
    for t in threads_to_watch:
        if not t.is_alive():
            try:
                print(f"\n\nThreadDEAD!!! {t.name}\n\n", flush=True)
                adminModule.send_thread_dead_message_to_creator()

                if config.server:
                    time.sleep(1)
                    restart_bot.restart()

            except Exception as e:
                print("\n\nmainf/serving: ", e, "\n\n", flush=True)

                if "[Errno 12] Cannot allocate memory" in str(e):
                    adminModule.send_message_to_creator("Cannot allocate memory")
                    restart_bot.print_top_memory()
                    restart_bot.restart()


def analytics_serving(tg_data: ControllerParams, user: Any, is_new_user: bool = False,
                      is_by_refer: bool = False, action: str | None = None):

    # Аналитика
    try:
        analytics = Analytics()
        analytics_data: SmartEventTelegramProcessingType = {
            'tgData': tg_data, 'userSystemId': user['id'], 'actionName': str(tg_data['action_name']),
            'language_code': user['lang'], 'specialEventData': None}

        # особые случаи при старте бота
        if is_new_user:
            special_event_data_new_user: SpecialEventDataNewUserType = {'mode': 'new_user'}
            if is_by_refer:
                special_event_data_new_user['is_referred'] = True
            # analyticsData['specialEventData']['refer_id'] = refer_id
            analytics_data['specialEventData'] = special_event_data_new_user
        elif action is not None:
            if action in ["podcast", "podcastItunes"]:
                special_event_data_podcast_opened_by_link: SpecialEventDataPodcastOpenedByLink = \
                    {'mode': 'podcast_opened_by_link', 'action': action}
                analytics_data['specialEventData'] = special_event_data_podcast_opened_by_link

        if tg_data['callback'] is not None:
            # особые случаи
            button_data = json.loads(tg_data['callback'].data)
            if tg_data['route_name'] == 'recs' and button_data.get('show_file_sizes', False) is True:
                analytics_data['actionName'] = 'turn_file_sizes_on'

        analytics.smart_event_telegram_processing(analytics_data)
    except Exception as e:
        logger.err(e)
        pass


def analytics_serving_inline(tg_data: InlineControllerParams, user: Any):
    # Аналитика
    try:
        analytics = Analytics()
        analytics_data = {
            'tgData': tg_data, 'userSystemId': user['id'], 'language_code': user['lang'],
            'specialEventData': {}}

        analytics_data['specialEventData']['mode'] = "search_inline"
        analytics.smart_event_telegram_processing(analytics_data)
    except Exception:
        pass
