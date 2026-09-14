import datetime
import json
import os
import threading
import time
from hashlib import sha256
from typing import Union, Any, TypedDict

from lib.telegram.telebot.types import Message, ApiException, InlineKeyboardButton, InlineKeyboardMarkup

from agent import bot_telethon
from agent.bot_telebot import bot
from app.controller.builders.adminModule import send_message_to_creator
from app.controller.builders.channelModule import bot_removed_from_channel_reaction
from app.controller.types_helpers.recs import rec_callback_data_identifier
from app.core.sender import outbox
from app.i18n.messages import (
    get_message, get_message_rtd, emojiCodes, format_record_unavailable)
from app.repository.storage import storage, telegram_cache
from app.service.record.caption import DescriptionModeOptions, record_caption
from app.service.record.delivery import Upload, fetch_by_url_first, upload_order
from config import botName, creatorId, storageChatId, work_dir, maxPodcastDateCallDataHexLen, db_path
from lib.markup import telegram_html
# from tools.audio_processing import compress_audio
from lib.requests import requesterModule
from lib.system import space
from lib.system.disk_budget import BudgetedDownload, DiskBudget, DiskBusy, DiskTooSmall
from lib.telegram import limits
from lib.net.enclosure import enclosure_host_fault
from lib.telegram.general.errors import get_timeout_from_error_client, get_timeout_from_error_bot, bot_blocked_reaction, \
    user_unavailable_error, message_to_edit_not_found, audio_source_gone, request_entity_too_large, log_caught, \
    entities_parse_error, file_refused
from lib.telegram.general.message_master import outer_sender, message_editor, message_deleter, message_master, \
    render_messages
from lib.tools.logger import Logger
from tools.audio_processing import compress_audio

headers = requesterModule.STD_REQUEST_HEADERS

# No urllib3 retries: a hung CDN must fail this attempt and free the rec
# slot. Outbox fail_or_retry already backs off the row; newest clicks are
# claimed first. Default Retry(total=10) * download timeout occupied all
# four rec workers for tens of minutes (firstory HEAD/read).
requester = requesterModule.Requester(attempts=0, total_attempts=0)

logger = Logger(file="sender")

MB_NUMBER = 1048576  # 1024 * 1024

# One per bot process: every rec and circle worker thread reserves from it.
disk_budget = DiskBudget(os.path.join(work_dir, "records"))


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
    content_type = meta.get('Content-Type') or ''
    content_length = meta.get('Content-Length')

    # HEAD often has no Content-Length (chunked / some CDNs). int(None) used to
    # blow up here and the caller silently kept the 51 MB default.
    if 'audio' not in content_type or not content_length:
        logger.log("Can't get file size via headers, trying via pre downloading...")
        meta = requester.get_headers_with_pre_download(link)
        content_length = meta.get('Content-Length')

    if not content_length:
        raise ValueError("Content-Length is missing")
    return int(content_length)


class OutcomeMessagePauseErrorType(TypedDict):
    timeout: int | None
    createdAt: datetime.datetime | None


class OutcomeMessageErrorType(TypedDict):
    pause: OutcomeMessagePauseErrorType


class OutcomeMessageType(TypedDict, total=False):
    message_id: int
    errors: OutcomeMessageErrorType


class ChatParamsType(TypedDict, total=False):
    silent: bool
    dont_set_resend: bool
    based_on_user_id: int
    bot_reference: bool
    show_updated_text: bool
    description_mode: DescriptionModeOptions


