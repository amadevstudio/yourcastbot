import datetime
import mimetypes
import os
import time

from telethon import Button
from telethon import TelegramClient  # , events
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeAudio

import config
from lib.python.file_lock import InterprocessLock
from lib.tools.logger import Logger

session_handler = "telethon_sessions/yourcastbot"
uploader_session = "telethon_sessions/yourcastbot_uploader.session"

app_id = config.app_api_id
api_hash = config.app_api_hash
bot_token = config.token

logger = Logger(file="sender")

_thonbot = None
_uploader_session_string = None
_uploader_lock = InterprocessLock(uploader_session + ".lock")


def _role():
    return os.environ.get("YOURCAST_ROLE") or ""


def get_uploader_session_string():
    """StringSession for send workers / updater. Does not open the file session."""
    global _uploader_session_string
    if _uploader_session_string:
        return _uploader_session_string
    with _uploader_lock:
        if _uploader_session_string:
            return _uploader_session_string
        if os.path.exists(uploader_session):
            with open(uploader_session, "r") as f:
                saved = f.readline().strip()
            if saved:
                _uploader_session_string = saved
                return saved
        client = TelegramClient(
            StringSession(), app_id, api_hash).start(bot_token=bot_token)
        saved = client.session.save()
        client.disconnect()
        directory = os.path.dirname(uploader_session)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(uploader_session, "w") as f:
            f.write(saved)
        _uploader_session_string = saved
        return saved


def get_thonbot():
    """Receive client on the SQLite file session. Bot role only."""
    global _thonbot
    role = _role()
    if role and role != "bot":
        raise RuntimeError(
            "file Telethon session is bot-only; role=%s" % role)
    if _thonbot is None:
        _thonbot = TelegramClient(
            session_handler, app_id, api_hash).start(bot_token=bot_token)
    return _thonbot


def __getattr__(name):
    if name == "thobot_session_handler":
        return get_uploader_session_string()
    if name == "thonbot":
        return get_thonbot()
    raise AttributeError(
        "module %r has no attribute %r" % (__name__, name))


async def __uploader(local_thonbot, fname, callback=None):
    await local_thonbot.connect()
    if callback is not None:
        file = await local_thonbot.upload_file(fname, progress_callback=callback)  # , part_size_kb=32)
    else:
        file = await local_thonbot.upload_file(fname)
    await local_thonbot.disconnect()

    logger.log("file uploaded")
    return file


def upload(local_thonbot, fname, callback=None, retries=3):
    try:
        logger.log("uploading file via agent...", datetime.datetime.now())
        file = local_thonbot.loop.run_until_complete(
            __uploader(local_thonbot, fname, callback=callback))
        return file
    except RuntimeError as e:
        if retries <= 0:
            logger.log("Upload retries exhausted:", e)
            raise
        logger.log("Runtime error while uploading, retries left:", retries, e)
        time.sleep(10)
        return upload(local_thonbot, fname, callback=callback, retries=retries - 1)


async def sender(local_thonbot, argv, file):
    file_name = argv['title']
    chat_id = argv['chat_id']
    duration = argv['duration_sec']
    performer = argv['channel_name']
    message_text = argv['message_text']

    mimetypes.add_type('audio/aac', '.aac')
    mimetypes.add_type('audio/ogg', '.ogg')

    await local_thonbot.connect()
    file_sending_result = await local_thonbot.send_file(
        int(chat_id),
        file,
        caption=str(message_text)[0:1024],
        buttons=get_next_ep_button(argv),
        parse_mode='HTML',
        file_name=str(file_name),
        use_cache=False,
        part_size_kb=512,
        attributes=[DocumentAttributeAudio(
            int(duration),
            voice=None,
            title=file_name,
            performer=performer)]
    )
    await local_thonbot.disconnect()

    logger.log("sent in agent")
    # Return message_id and chat_id so the caller can obtain a Bot API file_id
    # via forwardMessage. We cannot return file_sending_result.media.document.id
    # (MTProto document ID) because it is not compatible with Bot API file_id.
    return {
        'message_id': file_sending_result.id,
        'chat_id': int(chat_id),
    }


def send_uploaded(local_thonbot, data, file, retries=3):
    try:
        logger.log("sending uploaded...")
        result = local_thonbot.loop.run_until_complete(
            sender(local_thonbot, data, file))
        logger.log("STATUS OK")
        return result
    except RuntimeError as e:
        if retries <= 0:
            logger.log("Send retries exhausted:", e)
            raise
        logger.log("Runtime error while sending, retries left:", retries, e)
        time.sleep(10)
        return send_uploaded(local_thonbot, data, file, retries=retries - 1)


def get_next_ep_button(argv):
    if 'nextEpButtonText' in argv and 'nextEpButtonData' in argv:
        next_ep_button_text = argv['nextEpButtonText']
        next_ep_button_data = argv['nextEpButtonData']

        keyboard = [
            [
                Button.inline(next_ep_button_text, next_ep_button_data)
            ]
        ]
        return keyboard

    else:
        return None

# def get_or_create_event_loop():
#     try:
#         loop = asyncio.get_event_loop()
#     except RuntimeError:
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#     print("LOOOOP IS ", loop, flush=True)
#     return loop

