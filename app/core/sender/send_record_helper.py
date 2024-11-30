import datetime
import json
import os
import threading
import time
import urllib
from hashlib import sha256
from io import BufferedReader
from typing import Union, Any, Optional, TypedDict, Literal, BinaryIO

from lib.telegram.telebot.types import Message, ApiException, InlineKeyboardButton, InlineKeyboardMarkup, \
    ApiTelegramException

from agent import bot_telethon
from agent.bot_telebot import bot
from app.controller.builders.adminModule import send_message_to_creator
from app.controller.builders.channelModule import bot_removed_from_channel_reaction
from app.controller.types_helpers.recs import rec_callback_data_identifier
from app.i18n.messages import get_message, get_message_rtd, emojiCodes
from app.repository.storage import storage, telegram_cache
from app.service.podcast.podcast import prepare_podcast_update_time
from app.service.record.caption import prepare_message_text
from config import botName, work_dir, maxPodcastDateCallDataHexLen
from lib.markup.cleaner import html_mrkd_cleaner
# from tools.audio_processing import compress_audio
from lib.requests import requesterModule
from lib.system import space
from lib.telegram.general.errors import get_timeout_from_error_client, get_timeout_from_error_bot, bot_blocked_reaction, \
    user_unavailable_error
from lib.telegram.general.message_master import outer_sender, message_editor, message_deleter, message_master, \
    render_messages
from lib.tools.logger import Logger
from tools.audio_processing import compress_audio

headers = requesterModule.STD_REQUEST_HEADERS

requester = requesterModule.Requester()

logger = Logger(file="sender")

MB_NUMBER = 1048576  # 1024 * 1024


def transform_duration(duration):
    if isinstance(duration, int):  # type(duration) is int:
        duration_sec = duration
    else:
        try:
            duration = duration.split(":")
        except Exception:
            duration = []
        duration_sec = 0
        if len(duration) < 4:
            for i in range(len(duration)):
                try:
                    duration_sec = duration_sec * 60 + int(duration[i])
                except Exception:
                    duration_sec = duration_sec * 60
    return duration_sec


def get_file_size_HTTP(link: str) -> int:
    meta = requester.get_headers(link)

    if 'audio' not in meta['Content-Type']:
        logger.log("Can't get file size via headers, trying via pre downloading...")
        meta = requester.get_headers_with_pre_download(link)

    return int(meta.get("Content-Length"))


class OutcomeMessagePauseErrorType(TypedDict):
    timeout: int | None
    createdAt: datetime.datetime | None


class OutcomeMessageErrorType(TypedDict):
    pause: OutcomeMessagePauseErrorType


class OutcomeMessageType(TypedDict, total=False):
    message_id: int
    errors: OutcomeMessageErrorType


DescriptionModeOptions = Literal['default', 'short', 'none']


class ChatParamsType(TypedDict, total=False):
    silent: bool
    dont_set_resend: bool
    based_on_user_id: int
    bot_reference: bool
    show_updated_text: bool
    description_mode: DescriptionModeOptions