class Sender:

    def __init__(self, thonbot, link, chats: dict[int, ChatParamsType], lang_codes_by_utg, bitrates_tg, podcast_info,
                 with_status_message=True, consume_notify=False,
                 outbox_id=None, outbox_attempts=None):
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
        self.link = link
        self.chats = chats
        self.blocked_chats: list[int] = []
        self.lang_codes_by_utg = lang_codes_by_utg
        self.bitrates_tg = bitrates_tg
        self.podcast_info = podcast_info
        self.withStatusMessage = with_status_message
        self.consume_notify = bool(consume_notify)
        self.outbox_id = outbox_id
        self.outbox_attempts = outbox_attempts
        self._last_outbox_touch = None
        self._quota_charged = set()

        self.successfully_sent_to = []
        self.outcome_messages: dict[int, OutcomeMessageType] = {}
        self.bitrates = {}
        self.send_attempts = {}
        self._file: BudgetedDownload | None = None
        self.cached_file_id: str | None = None
        self.recordSize: int | None = None
        self.recordSizeMb: float = 51  # will be downloaded and sent via agent by default
        self.compressed_file_size_mb = None
        self.percent_step = 9
        self.last_download_percent = [0]  # using pointers
        self.last_upload_percent = [0]  # using pointers
        self.statusTemplate = ""

        self.__too_big_record = False
        self.__record_gone = False

        self.prepare()

        self.sendProgressLast: None | datetime.datetime = None
        self.sendProgressLastMutex = threading.Lock()

    def prepare(self):
        self.logger.log("Start sending: ", datetime.datetime.now())

        for chat_id in self.chats:
            self.outcome_messages.setdefault(chat_id, {})
            if not self.__chat_is_silent(chat_id) and self.withStatusMessage:
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
            if storage.enclosure_host_is_cool(self.link):
                self.logger.warn("enclosure host cooling, skip size check")
            else:
                self.recordSize = get_file_size_HTTP(self.link)
                self.recordSizeMb = self.recordSize / MB_NUMBER
                self.__set_percent_step_dynamic()
        except Exception as e:
            log_caught(self.logger, error=e)
            if enclosure_host_fault(e):
                storage.mark_enclosure_host_cool(self.link)

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

    def _touch_outbox(self):
        if self.outbox_id is None:
            return
        now = datetime.datetime.now()
        if self._last_outbox_touch is not None:
            elapsed = (now - self._last_outbox_touch).total_seconds()
            if elapsed < outbox.TOUCH_MIN_INTERVAL_SECONDS:
                return
        self._last_outbox_touch = now
        try:
            outbox.touch(self.outbox_id, attempts=self.outbox_attempts)
        except Exception as e:
            self.logger.err("outbox touch:", e)

    def _sleep_or_release_flood(self, error):
        """Without an outbox id, sleep. A queued rec job releases the lease."""
        pause = get_timeout_from_error_bot(error)
        if not pause:
            pause = get_timeout_from_error_client(error)
        if not pause:
            return False
        if self.outbox_id is not None:
            raise outbox.OutboxRetryableError(error)
        time.sleep(pause)
        return True

    def _remaining_chats(self):
        remaining = {}
        for chat_id, params in self.chats.items():
            if chat_id in self.successfully_sent_to:
                continue
            if chat_id in self.blocked_chats:
                continue
            remaining[chat_id] = params
        return remaining

    def _sync_outbox_recipients(self):
        """Drop delivered chats from the payload, then charge notify_count."""
        remaining = self._remaining_chats()
        persisted = self.outbox_id is None
        if self.outbox_id is not None:
            remaining_langs = {
                chat_id: self.lang_codes_by_utg[chat_id]
                for chat_id in remaining
                if chat_id in self.lang_codes_by_utg
            }
            remaining_bitrates = {
                chat_id: self.bitrates_tg[chat_id]
                for chat_id in remaining
                if chat_id in self.bitrates_tg
            }
            try:
                persisted = outbox.update_rec_recipients(
                    self.outbox_id, remaining,
                    utglangs=remaining_langs, bitratestg=remaining_bitrates,
                    attempts=self.outbox_attempts) == 1
            except Exception as e:
                self.logger.err("outbox update_rec_recipients:", e)
                persisted = False
        if not self.consume_notify or not persisted:
            return
        for chat_id in list(self.successfully_sent_to):
            self._charge_circle_notify(chat_id)

    def _charge_circle_notify(self, chat_id):
        if chat_id in self._quota_charged:
            return
        if chat_id in self.blocked_chats:
            return
        self._quota_charged.add(chat_id)
        from db.sqliteAdapter import SQLighter
        left = None
        db_users = SQLighter(db_path)
        try:
            db_users.decrease_notify_count(chat_id, 1)
            subscription = db_users.getUserSubscriptionByTg(chat_id)
            if subscription is not None:
                try:
                    left = int(subscription['notify_count'])
                except (TypeError, ValueError, KeyError):
                    left = None
        except Exception as e:
            self.logger.err("circle notify_count:", chat_id, e)
            return
        finally:
            db_users.close()
        if left != 0:
            return
        lang = self.lang_codes_by_utg.get(chat_id)
        if not lang:
            return
        try:
            outer_sender(chat_id, [{
                'type': 'text',
                'text': get_message("notificationsEnded", lang),
                'reply_markup': [[{
                    'text': get_message("tariffs", lang),
                    'callback_data': {'tp': 'bs_trfs'},
                }]],
            }])
        except Exception as e:
            self.logger.err("notificationsEnded:", chat_id, e)

    def _outbox_job_complete(self):
        if self.outbox_id is None:
            return True
        # User was told (too big / file gone): this row is finished work,
        # not a flood retry.
        if self.__too_big_record or self.__record_gone:
            return True
        if (self.outbox_attempts or 0) >= outbox.MAX_ATTEMPTS:
            return True
        for chat_id in self.chats:
            if (
                    chat_id not in self.successfully_sent_to
                    and chat_id not in self.blocked_chats
            ):
                return False
        return True

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

            # Progress edits a throwaway status message. If the user (or Telegram)
            # already dropped it, keep sending the audio and stop poking the ghost.
            if message_to_edit_not_found(e):
                self.outcome_messages[chat_id]['message_id'] = None
                return

            log_caught(self.logger, status, error=e)

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

        status_key = status
        once_statuses = ["compressing"]
        once_condition = status_key in once_statuses or (
            status_key == "uploading_to_telegram_servers" and additional is None)

        for chat_id in self.chats:
            if self.__chat_is_silent(chat_id):
                continue

            # status_key stays the lookup key: overwriting `status` in this loop
            # used to feed the first user's translated text into get_message_rtd
            # for everyone after them.
            text = self.statusTemplate + get_message_rtd(
                ["file_processing", status_key], self.lang_codes_by_utg[chat_id])
            if additional is not None:
                if 'percent' in additional:
                    text += f": {additional['percent']}%"

            try:
                if once_condition:
                    self.__make_update_status_message(chat_id, text)

                else:
                    write_thread = threading.Thread(
                        target=self.__make_update_status_message_excepted,
                        args=(chat_id, text,))
                    write_thread.start()
            except Exception as e:
                self.logger.warn(f"Can't set status {text} with error:")
                log_caught(self.logger, error=e)

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
                log_caught(self.logger, error=e)

    def send_record(self):
        self.logger.log(f"Begin sending {self.link} to {','.join(map(str, self.chats.keys()))}")

        retryable = None
        self._touch_outbox()
        try:
            if storage.enclosure_host_is_cool(self.link):
                self.__record_gone = True
                self.logger.warn("enclosure host cooling, skip download")
            else:
                self._deliver()

        except outbox.OutboxRetryableError as e:
            retryable = e
        # All services error
        except Exception as e:
            self._note_send_exception(e)
            if self.outbox_id is not None and not self.__record_gone and not self.__too_big_record:
                retryable = e

        self._sync_outbox_recipients()
        complete = self._outbox_job_complete()
        # Receipt only after Telegram ACK (or a terminal outcome: too big /
        # blocked chat). A 429 must not be done — leftover mp3 is ok.
        if complete:
            self._mark_outbox_done_after_send()

        # Удаляем файл и освобождаем место
        if self._file is not None:
            try:
                self._file.close()
            except Exception as e:
                self.logger.err(e, f"Can't delete file #{self._file.path}")

        self.__delete_status_messages()

        # Don't tell the user "unavailable" if the outbox will retry (429).
        will_retry = self.outbox_id is not None and not complete
        try:
            # Only chats that did not get the audio hear why. A circle job can
            # turn too big after part of its recipients already got the file.
            undelivered = list(self._remaining_chats())
            if self.__too_big_record:
                self.__send_too_big_record(targets=undelivered)

            elif not will_retry:
                self.__send_record_unavailable(targets=undelivered)
        except Exception as e:
            self.logger.warn(e)

        self.logger.log("Exit sending: ", datetime.datetime.now(), "\n\n\n")

        if will_retry:
            if retryable is not None:
                raise retryable
            raise RuntimeError("rec send failed")

        return self.successfully_sent_to

    def _mark_outbox_done_after_send(self):
        if self.outbox_id is None:
            return
        try:
            outbox.mark_done(self.outbox_id, attempts=self.outbox_attempts)
        except Exception as e:
            self.logger.err("outbox mark_done after send:", e)

    def __get_annex(self):
        if self.recordSizeMb > limits.BOT_UPLOAD_MB:
            return "l"
        elif self.recordSizeMb > limits.URL_FETCH_MB:
            return "m"
        else:
            return "s"

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
        self._touch_outbox()
        if mode not in ["up", "down"]:
            return

        last_percent: list[int] = [0]
        text = ""

        if mode == "up":
            # Если запись маленькая, прогресс не нужен
            if self.compressed_file_size_mb is not None and self.compressed_file_size_mb < limits.URL_FETCH_MB \
                    or (self.compressed_file_size_mb is None and self.recordSizeMb < limits.URL_FETCH_MB):
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

    def _deliver(self):
        """Same path for iTunes and RSS podcasts, user clicks and circle.

        Small files: Telegram fetches the URL. Otherwise, and for chats it
        could not serve, we get the file once and upload it (delivery.upload_order).
        """
        if not upload_order(self.recordSizeMb):
            self.__too_big_record = True
            return
        if fetch_by_url_first(self.recordSizeMb):
            delivered, _ = self.send_via_link()
            self.successfully_sent_to.extend(delivered)
            if not self._remaining_chats():
                return
        try:
            self._obtain_file()
        except DiskBusy as e:
            # Other downloads hold the space: give the lease back, come back later.
            self.logger.warn(e)
            raise outbox.OutboxRetryableError(e)
        except DiskTooSmall as e:
            self.logger.warn(e)
            self.__too_big_record = True
            return
        self._upload_to_remaining()

    def _obtain_file(self):
        """A file_id Telegram already has for this URL, or the episode on our disk."""
        cached_file_id = telegram_cache.get_file_id(self.link, 'audio')
        if cached_file_id is not None:
            self.cached_file_id = cached_file_id
            return
        name = "r%d_%d_%s.mp3" % (len(self.chats), time.time_ns() // 100, self.__get_annex())
        self._file = BudgetedDownload(
            disk_budget, os.path.join(self.work_dir, "records", name), expected_bytes=self.recordSize)
        self.__update_status_message("downloading")
        self._file.fetch(requester, self.link, progress=self.__download_file_callback)
        self._refresh_size_from_disk()

    def _refresh_size_from_disk(self):
        size = self._file.size_bytes() if self._file is not None else 0
        if size <= 0:
            return
        self.recordSize = size
        self.recordSizeMb = size / MB_NUMBER
        self.logger.log("File size on disk (mb): ", self.recordSizeMb)

    def _note_send_exception(self, error):
        log_caught(self.logger, error=error)
        if audio_source_gone(error):
            self.__record_gone = True
        if enclosure_host_fault(error):
            storage.mark_enclosure_host_cool(self.link)

    def _upload_to_remaining(self):
        """Upload the file (or reuse a file_id) to every chat not reached yet.

        HEAD Content-Length is often a lie: the order comes from the size on disk.
        """
        self._refresh_size_from_disk()
        order = upload_order(self.recordSizeMb)
        if not order:
            self.__too_big_record = True
            return
        refused_as_too_large = False
        for upload in order:
            remaining = list(self._remaining_chats())
            if not remaining:
                return
            if upload is Upload.AGENT:
                delivered, refusal = self.send_via_agent(remaining)
            elif self.cached_file_id is not None or self.recordSizeMb <= limits.BOT_UPLOAD_MB:
                delivered, refusal = self.send(remaining)
            else:
                continue  # over the Bot API upload limit, and no file_id to reuse
            self.successfully_sent_to.extend(delivered)
            refused_as_too_large |= refusal is not None and request_entity_too_large(refusal)
        if self._remaining_chats():
            if refused_as_too_large or self.recordSizeMb > limits.BOT_UPLOAD_MB:
                self.__too_big_record = True
            else:
                self.__record_gone = True

    def send_via_link(self):
        """Telegram fetches self.link for each chat."""
        def send_one(chat_id, caption):
            self.send_audio(chat_id, self.link, caption)

        return self._send_each(list(self._remaining_chats()), send_one, "success_s ")

    def send(self, chat_ids):
        """Bot API: the first chat gets the upload, the rest its file_id."""
        self.__update_status_message("uploading_to_telegram_servers")

        def send_one(chat_id, caption):
            if self.cached_file_id is not None:
                self.send_audio(chat_id, self.cached_file_id, caption)
                return
            with open(self._file.path, 'rb') as audio:
                file_id = self.send_audio(chat_id, audio, caption)
            if file_id is not None:
                self._remember_file_id(file_id)

        return self._send_each(chat_ids, send_one, "success_m ")

    def send_via_agent(self, chat_ids):
        """Telethon upload per bitrate group; the first delivery yields a file_id for the rest."""
        delivered, refusal = [], None
        for bitrate, group in self.bitrates.items():
            targets = [chat_id for chat_id in group if chat_id in chat_ids]
            if not targets:
                continue
            uploaded = self._agent_upload(bitrate)

            def send_one(chat_id, caption, uploaded=uploaded):
                caption = caption.replace('*', '**')
                if self.cached_file_id is not None:
                    self.send_audio(chat_id, self.cached_file_id, caption)
                    return
                sent = bot_telethon.send_uploaded(self.thonbot, self._agent_message(chat_id, caption), uploaded)
                self._remember_agent_file_id(sent)

            group_delivered, refusal = self._send_each(targets, send_one, "success_l ")
            delivered.extend(group_delivered)
            if refusal is not None:
                break
        return delivered, refusal

    def _agent_upload(self, bitrate):
        if bitrate is None and self.cached_file_id is not None:
            return self.cached_file_id
        path = self._file.path
        if bitrate is not None:
            # TODO: Compressing feature (need more servers)
            self.__update_status_message("compressing")
            path = compress_audio(path, bitrate)
            self.compressed_file_size_mb = os.path.getsize(path) / MB_NUMBER
            self.__prepare_status_template()
        self.__update_status_message("uploading_to_telegram_servers")
        return bot_telethon.upload(self.thonbot, path, callback=self.__upload_file_callback)

    def _agent_message(self, chat_id, caption):
        message = {
            'title': self.podcast_info['title'],
            'chat_id': chat_id,
            'file_id': 'fileid',
            'bot_name': botName,
            'duration_sec': self.podcast_info['duration_sec'],
            'channel_name': self.podcast_info['chName'],
            'message_text': caption,
        }
        if self.podcast_info['with_next_ep_button']:
            message['nextEpButtonText'] = get_message("loadNextRecord", self.lang_codes_by_utg[chat_id])
            message['nextEpButtonData'] = self.get_button_data()
        return message

    def _remember_agent_file_id(self, sent):
        """MTProto document ids are not Bot API file_ids: forward the agent's
        message to the storage chat and take the file_id from the copy."""
        try:
            forwarded = self.bot.forward_message(
                chat_id=storageChatId, from_chat_id=sent['chat_id'], message_id=sent['message_id'])
        except Exception as e:
            self.logger.log("Could not obtain Bot API file_id for cache:", e)
            return
        if not forwarded:
            return
        try:
            self.bot.delete_message(storageChatId, forwarded.message_id)
        except Exception:
            pass
        media = forwarded.audio or forwarded.document
        if media is None:
            self.logger.log("forward returned unexpected media type, skipping cache")
            return
        self._remember_file_id(media.file_id)

    def _remember_file_id(self, file_id):
        self.cached_file_id = file_id
        telegram_cache.add_file_id(self.link, file_id, 'audio', self.cache_expiration_date)

    def _send_each(self, chat_ids, send_one, success_tag):
        """Per-chat loop shared by the URL, Bot API and agent sends.

        send_one(chat_id, caption) delivers or raises. A blocked chat is marked
        and skipped; a flood gets one retry (or gives the outbox lease back); a
        refusal of the file itself ends the loop, since every next chat would
        get the same answer. Returns (delivered chat ids, that refusal or None).
        """
        delivered = []
        for chat_id in chat_ids:
            caption = self.prepare_record_text(chat_id, mode=self.__description_mode(chat_id))
            try:
                send_one(chat_id, caption)
            except outbox.OutboxRetryableError:
                raise
            except Exception as e:
                log_caught(self.logger, error=e)
                self.print_failure_message_stack(chat_id)
                if self.error_reactions(e, chat_id):
                    continue
                if file_refused(e):
                    return delivered, e
                if not self._retry_after_flood(e, send_one, chat_id, caption):
                    continue
            delivered.append(chat_id)
            self.logger.log(chat_id, success_tag, str(self.podcast_info['id']))
            self.__set_resend_status(chat_id)
        return delivered, None

    def _retry_after_flood(self, error, send_one, chat_id, caption):
        """One more try after a flood pause. With an outbox the lease goes back instead (raises)."""
        if not self._sleep_or_release_flood(error):
            return False
        try:
            send_one(chat_id, caption)
            return True
        except Exception as retry_error:
            log_caught(self.logger, error=retry_error)
            return False

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
            # Not a caption problem: the caller skips, stops or waits out the flood.
            if user_unavailable_error(e) or file_refused(e) or get_timeout_from_error_bot(e):
                raise

            self.logger.warn(e, "Fail to send with caption")
            if hasattr(audio, 'seek'):
                try:
                    audio.seek(0)
                except Exception:
                    pass
            message = self.bot.send_audio(
                chat_id=chat_id, audio=audio,
                duration=self.podcast_info['duration_sec'],
                performer=self.podcast_info['chName'], title=self.podcast_info['title'])
            # Same markup would fail the same way: say it as plain text.
            as_plain_text = entities_parse_error(e)
            try:
                self.bot.send_message(
                    chat_id=chat_id,
                    text=(telegram_html.plain_text(record_message_text) if as_plain_text
                          else record_message_text),
                    parse_mode=None if as_plain_text else "HTML",
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
        outcome_message_id = self.outcome_messages.get(chat_id, {}).get('message_id')

        message_text = self.prepare_record_text(
            chat_id, mode='short', on_error=True) + "\n\n" + get_message(
            "tooBigRecord", lang_code) % telegram_html.href(self.link)

        # One link per line, like format_record_unavailable. The site line used
        # to check itunesLink, so RSS episodes never showed it.
        if self.podcast_info['itunesLink']:
            message_text += "\n" + get_message(
                "tooBigRecord2", lang_code) % telegram_html.href(self.podcast_info['itunesLink'])

        if self.podcast_info['channelLink']:
            message_text += "\n" + get_message(
                "tooBigRecord3", lang_code) % telegram_html.href(self.podcast_info['channelLink'])

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
                + str(lang_code) + str(self.podcast_info['channelLink']) + "\n\n" + str(self.link),
                level='error')

        error_text = (
                self.prepare_record_text(chat_id, mode='short', on_error=True) + "\n\n"
                + format_record_unavailable(
                    lang_code,
                    self.podcast_info.get('channelLink'),
                    self.link if isinstance(self.link, str) else None))

        try:
            if self.outcome_messages.get(chat_id, {}).get('message_id') is not None:
                self.__make_update_status_message(chat_id, error_text)
            else:
                outer_sender(chat_id, [{'type': 'text', 'text': error_text}])
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
        self.statusTemplate = telegram_html.text(self.podcast_info['chName']) + "\n" + \
                              "<b>" + telegram_html.text(self.podcast_info['title']) + "</b>\n\n" + \
                              emojiCodes.get('floppyDisk') + " " + str(round(self.recordSizeMb, 2)) + " MiB" + \
                              ("\n" if self.compressed_file_size_mb is None
                               else f" -> {round(self.compressed_file_size_mb, 2)} MiB\n")

    def prepare_record_text(self, chat_id, mode: DescriptionModeOptions = 'default', on_error=False):

        lang_code = self.lang_codes_by_utg[chat_id]
        chat = self.chats[chat_id]

        return record_caption(
            lang_code, mode, self.podcast_info['channelLink'], self.podcast_info['chName'],
            self.podcast_info['title'], self.podcast_info['id'],
            self.podcast_info['pubDate'], self.podcast_info['descr'],
            self.podcast_info['service_name'], self.podcast_info['service_id'],
            on_error=on_error,
            show_updated_text=('show_updated_text' not in chat or chat['show_updated_text'] is True),
            bot_reference=('bot_reference' not in chat or chat['bot_reference'] is True))

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
