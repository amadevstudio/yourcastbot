import json
import shelve
import datetime
from typing import Literal, Any

from config import telegram_cache_shelve_name, use_cache
from lib.python.file_lock import InterprocessLock
from lib.tools.logger import logger

storage = shelve.open(telegram_cache_shelve_name)
_lock = InterprocessLock(telegram_cache_shelve_name + ".lock")

file_types = Literal['img', 'audio']


def __process_with_expiration(key) -> Any:
    try:
        f = json.loads(storage[key])
    except Exception:
        return None

    if datetime.datetime.fromisoformat(f['exp']) < datetime.datetime.now():
        del storage[key]
        return None

    return f['t']


def __save_with_expiration(key: str, value: Any, expiration_date: datetime.datetime):
    storage[key] = json.dumps({'t': value, 'exp': str(expiration_date)})


def get_file_id(file: str, file_type: file_types):
    if not use_cache:
        return None

    with _lock:
        key = f'{file_type}:{file}'
        return __process_with_expiration(key)


def add_file_id(
        file: str, file_id: str, file_type: file_types,
        expiration_date: datetime.datetime | None = None):
    # Default arguments are evaluated once on import, so the expiration has to be built on every call,
    # otherwise every entry expires at "process start + 3 days" and the cache dies for good
    if expiration_date is None:
        expiration_date = datetime.datetime.now() + datetime.timedelta(days=3)

    with _lock:
        __save_with_expiration(f'{file_type}:{file}', file_id, expiration_date)


def get_cached(unique: str):
    with _lock:
        return __process_with_expiration(f'strCache:{unique}')


def add_cache(
        unique: str, value: Any,
        expiration_date: datetime.datetime | None = None):
    if expiration_date is None:
        expiration_date = datetime.datetime.now() + datetime.timedelta(hours=1)

    with _lock:
        __save_with_expiration(f'strCache:{unique}', value, expiration_date)


def close_storage():
    try:
        storage.sync()
        storage.close()
        logger.log("Telegram cache shelve closed")
    except Exception as e:
        logger.err("Error closing telegram cache shelve:", e)
