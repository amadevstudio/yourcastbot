import json
import os
import threading
import time
from functools import wraps
from typing import Mapping, Any, Sequence

from app.routes.routes_list import AvailableRoutes
from db import runtime_kv
from lib.net.enclosure import (
    COOL_SECONDS, FAULT_WINDOW_SECONDS, FAULTS_BEFORE_COOL, enclosure_hosts,
    host_from_error, host_from_url)
from lib.tools.logger import logger

_thread_lock = threading.RLock()

# Menu states ("<chat>_states", "<chat>_states_data") under this prefix in
# bot_runtime_kv. They lived in a gdbm shelve: it never gives space back
# (10 MB of states in a 448 MB file) and could only be compacted with the
# bot stopped.
FSM_KEY_PREFIX = "fsm:"


def _role():
    return os.environ.get("YOURCAST_ROLE") or ""


def _fsm_allowed():
    # The menu belongs to the bot process (unset role = legacy single process);
    # updater/jobs touching it would be a bug, as it was with the shelve.
    return _role() in ("", "bot")


class _FsmStore:
    """Dict-like view of the menu states; same interface the shelve had.

    One connection per thread, kept open: a screen reads and writes states
    several times, and opening SQLite for each access cost ~8 ms.
    """

    def __init__(self, database=None):
        self.database = database
        self._local = threading.local()

    def _conn(self):
        if not _fsm_allowed():
            raise RuntimeError(
                "menu states are used only in the bot process")
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = runtime_kv._connect(self.database)
            self._local.conn = conn
        return conn

    def __getitem__(self, key):
        row = self._conn().execute(
            "SELECT value FROM bot_runtime_kv WHERE key = ?",
            (FSM_KEY_PREFIX + key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return row["value"]

    def __setitem__(self, key, value):
        # Autocommit: one statement, one transaction
        self._conn().execute(
            "INSERT INTO bot_runtime_kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (FSM_KEY_PREFIX + key, str(value)))

    def __delitem__(self, key):
        cursor = self._conn().execute(
            "DELETE FROM bot_runtime_kv WHERE key = ?", (FSM_KEY_PREFIX + key,))
        if cursor.rowcount == 0:
            raise KeyError(key)

    def sync(self):
        pass

    def close(self):
        conn = getattr(self._local, "conn", None)
        self._local.conn = None
        if conn is not None:
            conn.close()


storage = _FsmStore()


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
def _load_states(chat_id) -> list | None:
    """The screen stack; None when there is none.

    About a third of the stored stacks (4.7k on 6 Oct 2026) are an old shape,
    {"states": [...]}: read as a list they made the current screen unknown,
    reset the stack with an ERR on the next tap, and broke "Back" (dict.pop).
    """
    try:
        states = json.loads(storage[str(chat_id) + "_states"])
    except Exception:
        return None
    if isinstance(states, dict):
        states = states.get("states")
    if not isinstance(states, list):
        return None
    return states


@_locked
def add_user_state(chat_id, state: AvailableRoutes):
    curr_states = _load_states(chat_id) or []
    if curr_states and curr_states[-1] == state:
        return

    curr_states.append(state)
    storage[str(chat_id) + "_states"] = json.dumps(curr_states)


@_locked
def get_user_states(chat_id) -> list[AvailableRoutes] | None:
    return _load_states(chat_id)


@_locked
def get_user_curr_state(chat_id) -> AvailableRoutes | None:
    curr_states = _load_states(chat_id)
    return curr_states[-1] if curr_states else None


@_locked
def get_user_prev_state(chat_id) -> AvailableRoutes | None:
    curr_states = _load_states(chat_id)
    return curr_states[-2] if curr_states and len(curr_states) >= 2 else None


@_locked
def get_user_prev_curr_states(chat_id) -> tuple[AvailableRoutes | None, AvailableRoutes | None]:
    curr_states = _load_states(chat_id)
    if not curr_states:
        return None, None
    if len(curr_states) == 1:
        return None, curr_states[0]
    return curr_states[-2], curr_states[-1]


@_locked
def del_user_curr_state(chat_id):
    curr_states = _load_states(chat_id)
    if curr_states is None:
        return
    if curr_states:
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


def get_channel_feed_failures(channel_id, database=None) -> int:
    try:
        return int(runtime_kv.get_kv(
            __channel_feed_failures_key(channel_id), database=database) or 0)
    except Exception:
        return 0


def increase_channel_feed_failures(channel_id, database=None) -> int:
    return runtime_kv.incr_kv(
        __channel_feed_failures_key(channel_id), database=database)


def reset_channel_feed_failures(channel_id, database=None):
    runtime_kv.delete_kv(
        __channel_feed_failures_key(channel_id), database=database)


def __channel_feed_dead_key(channel_id):
    return "channel_feed_dead_until_" + str(channel_id)


def get_channel_feed_dead_until(channel_id, database=None) -> float | None:
    raw = runtime_kv.get_kv(
        __channel_feed_dead_key(channel_id), database=database)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def set_channel_feed_dead_until(channel_id, until_ts, database=None):
    runtime_kv.set_kv(
        __channel_feed_dead_key(channel_id), str(until_ts), database=database)


def clear_channel_feed_dead(channel_id, database=None):
    runtime_kv.delete_kv(
        __channel_feed_dead_key(channel_id), database=database)
    reset_channel_feed_failures(channel_id, database=database)


def __enclosure_cool_key(host):
    return "enclosure_cool_until_" + str(host)


def __enclosure_faults_key(host):
    return "enclosure_faults_" + str(host)


def __host_is_cool(host, now=None, database=None) -> bool:
    until = runtime_kv.get_kv(__enclosure_cool_key(host), database=database)
    if until is None or until == "":
        return False
    try:
        deadline = float(until)
    except (TypeError, ValueError):
        return False
    stamp = time.time() if now is None else float(now)
    if stamp >= deadline:
        runtime_kv.delete_kv(__enclosure_cool_key(host), database=database)
        return False
    return True


def enclosure_host_is_cool(url, now=None, database=None) -> bool:
    """A host on the way to this file is cooling.

    Tracker links (podtrac, pdst.fm) reach the CDN named inside the path, and
    the cooldown is keyed by the host that actually died: check them all, or
    the 30-minute skip stops working for every redirected podcast.
    """
    for host in enclosure_hosts(url):
        if __host_is_cool(host, now=now, database=database):
            return True
    return False


def mark_enclosure_host_cool(
        url, error=None, seconds=None, now=None, database=None) -> str | None:
    """Cool the host that hung, not the first hop of the URL.

    urllib3 names it in the message; a redirector (dts.podtrac.com) carries
    dozens of unrelated podcasts and must not be cooled for one dead CDN.
    """
    host = host_from_error(error) or host_from_url(url)
    if not host:
        return None
    __cool_host(host, seconds=seconds, now=now, database=database)
    return host


def __cool_host(host, seconds=None, now=None, database=None):
    wait = COOL_SECONDS if seconds is None else int(seconds)
    stamp = time.time() if now is None else float(now)
    runtime_kv.set_kv(
        __enclosure_cool_key(host), str(stamp + wait), database=database)


def note_enclosure_host_fault(url, error=None, now=None, database=None) -> str | None:
    """A job's enclosure hit a timeout/DNS fault. Returns the host if this cooled it.

    One fault is often a hiccup, so it only counts. FAULTS_BEFORE_COOL faults
    within FAULT_WINDOW_SECONDS cool the host (the one urllib3 names, not the
    redirector in the URL). Cooling leaves the counter primed from the end of
    the cooldown: a host still dead after 30 minutes is cooled again by its
    first failure, not given two more jobs every half hour.
    """
    host = host_from_error(error) or host_from_url(url)
    if not host:
        return None
    stamp = time.time() if now is None else float(now)
    cooled = []

    def count_fault(old):
        first, count = stamp, 0
        if old:
            try:
                old_first, old_count = old.split("|", 1)
                if stamp - float(old_first) <= FAULT_WINDOW_SECONDS:
                    first, count = float(old_first), int(old_count)
            except (TypeError, ValueError):
                pass
        count += 1
        if count < FAULTS_BEFORE_COOL:
            return "%s|%d" % (first, count)
        cooled.append(host)
        return "%s|%d" % (stamp + COOL_SECONDS, FAULTS_BEFORE_COOL - 1)

    runtime_kv.update_kv(
        __enclosure_faults_key(host), count_fault, database=database)
    if not cooled:
        return None
    __cool_host(host, now=stamp, database=database)
    return host


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
        logger.log("Storage closed")
    except Exception as e:
        logger.err("Error closing storage:", e)
