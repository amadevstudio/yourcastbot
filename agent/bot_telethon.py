import datetime
import mimetypes
import os
import time

from telethon import Button
from telethon import TelegramClient  # , events
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeAudio

import config
from lib.tools.logger import Logger

session_handler = "telethon_sessions/yourcastbot"
uploader_session = "telethon_sessions/yourcastbot_uploader.session"

app_id = config.app_api_id
api_hash = config.app_api_hash
bot_token = config.token

# Do not connect at import time: MTProto is blocked in some environments
# (Cloud Agent, filtered networks) while Bot API HTTPS still works.
thonbot = TelegramClient(session_handler, app_id, api_hash)
thonbot_uploader: TelegramClient | None = None
thobot_session_handler = ""
telethon_available = False

logger = Logger(file="sender")


def try_start_telethon() -> bool:
    """Connect Telethon clients. Returns False when MTProto is unavailable."""
    global thonbot_uploader, thobot_session_handler, telethon_available

    if telethon_available:
        return True

    if os.environ.get('TELEGRAM_FORCE_BOTAPI', '').lower() in ('1', 'true', 'yes'):
        logger.log("TELEGRAM_FORCE_BOTAPI is set, skipping MTProto")
        return False

    if not bot_token or not app_id or not api_hash:
        logger.log("Telethon credentials missing, skipping MTProto")
        return False

    try:
        thonbot.start(bot_token=bot_token)

        if os.path.exists(uploader_session):
            with open(uploader_session, 'r') as f:
                string_session = StringSession(f.readline())
        else:
            string_session = StringSession()

        uploader = TelegramClient(string_session, app_id, api_hash).start(
            bot_token=bot_token)
        session_string = uploader.session.save()
        with open(uploader_session, 'w+') as f:
            f.write(session_string)

        thonbot_uploader = uploader
        thobot_session_handler = session_string
        telethon_available = True
        logger.log("Telethon MTProto connected")
        return True
    except Exception as e:
        logger.err("Telethon MTProto connect failed:", e)
        return False


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
