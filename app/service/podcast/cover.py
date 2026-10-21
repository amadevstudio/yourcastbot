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
"""
import threading

import requests

from app.repository.storage import telegram_cache
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
    get = get or requests.get
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


def recheck(image, bot=None, storage_chat_id=None, get=None):
    from config import storageChatId
    from lib.telegram.general.errors import media_fetch_failed
    if bot is None:
        from agent.bot_telebot import bot
    chat_id = storageChatId if storage_chat_id is None else storage_chat_id
    try:
        sent = bot.send_photo(chat_id, image)
    except Exception as e:
        if not media_fetch_failed(e):
            logger.warn("cover check:", image, e)
            return False
        # Telegram refuses the URL: the host may still give the file to us
        content = download(image, get)
        try:
            sent = bot.send_photo(chat_id, content) if content else None
        except Exception as upload_error:
            logger.warn("cover upload:", image, upload_error)
            sent = None
        if sent is None:
            telegram_cache.mark_image_unreachable(image)  # still refused: keep the page without it
            return False
    telegram_cache.add_file_id(image, sent.photo[-1].file_id, 'img')
    telegram_cache.clear_image_unreachable(image)
    try:
        bot.delete_message(chat_id, sent.message_id)
    except Exception:
        pass
    return True
