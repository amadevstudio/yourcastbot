import json
import shelve
from functools import wraps
from typing import Mapping, Any, Sequence

from app.routes.routes_list import AvailableRoutes
from config import shelve_name
from lib.python.file_lock import InterprocessLock
from lib.tools.logger import logger

storage = shelve.open(shelve_name)
_lock = InterprocessLock(shelve_name + ".lock")


def _locked(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapped



@_locked
def clear_user_storage(chat_id):
    storage_values = ["states", "states_data", "resend_flag"]
    for i in storage_values:
        try:
            del storage[str(chat_id) + "_" + i]
        except Exception:
            pass  # print("can't delete " + i, flush=True)


@_locked
def clear_user_storage_partly(chat_id, storage_values=None):
    if storage_values is None:
        storage_values = []
    for i in storage_values:
        try:
            del storage[str(chat_id) + "_" + i]
        except Exception:
            pass  # print("can't delete " + i, flush=True)


@_locked
def get_message_structures(chat_id: int):
    try:
        message_structures_encoded = storage[f'users:tg:{chat_id}:message_structures']
    except KeyError:
        return []

    return json.loads(message_structures_encoded)


@_locked
def set_user_message_structures(chat_id: int, message_structures: Sequence[Any]):
    storage[f'users:tg:{chat_id}:message_structures'] = json.dumps(message_structures)


# флаг для повторной отправки
@_locked
def set_user_resend_flag(chat_id):
    storage[str(chat_id) + "_resend_flag"] = str(1)


@_locked
def get_user_resend_flag(chat_id):
    try:
        if storage[str(chat_id) + "_resend_flag"] == "1":
            return True
        else:
            return False
    except Exception:
        return False


@_locked
def del_user_resend_flag(chat_id):
    try:
        del storage[str(chat_id) + "_resend_flag"]
    except Exception:
        pass  # print("can't delete resend flag", flush=True)


# состояния
@_locked
def add_user_state(chat_id, state: AvailableRoutes):
    curr_state = get_user_curr_state(chat_id)
    if curr_state == state:
        return

    try:
        curr_states = json.loads(storage[str(chat_id) + "_states"])
    except Exception:
        curr_states = []

    # TODO: bug when curr_states is {'states': []}, added workaround
    if type(curr_states) is not list:
        logger.custom_err(f"Curr states for user #{chat_id} isn't list:", curr_states)
        curr_states = []

    curr_states.append(state)
    storage[str(chat_id) + "_states"] = json.dumps(curr_states)


@_locked
def get_user_states(chat_id) -> list[AvailableRoutes] | None:
    try:
        return json.loads(storage[str(chat_id) + "_states"])
    except Exception:
        return None


@_locked
def get_user_curr_state(chat_id) -> AvailableRoutes | None:
    try:
        curr_states = json.loads(storage[str(chat_id) + "_states"])
        return curr_states[len(curr_states) - 1]
    except Exception:
        return None


@_locked
def get_user_prev_state(chat_id) -> AvailableRoutes | None:
    try:
        curr_states = json.loads(storage[str(chat_id) + "_states"])
        return curr_states[len(curr_states) - 2]
    except Exception:
        return None


@_locked
def get_user_prev_curr_states(chat_id) -> tuple[AvailableRoutes | None, AvailableRoutes | None]:
    try:
        curr_states = json.loads(storage[str(chat_id) + '_states'])
        if len(curr_states) >= 2:
            return curr_states[-2], curr_states[-1]
        elif len(curr_states) == 1:
            return None, curr_states[0]
        else:
            return None, None
    except Exception:
        return None, None


@_locked
def del_user_curr_state(chat_id):
    try:
        curr_states = json.loads(storage[str(chat_id) + "_states"])
    except Exception:
        return
    if curr_states is not None:
        curr_states.pop()
    storage[str(chat_id) + "_states"] = json.dumps(curr_states)


@_locked
def del_user_state(chat_id):
    try:
        del storage[str(chat_id) + "_states"]
    except Exception:
        pass  # print("can't delete user states", flush=True)


# сохранение открытых каналов, поиска и так далее
@_locked
def set_user_state_data(chat_id, st_name: AvailableRoutes, st_params=None):
    if st_params is None:
        st_params = {}
    try:
        curr_data = json.loads(storage[str(chat_id) + "_states_data"])
    except Exception:
        curr_data = {'channel': {}, "pl": {}, "srch": {}}
    curr_data[st_name] = st_params
    storage[str(chat_id) + "_states_data"] = json.dumps(curr_data)


@_locked
def get_user_state_data(chat_id, st_name: AvailableRoutes | None) -> dict | None:
    if st_name is None:
        return None

    try:
        return json.loads(storage[str(chat_id) + "_states_data"])[st_name]
    except Exception:
        return None


@_locked
def get_user_state_data_empty(chat_id, st_name: AvailableRoutes):
    try:
        return json.loads(storage[str(chat_id) + "_states_data"])[st_name] == {}
    except Exception:
        return True


@_locked
def del_user_state_data(chat_id, st_name: AvailableRoutes):
    try:
        curr_data = json.loads(storage[str(chat_id) + "_states_data"])
    except Exception:
        return
    curr_data[st_name] = {}
    storage[str(chat_id) + "_states_data"] = json.dumps(curr_data)


@_locked
def del_user_state_alldata(chat_id):
    try:
        del storage[str(chat_id) + "_states_data"]
    except Exception:
        pass  # print("can't delete user states data", flush=True)


# сохранение последнего id канала в обработке
@_locked
def set_last_channel_id(channel_id):
    storage["last_channel_id"] = str(channel_id)


@_locked
def get_last_channel_id():
    try:
        return int(storage["last_channel_id"])
    except Exception:
        return 1


@_locked
def set_last_channel_restarted(restarted):
    storage["last_channel_restarted"] = ("1" if restarted else "0")


@_locked
def is_last_channel_restarted():
    try:
        return bool(int(storage["last_channel_restarted"]))
    except Exception:
        return False


# счётчик подряд идущих неудачных выборок фида канала
# нужен, чтобы не гасить уведомления из-за разового сбоя
def __channel_feed_failures_key(channel_id):
    return "channel_feed_failures_" + str(channel_id)


@_locked
def get_channel_feed_failures(channel_id) -> int:
    try:
        return int(storage[__channel_feed_failures_key(channel_id)])
    except Exception:
        return 0


@_locked
def increase_channel_feed_failures(channel_id) -> int:
    failures = get_channel_feed_failures(channel_id) + 1
    storage[__channel_feed_failures_key(channel_id)] = str(failures)
    return failures


@_locked
def reset_channel_feed_failures(channel_id):
    try:
        del storage[__channel_feed_failures_key(channel_id)]
    except Exception:
        pass


# флаги, что доступны подкасты
@_locked
def set_new_podcast_available_flag(user_id):
    try:
        flags = json.loads(storage["new_podcast_available_flag"])
    except Exception:
        flags = []
    if user_id not in flags:
        flags.append(user_id)
        storage["new_podcast_available_flag"] = json.dumps(flags)


@_locked
def get_new_podcast_available_flags():
    try:
        return json.loads(storage["new_podcast_available_flag"])
    except Exception:
        return []


@_locked
def clear_new_podcast_available_flags():
    try:
        del storage["new_podcast_available_flag"]
    except Exception:
        pass


def close_storage():
    try:
        storage.sync()
        storage.close()
        logger.log("Storage shelve closed")
    except Exception as e:
        logger.err("Error closing storage shelve:", e)
