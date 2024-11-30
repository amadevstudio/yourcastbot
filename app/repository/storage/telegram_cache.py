import json
import shelve
import datetime
from typing import Literal, Any

from config import telegram_cache_shelve_name, use_cache

storage = shelve.open(telegram_cache_shelve_name)
storage.clear()

file_types = Literal['img', 'audio']


def __process_with_expiration(key) -> Any:
    try:
        f = json.loads(storage[key])
    except Exception:
        return None

    if datetime.datetime.fromisoformat(f['exp']) < datetime.datetime.now():
        storage[key] = None
        del storage[key]
        return None

    return f['t']


def __save_with_expiration(key: str, value: Any, expiration_date: datetime.datetime):
    storage[key] = json.dumps({'t': value, 'exp': str(expiration_date)})


def get_file_id(file: str, file_type: file_types):
    if not use_cache:
        return None

    key = f'{file_type}:{file}'
    return __process_with_expiration(key)


def add_file_id(
        file: str, file_id: str, file_type: file_types,
        expiration_date: datetime.datetime = datetime.datetime.now() + datetime.timedelta(days=3)):
    __save_with_expiration(f'{file_type}:{file}', file_id, expiration_date)


def get_cached(unique: str):
    return __process_with_expiration(f'strCache:{unique}')


def add_cache(
        unique: str, value: Any,
        expiration_date: datetime.datetime = datetime.datetime.now() + datetime.timedelta(hours=1)):
    __save_with_expiration(f'strCache:{unique}', value, expiration_date)
