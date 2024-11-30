import json
from typing import Any

import config
from app.repository.storage import storage
from app.routes.routes_list import AvailableActions
from app.routes.ptypes import Callback, Message
from app.routes.routes import AvailableRoutes
from lib.tools.logger import logger


def decode_call_data(call: Callback) -> dict[str, Any]:
    try:
        return json.loads(call.data)
    # except json.decoder.JSONDecodeError:
    #     return {}
    except Exception as e:
        logger.error(e)

    return {}


def get_local_state_data(chat_id: int, route: AvailableRoutes | None):
    try:
        return storage.get_user_state_data(chat_id, route)
    except json.decoder.JSONDecodeError:
        return {}


def get_call_data(call: Callback | None, route: AvailableRoutes | None, action: AvailableActions | None = None):
    if call is None:
        call_data = {}
    else:
        call_data = decode_call_data(call)

        # Если не действие (смена маршрута, назад, валидации)
        if action is None:
            # То учитывать только state_data для этого же маршрута
            if call_data['tp'] != route:
                call_data = {}
        # Если действие, примешать к состоянию, удалив tp
        else:
            del call_data['tp']
    return call_data


def get_state_data(chat_id: int, route: AvailableRoutes | None):
    return get_local_state_data(chat_id, route) or {}


def get_united_data(
        call: Callback | None,
        chat_id: int,
        route: AvailableRoutes | None,
        action: AvailableActions | None = None
) -> dict[str, Any]:
    # 1. Смена маршрута: данные маршрута (пустые) + call (так как tp равен маршруту)
    # 2. Экшен: данные маршрута + call (без tp, мутация)
    # 3. Назад: данные маршрута + call (пустой, так как tp не равен маршруту)
    # 4. Валидации: данные маршрута (пустые или нет) + call (пустой, если кнопка не маршрута)

    call_data = get_call_data(call, route, action)
    state_data = get_state_data(chat_id, route)

    if not config.server:
        logger.log("Call data:", call_data)
        logger.log("State data:", state_data)

    return state_data | call_data
