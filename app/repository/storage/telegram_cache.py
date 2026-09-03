import json
import shelve
import datetime
from typing import Literal, Any

from config import telegram_cache_shelve_name, use_cache
from lib.python.file_lock import InterprocessLock

# Open/close under flock so bot (long-lived UI) and updater (auto-send)
# never hold gdbm open at the same time.
_lock = InterprocessLock(telegram_cache_shelve_name + ".lock")

file_types = Literal['img', 'audio']


def _with_db(fn):
    def wrapped(*args, **kwargs):
        with _lock:
            db = shelve.open(telegram_cache_shelve_name)
            try:
                return fn(db, *args, **kwargs)
            finally:
                db.close()
    return wrapped


@_with_db
def __process_with_expiration(db, key) -> Any:
    try:
        f = json.loads(db[key])
    except Exception:
        return None

    if datetime.datetime.fromisoformat(f['exp']) < datetime.datetime.now():
        del db[key]
        return None

    return f['t']


@_with_db
def __save_with_expiration(db, key: str, value: Any, expiration_date: datetime.datetime):
    db[key] = json.dumps({'t': value, 'exp': str(expiration_date)})


def get_file_id(file: str, file_type: file_types):
    if not use_cache:
        return None

    key = f'{file_type}:{file}'
    return __process_with_expiration(key)


def add_file_id(
        file: str, file_id: str, file_type: file_types,
        expiration_date: datetime.datetime | None = None):
    # Default arguments are evaluated once on import, so the expiration has to be built on every call,
    # otherwise every entry expires at "process start + 3 days" and the cache dies for good
    if expiration_date is None:
        expiration_date = datetime.datetime.now() + datetime.timedelta(days=3)

    __save_with_expiration(f'{file_type}:{file}', file_id, expiration_date)


def get_cached(unique: str):
    return __process_with_expiration(f'strCache:{unique}')


def add_cache(
        unique: str, value: Any,
        expiration_date: datetime.datetime | None = None):
    if expiration_date is None:
        expiration_date = datetime.datetime.now() + datetime.timedelta(hours=1)

    __save_with_expiration(f'strCache:{unique}', value, expiration_date)


def close_storage():
    # Per-call open/close; nothing long-lived to shut down.
    pass
