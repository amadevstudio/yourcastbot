import json
import os
import shelve
import threading
from functools import wraps
from typing import Mapping, Any, Sequence

from app.routes.routes_list import AvailableRoutes
from config import shelve_name
from db import runtime_kv
from lib.tools.logger import logger

_thread_lock = threading.RLock()
_shelve_init_lock = threading.Lock()
_shelve_db = None


def _role():
    return os.environ.get("YOURCAST_ROLE") or ""


def _shelve_allowed():
    # Unset role = legacy single process. After the split, only bot opens gdbm.
    return _role() in ("", "bot")


def _get_shelve():
    global _shelve_db
    if not _shelve_allowed():
        raise RuntimeError(
            "FSM shelve is opened only in the bot process; "
            "updater/jobs must use sqlite (runtime_kv)")
    with _shelve_init_lock:
        if _shelve_db is None:
            _shelve_db = shelve.open(shelve_name)
        return _shelve_db


class _LazyShelve:
    def __getitem__(self, key):
        return _get_shelve()[key]

    def __setitem__(self, key, value):
        _get_shelve()[key] = value

    def __delitem__(self, key):
        del _get_shelve()[key]

    def sync(self):
        db = _shelve_db
        if db is not None:
            db.sync()

    def close(self):
        global _shelve_db
        with _shelve_init_lock:
            db = _shelve_db
            _shelve_db = None
        if db is not None:
            try:
                db.sync()
                db.close()
            except Exception:
                pass


storage = _LazyShelve()


def _locked(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _thread_lock:
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
    del_user_resend_flag(chat_id)


@_locked
def clear_user_storage_partly(chat_id, storage_values=None):
    if storage_values is None:
        storage_values = []
    for i in storage_values:
        try:
            del storage[str(chat_id) + "_" + i]
        except Exception:
            pass  # print("can't delete " + i, flush=True)


def get_message_structures(chat_id: int):
    raw = runtime_kv.get_kv("users:tg:%s:message_structures" % chat_id)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def set_user_message_structures(chat_id: int, message_structures: Sequence[Any]):
    runtime_kv.set_kv(
        "users:tg:%s:message_structures" % chat_id,
        json.dumps(list(message_structures)))


# флаг для повторной отправки (sqlite: bot and updater both write this)
def set_user_resend_flag(chat_id):
    runtime_kv.set_kv("resend_flag_" + str(chat_id), "1")


def get_user_resend_flag(chat_id):
    return runtime_kv.get_kv("resend_flag_" + str(chat_id)) == "1"


def del_user_resend_flag(chat_id):
    runtime_kv.delete_kv("resend_flag_" + str(chat_id))


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


# курсор апдейтера, счётчик фейлов фида, флаги дайджеста — sqlite,
# потому что bot и updater — разные процессы и gdbm так не шарится.
def set_last_channel_id(channel_id):
    runtime_kv.set_kv("last_channel_id", str(channel_id))


def get_last_channel_id():
    try:
        return int(runtime_kv.get_kv("last_channel_id") or 1)
    except Exception:
        return 1


def set_last_channel_restarted(restarted):
    runtime_kv.set_kv("last_channel_restarted", "1" if restarted else "0")


def is_last_channel_restarted():
    try:
        return bool(int(runtime_kv.get_kv("last_channel_restarted") or "0"))
    except Exception:
        return False


def __channel_feed_failures_key(channel_id):
    return "channel_feed_failures_" + str(channel_id)


def get_channel_feed_failures(channel_id) -> int:
    try:
        return int(runtime_kv.get_kv(__channel_feed_failures_key(channel_id)) or 0)
    except Exception:
        return 0


def increase_channel_feed_failures(channel_id) -> int:
    return runtime_kv.incr_kv(__channel_feed_failures_key(channel_id))


def reset_channel_feed_failures(channel_id):
    runtime_kv.delete_kv(__channel_feed_failures_key(channel_id))


def set_new_podcast_available_flag(user_id):
    from app.jobs.digest_outbox import enqueue
    enqueue(user_id)


def get_new_podcast_available_flags():
    try:
        return json.loads(
            runtime_kv.get_kv("new_podcast_available_flag") or "[]")
    except Exception:
        return []


def clear_new_podcast_available_flags():
    runtime_kv.delete_kv("new_podcast_available_flag")


def close_storage():
    try:
        storage.close()
        logger.log("Storage shelve closed")
    except Exception as e:
        logger.err("Error closing storage shelve:", e)