class Sender:

    def __init__(self, thonbot, link, chats: dict[int, ChatParamsType], lang_codes_by_utg, bitrates_tg, podcast_info,
                 with_status_message=True):
        # link — link to file
        # chats — users with params
        # lang_codes_by_utg — tg id to language: {123: 'en'}
        # bitrates_tg — tg id to bitrate
        # podcast_info = {
        # 	'id': id,
        # 	'title': title,
        # 	'descr': descr,
        # 	'itunesLink': itunesLink,
        # 	'channelLink': channelLink,
        # 	'chName': chName,
        # 	'pubDate': pubDate,
        # 	'duration_sec': duration_sec,
        # 	'service_name': serice_name,
        #   'service_id': service_id,
        # 	'send_next_ep_button': boolean,
        # 	'recNum': int  # on publication,
        # 	'recordUniqId': string
        # }

        self.work_dir = work_dir
        self.logger = logger
        self.cache_expiration_date = datetime.datetime.now() + datetime.timedelta(days=30)

        self.thonbot = thonbot
        self.bot = bot
        self.link = urllib.parse.unquote(link)
        self.chats = chats
        self.blocked_chats: list[int] = []
        self.lang_codes_by_utg = lang_codes_by_utg
        self.bitrates_tg = bitrates_tg
        self.podcast_info = podcast_info
        self.withStatusMessage = with_status_message

        self.successfully_sent_to = []
        self.outcome_messages: dict[int, OutcomeMessageType] = {}
        self.bitrates = {}
        self.send_attempts = {}
        self.fname = ''
        self.cached_file_id: int | None = None
        self.recordSize: int | None = None
        self.recordSizeMb: float = 51  # will be downloaded and sent via agent by default
        self.compressed_file_size_mb = None
        self.percent_step = 9
        self.last_download_percent = [0]  # using pointers
        self.last_upload_percent = [0]  # using pointers
        self.statusTemplate = ""

        self.__too_big_record = False

        self.prepare()

        self.sendProgressLast: None | datetime.datetime = None
        self.sendProgressLastMutex = threading.Lock()

    def prepare(self):
        self.logger.log("Start sending: ", datetime.datetime.now())

        for chat_id in self.chats:
            if not self.__chat_is_silent(chat_id) and self.withStatusMessage:
                self.outcome_messages[chat_id] = {}
                send_result = outer_sender(chat_id, [{
                    'type': 'text', 'text': get_message("needTimeToLoad", self.lang_codes_by_utg[chat_id])}])
                if len(send_result) > 0:
                    self.outcome_messages[chat_id]['message_id'] = send_result[-1]['id']
                self.outcome_messages[chat_id]['errors'] = {
                    'pause': {
                        'timeout': None,
                        'createdAt': None
                    }
                }

            self.send_attempts[chat_id] = 0

            bitrate = self.bitrates_tg[chat_id]
            if bitrate not in self.bitrates:
                self.bitrates[bitrate] = []
            self.bitrates[bitrate].append(chat_id)
        self.bitrates = {k: v for k, v in reversed(sorted(self.bitrates.items()))}

        self.__update_status_message("getting_file_size")

        try:
            self.recordSize = get_file_size_HTTP(self.link)
            self.recordSizeMb = self.recordSize / MB_NUMBER
            self.__set_percent_step_dynamic()
        except Exception as e:
            self.logger.warn(e)

        self.__prepare_status_template()

        # Статистика по размеру диска, размеру файла и оперативке + то процессов
        try:
            self.logger.log("Memory stat:\n", space.memory_stat())
            self.logger.log("Top processes:\n", space.top())
            self.logger.log("File size (mb): ", self.recordSizeMb)
            self.logger.log("Disk stat:\n", space.storage_stat())
        except Exception as e:
            self.logger.warn(e)

        # Printing takes too long
        # # Потребление памяти
        # if server:
        #     logger.log("Internal memory usage (obj, number, mem):\n", debug.memory_usage('pympler'))
        #     logger.log("Internal memory usage:\n", debug.memory_usage('tracemalloc'))
        #     # compare_to, traceback.format, get_traced_memory

    def __chat_is_silent(self, chat_id):
        if 'silent' not in self.chats[chat_id] \
                or self.chats[chat_id]['silent'] is False:
            return False
        else:
            return True

    # Переслать следующую команду бота, если это не канал (там отключены команды, ставится флаг dont_set_resend)
    def __set_resend_status(self, chat_id: int):
        if 'dont_set_resend' not in self.chats[chat_id] \
                or self.chats[chat_id]['dont_set_resend'] is False:
            try:
                storage.set_user_resend_flag(chat_id)
            except Exception as e:
                self.logger.err(e)

    def __description_mode(self, chat_id) -> DescriptionModeOptions:
        available_modes: list[DescriptionModeOptions] = ['default', 'short', 'none']
        if self.chats[chat_id].get('description_mode', None) in available_modes:
            return self.chats[chat_id]['description_mode']
        else:
            return 'default'

    def __make_update_status_message(self, chat_id, status):
        if self.outcome_messages[chat_id].get('message_id') is not None:
            # Limits
            if hasattr(self, 'sendProgressLast') and self.sendProgressLast is not None:
                self.sendProgressLastMutex.acquire()
                while datetime.timedelta(seconds=1) + self.sendProgressLast > datetime.datetime.now():
                    time.sleep(1)
                self.sendProgressLastMutex.release()
            self.sendProgressLast = datetime.datetime.now()

            message_editor(
                chat_id, {'type': 'text', 'text': status},
                self.outcome_messages[chat_id]['message_id'])

    def __make_update_status_message_excepted(self, chat_id, status):
        if status is None or status == '':
            return

        try:
            if self.__message_not_paused(chat_id):
                self.__make_update_status_message(chat_id, status)
        except Exception as e:
            timeout = get_timeout_from_error_bot(e)
            if timeout:
                self.__set_status_message_pause(chat_id, timeout)
                return

            self.logger.err(e, status)

    def __set_status_message_pause(self, chat_id, timeout):
        self.outcome_messages[chat_id]['errors']['pause']['timeout'] = timeout
        self.outcome_messages[chat_id]['errors']['pause']['createdAt'] = datetime.datetime.now()

    def __message_not_paused(self, chat_id):
        if self.outcome_messages[chat_id]['errors']['pause']['timeout'] is None \
                or self.outcome_messages[chat_id]['errors']['pause']['createdAt'] is None:
            return True

        can_be_sent_after = datetime.timedelta(
            seconds=self.outcome_messages[chat_id]['errors']['pause']['timeout']
        ) + self.outcome_messages[chat_id]['errors']['pause']['createdAt']

        if can_be_sent_after > datetime.datetime.now():
            return False

        self.outcome_messages[chat_id]['errors']['pause']['timeout'] = None
        self.outcome_messages[chat_id]['errors']['pause']['createdAt'] = None
        return True

    def __update_status_message(self, status, additional=None):
        if not self.withStatusMessage:
            return

        once_statuses = ["compressing"]
        once_condition = status in once_statuses or (status == "uploading_to_telegram_servers" and additional is None)

        for chat_id in self.chats:
            if self.__chat_is_silent(chat_id):
                continue

            status = self.statusTemplate + get_message_rtd(["file_processing", status], self.lang_codes_by_utg[chat_id])
            if additional is not None:
                if 'percent' in additional:
                    status += f": {additional['percent']}%"

            try:
                if once_condition:
                    self.__make_update_status_message(chat_id, status)

                else:
                    write_thread = threading.Thread(
                        target=self.__make_update_status_message_excepted,
                        args=(chat_id, status,))
                    write_thread.start()
            except Exception as e:
                self.logger.warn(f"Can't set status {status} with error:")
                self.logger.err(e)

    def __delete_status_messages(self):
        if not self.withStatusMessage:
            return

        for chat_id in self.chats:
            if self.__chat_is_silent(chat_id):
                continue

            try:
                if self.outcome_messages[chat_id].get('message_id', None) is not None:
                    message_deleter(chat_id, self.outcome_messages[chat_id]['message_id'])
            except Exception as e:
                self.logger.err(e)

    def get_cant_send_to(self, successfully_via_link: list[int]) -> list[int]:
        return [
            chat_id
            for chat_id in self.chats
            if chat_id not in successfully_via_link and chat_id not in self.blocked_chats]

    def send_record(self):
        self.logger.log(f"Begin sending {self.link} to {','.join(map(str, self.chats.keys()))}")

        try:

            # iTunes
            if self.podcast_info['service_name'] == 'itunes':
                if self.recordSizeMb > 2000:
                    self.__too_big_record = True

                elif self.recordSizeMb > 20:
                    self.fname = self.specify_file()
                    self.download_file()

                    if self.recordSizeMb > 50:
                        successfully_via_download = self.send_via_agent()
                    else:
                        successfully_via_download = self.send()

                    self.successfully_sent_to.extend(successfully_via_download)

                else:
                    try:
                        successfully_via_link = self.send_via_link()
                        self.successfully_sent_to.extend(successfully_via_link)

                        cant_sent_to = self.get_cant_send_to(successfully_via_link)

                        if cant_sent_to:
                            self.fname = self.specify_file()
                            self.download_file()

                            successfully_via_download = self.send(cant_sent_to)
                            self.successfully_sent_to.extend(successfully_via_download)

                            cant_sent_to = self.get_cant_send_to(successfully_via_download)
                            if cant_sent_to:
                                successfully_via_download = self.send_via_agent(cant_sent_to)
                                self.successfully_sent_to.extend(successfully_via_download)

                    except Exception as e:
                        self.logger.err(e)

            # RSS
            elif self.podcast_info['service_name'] == 'rss':
                if self.recordSizeMb > 20:
                    self.__too_big_record = True

                else:
                    successfully_via_link = self.send_via_link()
                    try:
                        self.successfully_sent_to.extend(successfully_via_link)
                    except Exception as e:
                        self.logger.err(e)

        # All services error
        except Exception as e:
            self.logger.err(e)

        # Удаляем файл
        try:
            if self.fname is not None and self.fname != '':
                os.remove(self.fname)
        except Exception as e:
            self.logger.err(e, f"Can't delete file #{self.fname}")

        self.__delete_status_messages()

        # Отвечаем, если и кому не получилось отправить
        try:
            if self.__too_big_record:
                self.__send_too_big_record()

            else:
                for chat_id in self.chats:
                    if chat_id not in self.successfully_sent_to:
                        self.__send_record_unavailable(targets=[chat_id])
        except Exception as e:
            self.logger.warn(e)

        self.logger.log("Exit sending: ", datetime.datetime.now(), "\n\n\n")

        return self.successfully_sent_to

    def __get_annex(self):
        if self.recordSizeMb > 50:
            return "l"
        elif self.recordSizeMb > 20:
            return "m"
        else:
            return "s"

    def specify_file(self):
        uniq = len(self.chats)
        annex = f"_{self.__get_annex()}"

        fname = (
                self.work_dir + "/records/r" + str(uniq)
                + "_" + str(int(time.time() * 10000000)) + annex + ".mp3")
        file = open(fname, "w")
        file.close()
        return fname

    def __set_percent_step_dynamic(self):
        if self.recordSizeMb < 20:
            self.percent_step = 19
        elif self.recordSizeMb < 30:
            self.percent_step = 12
        elif self.recordSizeMb < 40:
            self.percent_step = 8
        elif self.recordSizeMb < 100:
            self.percent_step = 5
        else:
            self.percent_step = 2

    def __file_progress(self, mode, done, size: int | None):
        if mode not in ["up", "down"]:
            return

        last_percent: list[int] = [0]
        text = ""

        if mode == "up":
            # Если запись маленькая, прогресс не нужен
            if self.compressed_file_size_mb is not None and self.compressed_file_size_mb < 20 \
                    or (self.compressed_file_size_mb is None and self.recordSizeMb < 20):
                return

            text = "uploading_to_telegram_servers"
            last_percent = self.last_upload_percent
        elif mode == "down":
            text = "downloading"
            last_percent = self.last_download_percent

        if size is not None:
            current_progress = round(done / size * 100)
            if (current_progress > last_percent[0] + self.percent_step) \
                    and current_progress <= (100 - self.percent_step):
                last_percent[0] += self.percent_step  # using pointer
                self.__update_status_message(text, {'percent': current_progress})

            elif current_progress > (100 - self.percent_step):
                last_percent[0] = 100  # using pointer

    def __download_file_callback(self, downloaded, size):
        self.__file_progress("down", downloaded, size)

    def __upload_file_callback(self, uploaded, size):
        self.__file_progress("up", uploaded, size)

    def download_file(self):
        cached_file_id = telegram_cache.get_file_id(self.link, 'audio')
        if cached_file_id is not None:
            self.cached_file_id = cached_file_id
            return

        self.__update_status_message("downloading")
        requester.download_chunked(
            self.link, self.fname, chunk_size=32769,  # 1024 * 32
            # callback=partial(self.__download_file_callback, self))
            callback=self.__download_file_callback)

    def send_via_agent(self, specific_chat_ids: Optional[list[int]] = None):
        chats = self.chats
        bitrates = self.bitrates

        successfully_sent_to = []

        for bitrate in bitrates:
            # TODO: Compressing feature (need more servers)
            if bitrate is not None:
                self.__update_status_message("compressing")
                fname = compress_audio(self.fname, bitrate)
                self.compressed_file_size_mb = os.path.getsize(fname) / MB_NUMBER
                self.__prepare_status_template()
                self.__update_status_message("uploading_to_telegram_servers")
                file = bot_telethon.upload(self.thonbot, fname, callback=self.__upload_file_callback)
            else:
                if self.cached_file_id is not None:
                    file = self.cached_file_id
                else:
                    self.__update_status_message("uploading_to_telegram_servers")
                    file = bot_telethon.upload(self.thonbot, self.fname, callback=self.__upload_file_callback)

            message_info = {
                'title': self.podcast_info['title'],
                'chat_id': 0,
                'file_id': 'fileid',
                'bot_name': botName,
                'duration_sec': self.podcast_info['duration_sec'],
                'channel_name': self.podcast_info['chName'],
                'message_text': ''
            }

            for chat_id in bitrates[bitrate]:
                # If specific id passed, ignore another ids
                if specific_chat_ids is not None and chat_id not in specific_chat_ids:
                    continue

                if chat_id not in chats:
                    continue

                record_message_text = self.prepare_record_text(chat_id, mode=self.__description_mode(chat_id))
                record_message_text = record_message_text.replace('*', '**')

                message_info['message_text'] = record_message_text
                message_info['chat_id'] = chat_id

                if self.podcast_info['with_next_ep_button']:
                    message_info['nextEpButtonText'] = get_message(
                        "loadNextRecord", self.lang_codes_by_utg[chat_id])
                    message_info['nextEpButtonData'] = self.get_button_data()

                def send_uploaded():
                    if self.cached_file_id is not None:
                        new_file_id = self.send_audio(
                            chat_id,
                            file,
                            record_message_text)
                    else:
                        new_file_id = bot_telethon.send_uploaded(self.thonbot, message_info, file)

                    if new_file_id is not None:
                        telegram_cache.add_file_id(self.link, new_file_id, 'audio',
                                                   self.cache_expiration_date)

                    successfully_sent_to.append(chat_id)
                    self.logger.log(chat_id, "success_l ", str(self.podcast_info['id']))
                    self.__set_resend_status(chat_id)

                try:
                    send_uploaded()

                except (ApiException, ValueError, ApiTelegramException) as e:
                    self.logger.err(e)
                    self.print_failure_message_stack(chat_id)

                    if self.error_reactions(e, chat_id):
                        continue

                    # для юзера, если много отправлений, пытаемся ещё раз
                    pause = get_timeout_from_error_client(e)
                    if pause:
                        send_uploaded()

                except Exception as e:
                    self.logger.err(e)
                    self.print_failure_message_stack(chat_id)

        return successfully_sent_to

    def send(self, specific_chat_ids: Optional[list[int]] = None):
        bitrates = self.bitrates

        self.__update_status_message("uploading_to_telegram_servers")

        successfully_sent_to = []

        for bitrate in bitrates:
            file_id: Optional[str] = None
            for chat_id in bitrates[bitrate]:

                # If specific id passed, ignore another ids
                if specific_chat_ids is not None and chat_id not in specific_chat_ids:
                    continue

                file: int | BinaryIO
                if self.cached_file_id is not None:
                    file = self.cached_file_id
                else:
                    file = open(self.fname, 'rb')

                try:
                    record_message_text = self.prepare_record_text(chat_id, mode=self.__description_mode(chat_id))
                    try:
                        new_file_id = self.send_audio(
                            chat_id,
                            file if file_id is None else file_id,
                            record_message_text)

                        if file_id is None and new_file_id is not None:
                            telegram_cache.add_file_id(self.link, new_file_id, 'audio',
                                                       self.cache_expiration_date)
                            file_id = new_file_id

                        successfully_sent_to.append(chat_id)
                        self.logger.log(chat_id, "success_m ", str(self.podcast_info['id']))
                        self.__set_resend_status(chat_id)

                    except (ApiException, ApiTelegramException) as e:
                        self.logger.err(e, f"File id is {file_id}")
                        self.print_failure_message_stack(chat_id)

                        if self.error_reactions(e, chat_id):
                            continue

                        # попытка 2, если проблема в паузе
                        pause = get_timeout_from_error_bot(e)
                        if pause:
                            time.sleep(pause)
                            try:
                                new_file_id = self.send_audio(
                                    chat_id,
                                    file if file_id is None else file_id,
                                    record_message_text)

                                if file_id is None:
                                    file_id = new_file_id

                                successfully_sent_to.append(chat_id)
                                self.logger.log(chat_id, "success_m ", str(self.podcast_info['id']))
                                self.__set_resend_status(chat_id)
                            except Exception as e:
                                self.logger.err(e)

                    except Exception as e:
                        self.logger.err(e)
                        self.print_failure_message_stack(chat_id)
                finally:
                    if type(file) is BufferedReader:
                        file.close()

        return successfully_sent_to

    def send_via_link(self):
        successfully_sent_to = []
        chats = self.chats

        for chat_id in chats:
            record_message_text = self.prepare_record_text(chat_id, mode=self.__description_mode(chat_id))
            try:
                self.send_audio(chat_id, self.link, record_message_text)
                successfully_sent_to.append(chat_id)
                self.logger.log(chat_id, "success_s ", str(self.podcast_info['id']))
                self.__set_resend_status(chat_id)

            except (ApiException, ApiTelegramException) as e:
                self.logger.err(e)
                self.print_failure_message_stack(chat_id)

                if self.error_reactions(e, chat_id):
                    continue

                # попытка 2, если проблема в паузе
                pause = get_timeout_from_error_bot(e)
                if pause:
                    time.sleep(pause)
                    try:
                        self.send_audio(chat_id, self.link, record_message_text)
                        successfully_sent_to.append(chat_id)
                        self.logger.log(chat_id, "success_s ", str(self.podcast_info['id']))
                        self.__set_resend_status(chat_id)
                    except Exception as e:
                        self.logger.err(e)

            except Exception as e:
                self.logger.err(e)

        return successfully_sent_to

    def send_audio(self, chat_id: int, audio: Union[Any, str], record_message_text: str) -> str | None:
        """
        Sends audio by id, file or link
        :raises Exception

        :param chat_id:
        :param audio:
        :param record_message_text:
        :return: File id or None
        """
        # audio with caption
        message: Message
        try:
            message = self.bot.send_audio(
                chat_id=chat_id, audio=audio,
                duration=self.podcast_info['duration_sec'],
                performer=self.podcast_info['chName'], title=self.podcast_info['title'],
                caption=record_message_text,
                parse_mode="HTML",
                reply_markup=self.get_next_ep_button(lang_code=self.lang_codes_by_utg[chat_id]))

        # audio + message
        except Exception as e:  # telebot.apihelper.ApiTelegramException, ?
            if user_unavailable_error(e):
                raise e

            self.logger.err(e, "Fail to send with caption")
            message = self.bot.send_audio(
                chat_id=chat_id, audio=audio,
                duration=self.podcast_info['duration_sec'],
                performer=self.podcast_info['chName'], title=self.podcast_info['title'])
            try:
                self.bot.send_message(
                    chat_id=chat_id,
                    text=record_message_text,
                    parse_mode="HTML",
                    reply_markup=self.get_next_ep_button(
                        lang_code=self.lang_codes_by_utg[chat_id]))
            except Exception as e:
                self.logger.err(e, "Fail to send caption, but success record")
                self.logger.log(record_message_text)

        if message.audio is None:
            return None

        return message.audio.file_id

    def __send_too_big_record(self, targets=None):
        if targets is None:
            targets = self.chats

        for chat_id in targets:
            if not self.__chat_is_silent(chat_id):
                try:
                    self.__too_big_record_sender(chat_id)
                except ApiException as e:
                    self.error_reactions(e, chat_id)

    def __too_big_record_sender(self, chat_id):
        lang_code = self.lang_codes_by_utg[chat_id]
        outcome_message_id = self.outcome_messages[chat_id].get('message_id', None)

        message_text = self.prepare_record_text(
            chat_id, mode='short', on_error=True) + "\n\n" + get_message(
            "tooBigRecord", lang_code) % self.link

        if self.podcast_info['itunesLink'] != '':
            message_text += get_message(
                "tooBigRecord2", lang_code).lower() % self.podcast_info['itunesLink']

        if self.podcast_info['itunesLink'] != '':
            message_text += get_message(
                "tooBigRecord3", lang_code).lower() % self.podcast_info['channelLink']

        if outcome_message_id is not None:
            try:
                message_editor(
                    chat_id, {'type': 'text', 'text': message_text}, old_message_id=outcome_message_id)
            except Exception as e:
                render_messages(chat_id, [{'type': 'text', 'text': message_text}])
                logger.err(e)
            return

        else:
            logger.warn("outcome_message_id is None")
            render_messages(chat_id, [{'type': 'text', 'text': message_text}])

    def __send_record_unavailable(self, targets=None):
        if targets is None:
            targets = self.chats

        for chat_id in targets:
            if not self.__chat_is_silent(chat_id):
                try:
                    self.__record_unavailable(chat_id)
                except ApiException as e:
                    self.error_reactions(e, chat_id)

    def __record_unavailable(self, chat_id):
        lang_code = self.lang_codes_by_utg[chat_id]

        if str(type(self.link)) == "# <class 'str'>" or not isinstance(self.link, str):
            send_message_to_creator("lxml.etree._Element ERROR!!!!!!!!!\n\n" +
                str(chat_id) + str(self.podcast_info['title'])
                + str(lang_code) + str(self.podcast_info['channelLink']) + "\n\n" + str(self.link))

        error_text = (
                self.prepare_record_text(chat_id, mode='short', on_error=True) + "\n\n"
                + get_message("recordUnavaliable", lang_code) % self.podcast_info['channelLink'] + "\n"
                + get_message("recordUnavaliable2", lang_code) % str(self.link))

        try:
            self.__make_update_status_message(chat_id, error_text)
        except Exception:
            outer_sender(chat_id, [{'type': 'text', 'text': error_text}])

        self.logger.warn("Unavailable: ", str(self.link))

    def print_failure_message_stack(self, chat_id, attempt=1):

        self.logger.warn(f"Failure_{attempt}, chat_id: {chat_id}, reason_{self.__get_annex()}")
        self.logger.warn(
            "Podcast id: ", str(self.podcast_info['id']),
            "Link to record: ", str(self.link).encode('utf-8'),
            # "Record title: ", str(self.podcast_info['title']).encode('utf-8'),
        )
        # print(prepare_record_text(self.podcast_info, 'ru').encode('utf-8'), flush=True)

    def __prepare_status_template(self):
        self.statusTemplate = self.podcast_info['chName'] + "\n" + \
                              "<b>" + self.podcast_info['title'] + "</b>\n\n" + \
                              emojiCodes.get('floppyDisk') + " " + str(round(self.recordSizeMb, 2)) + " MiB" + \
                              ("\n" if self.compressed_file_size_mb is None
                               else f" -> {round(self.compressed_file_size_mb, 2)} MiB\n")

    def prepare_record_text(self, chat_id, mode: DescriptionModeOptions = 'default', on_error=False):

        lang_code = self.lang_codes_by_utg[chat_id]
        chat = self.chats[chat_id]

        # base message
        message = self.record_text_template(
            lang_code, mode, self.podcast_info['channelLink'], self.podcast_info['chName'],
            self.podcast_info['title'], self.podcast_info['id'],
            self.podcast_info['pubDate'], self.podcast_info['descr'],
            self.podcast_info['service_name'], self.podcast_info['service_id'],
            on_error=on_error,
            show_updated_text=('show_updated_text' not in chat or chat['show_updated_text'] is True),
            bot_reference=('bot_reference' not in chat or chat['bot_reference'] is True))

        return message

    # modes: default, short
    @staticmethod
    def record_text_template(
            lang_code, mode: DescriptionModeOptions,
            channel_link, ch_name, title, channel_id, pub_date, descr, service_name, service_id,
            on_error=False, show_updated_text=True, bot_reference=True, bot_reference_botname=True):
        message = ""
        if channel_link:
            message += "<a href=\"" + channel_link + "\">" \
                       + ch_name + "</a>"
        else:
            message += "<b>" + ch_name + "</b>"

        message += "\n<b>" + title

        if channel_id is not None:
            message += " #id" + str(channel_id) + "\n"
        else:
            message += "\n"

        pub_date = prepare_podcast_update_time(pub_date)

        if not on_error and show_updated_text:
            message += get_message("uploaded", lang_code) + " "
        message += pub_date + "</b>\n\n"

        # ссылка на бота + ссылка на подкаст в боте
        if not on_error and bot_reference:
            try:
                channel_id = int(channel_id)
                if channel_id < 1 and channel_id is not None:
                    channel_id = None
            except Exception:
                channel_id = None
            if channel_id is not None or (service_name == "itunes" and service_id):
                if channel_id is not None:
                    message += get_message(
                        "linkInTheBotByPodcastId_HTML", lang_code).format(
                        botName=botName, id=channel_id, mode="podcast")
                elif service_name == "itunes" and service_id:
                    message += get_message(
                        "linkInTheBotByPodcastId_HTML", lang_code).format(
                        botName=botName, id=service_id, mode="podcastItunes")
                if bot_reference_botname:
                    message += " " + get_message("in_the_bot", lang_code).format(botName=botName)
                message += "\n\n"
            elif bot_reference_botname:
                message += f"@{botName}" + "\n\n"

        if mode != 'none':
            message += html_mrkd_cleaner(descr)

        # default have description and longer
        if mode == 'default':
            max_characters = 1000
        elif mode == 'short' or mode == 'none':
            max_characters = 500
        else:
            max_characters = 1000

        # get rid of the last clipped sentence
        message = prepare_message_text(
            message, max_length=max_characters, clear_markup=False, parse_mode="HTML")

        return message

    def get_next_ep_button(self, lang_code='en'):
        if self.podcast_info['with_next_ep_button']:
            keyboard = InlineKeyboardMarkup()

            b1 = InlineKeyboardButton(
                text=get_message("loadNextRecord", lang_code),
                callback_data=self.get_button_data())
            keyboard.add(b1)

            return keyboard

        else:
            return None

    def get_button_data(self):
        dh = sha256(
            self.podcast_info['recordUniqId'].encode('utf-8')).hexdigest()[0:maxPodcastDateCallDataHexLen]
        return json.dumps(
            rec_callback_data_identifier(
                self.podcast_info['id'], self.podcast_info['service_id'], self.podcast_info['service_name'],
                dh, self.podcast_info['recNum'], True))

    def error_reactions(self, error, error_chat_id):
        user_blocked = bot_blocked_reaction(error, error_chat_id)
        channel_blocked = bot_removed_from_channel_reaction(error, error_chat_id)

        if user_blocked or channel_blocked:
            self.blocked_chats.append(error_chat_id)

        return user_blocked or channel_blocked
