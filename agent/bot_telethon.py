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

thonbot = TelegramClient(
    session_handler, app_id, api_hash).start(bot_token=bot_token)

if os.path.exists(uploader_session):
    with open(uploader_session, 'r') as f:
        string_session = StringSession(f.readline())
else:
    string_session = StringSession()

thonbot_uploader = TelegramClient(string_session, app_id, api_hash).start(bot_token=bot_token)
thobot_session_handler = thonbot_uploader.session.save()

logger = Logger(file="sender")

with open(uploader_session, 'w+') as f:
    f.write(thobot_session_handler)


async def __uploader(local_thonbot, fname, callback=None):
    await local_thonbot.connect()
    if callback is not None:
        file = await local_thonbot.upload_file(fname, progress_callback=callback)  # , part_size_kb=32)
    else:
        file = await local_thonbot.upload_file(fname)
    await local_thonbot.disconnect()

    logger.log("file uploaded")
    return file


def upload(local_thonbot, fname, callback=None):
    try:
        logger.log("uploading file via agent...", datetime.datetime.now())
        file = local_thonbot.loop.run_until_complete(
            __uploader(local_thonbot, fname, callback=callback))
        # loop = asyncio.get_event_loop()
        # future = asyncio.run_coroutine_threadsafe(
        #     uploader(thonbot, fname), loop)
        # file = future.result()
        return file
    except RuntimeError as e:
        logger.log("Runtime error while uploading:", e)
        time.sleep(10)
        return upload(local_thonbot, fname, callback=callback)


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
        # int(transmitter_chat),  # попытка сделать загрузку через другого бота
        file,
        # caption=str(
        #     chat_id + ':!:' + object_id + ':!:' + duration
        #     + ':!:' + file_name
        #     + ':!:' + performer + ':!:' + message_text)[0:1024],
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
    return file_sending_result.media.document.id


def send_uploaded(local_thonbot, data, file):
    try:
        logger.log("sending uploaded...")
        file_id = local_thonbot.loop.run_until_complete(
            sender(local_thonbot, data, file))
        logger.log("STATUS OK")
        return file_id
    except RuntimeError as e:
        logger.log("Runtime error while uploading:", e)
        time.sleep(10)
        return send_uploaded(local_thonbot, data, file)


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
