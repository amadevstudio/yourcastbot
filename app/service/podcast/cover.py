# -*- coding: utf-8 -*-
"""Podcast covers Telegram cannot fetch.

Telegram downloads a cover from the podcast's own host. Some hosts refuse it
(cdn.mave.digital: 15 times on 2026-10-21), and every open of that page
waited for Telegram's refusal before the buttons came, as a second step.
A refused cover is marked (telegram_cache, 7 days): the page goes out at
once without it. The refusal and, while marked, an open ask for a
background check at most once an hour: the cover is sent to the storage
chat by URL and, if Telegram still refuses the URL, as a file we download
(the same mave cover is a 208 KB JPEG our server gets at once). When it
goes through, its file_id is cached (later pages show it at once) and the
mark goes.

The page itself does not wait for the hour: a refusal, or an open while
marked, uploads the cover as a file we download right then (upload_now, at
most once an hour per cover, so a dead host does not slow every open) and
the page goes with it. Before, the first open of such a show had no picture
and only the next one had it (2026-10-26, a mave cover).
"""
import threading

from app.repository.storage import telegram_cache
from lib.net import public_only
from lib.requests.url import normalize_url
from lib.tools.logger import logger

RECHECK_SECONDS = 3600
MAX_COVER_BYTES = 5 * 1024 * 1024  # a cover, not a file: Telegram takes photos up to 10 MB


def is_url(image) -> bool:
    return isinstance(image, str) and image.startswith(('http://', 'https://'))


def known_unreachable(image) -> bool:
    return is_url(image) and telegram_cache.image_unreachable(image)


def mark_unreachable(image):
    if is_url(image):
        telegram_cache.mark_image_unreachable(image)


def recheck_later(image, check=None):
    """Once an hour per cover, in the background: the page does not wait for it."""
    if not is_url(image) or not telegram_cache.claim_once('coverCheck:' + image, RECHECK_SECONDS):
        return
    threading.Thread(target=check or recheck, args=(image,), name='cover check', daemon=True).start()


def download(image, get=None):
    """The cover's bytes, or None: not an image, too big, or the host does not answer."""
    get = get or public_only.session().get  # a URL a feed named: public addresses only
    try:
        with get(normalize_url(image), timeout=(5, 15), stream=True) as response:
            kind = response.headers.get('Content-Type', '')
            if response.status_code != 200 or not kind.startswith('image/'):
                return None
            content = b''
            for chunk in response.iter_content(64 * 1024):
                content += chunk
                if len(content) > MAX_COVER_BYTES:
                    return None
            return content or None
    except Exception as e:
        logger.warn("cover download:", image, e)
        return None


def _bot_and_chat(bot, storage_chat_id):
    from config import storageChatId
    if bot is None:
        from agent.bot_telebot import bot
    return bot, storageChatId if storage_chat_id is None else storage_chat_id


def _upload(image, bot, chat_id, get):
    """The cover as a file we download, sent to the storage chat; the sent message or None."""
    content = download(image, get)
    try:
        return bot.send_photo(chat_id, content) if content else None
    except Exception as upload_error:
        logger.warn("cover upload:", image, upload_error)
        return None


def upload_now(image, bot=None, storage_chat_id=None, get=None) -> bool:
    """A cover Telegram refuses by URL, uploaded now as a file we download, for a page that waits
    for it: its file_id is cached and the mark goes. At most one try an hour per cover."""
    if not is_url(image) or not telegram_cache.claim_once('coverUpload:' + image, RECHECK_SECONDS):
        return False
    bot, chat_id = _bot_and_chat(bot, storage_chat_id)
    sent = _upload(image, bot, chat_id, get)
    if sent is None:
        return False
    _cache(image, bot, chat_id, sent)
    return True


def recheck(image, bot=None, storage_chat_id=None, get=None):
    from lib.telegram.general.errors import media_fetch_failed
    bot, chat_id = _bot_and_chat(bot, storage_chat_id)
    try:
        sent = bot.send_photo(chat_id, image)
    except Exception as e:
        if not media_fetch_failed(e):
            logger.warn("cover check:", image, e)
            return False
        # Telegram refuses the URL: the host may still give the file to us
        sent = _upload(image, bot, chat_id, get)
        if sent is None:
            telegram_cache.mark_image_unreachable(image)  # still refused: keep the page without it
            return False
    _cache(image, bot, chat_id, sent)
    return True


def _cache(image, bot, chat_id, sent):
    telegram_cache.add_file_id(image, sent.photo[-1].file_id, 'img')
    telegram_cache.clear_image_unreachable(image)
    try:
        bot.delete_message(chat_id, sent.message_id)
    except Exception:
        pass
