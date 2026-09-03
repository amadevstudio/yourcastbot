import asyncio
import queue
import threading
from typing import Dict, List

from telethon import TelegramClient
from telethon.sessions import StringSession

from agent import bot_telethon
from app.controller.builders import recsModule
from app.jobs import podcastsUpdater
from config import app_api_id, app_api_hash, token, threads_config
from lib.python.singletonBase import Singleton
from lib.tools.logger import Logger

logger = Logger(file="sender")


# main idea is to have several threads which have their own event loop
# and starts telethon several exemplars

class RecordBalancer(threading.Thread, metaclass=Singleton):

    def __init__(self, main_queue, args=(), kwargs=None):
        threading.Thread.__init__(self, args=(), kwargs=None)
        self.daemon = True
        self.name = 'Send Balancer'

        self.main_queue = main_queue

        self.actions = ['rec', 'update']

        self.count_threads: Dict[str, int] = {}
        self.queues: Dict[str, List[queue.Queue]] = {}
        self.threads: Dict[str, List[RecordSender]] = {}
        self.user_threads: Dict[str, Dict[str, int]] = {}

        for action in self.actions:
            self.count_threads[action] = threads_config[action]
            self.queues[action] = []
            self.threads[action] = []
            self.user_threads[action] = {}

            for i in range(0, self.count_threads[action]):
                self.queues[action].append(queue.Queue())
                self.threads[action].append(
                    RecordSender(self.queues[action][i], f"{action}_{i}"))
                self.threads[action][i].start()

    def run(self):

        while True:
            try:
                input_data = self.main_queue.get()
            except Exception as e:
                logger.err("Send balancer failed to read queue:", e)
                continue

            try:
                self._dispatch(input_data)
            except Exception as e:
                logger.err("Send balancer failed to dispatch:", e)
            finally:
                try:
                    self.main_queue.task_done()
                except ValueError:
                    pass

    def _dispatch(self, input_data):
        logger.log("Received new sending task")

        action = input_data['action']
        if action not in self.actions:
            logger.warn(f"Unknown sender action {action!r}, skipping")
            return

        self.cancel_threads_booking()

        logger.log(f"Sender threads state for {action}",
                   [f"Is alive: {t.is_alive()}, {t.name}" for t in self.threads[action]], "\n",
                   "Pending queues", [q.qsize() for q in self.queues[action]], "\n",
                   "User bookings", self.user_threads[action])

        # бронирован ли поток?
        current_user_thread = self.user_threads[action].get(input_data['user_id'], None)
        if current_user_thread is None:  # у пользователя нет занятых потоков
            current_thread_index = self.less_loaded_thread_index(action)
        else:  # пользователь уже занял поток
            current_thread_index = current_user_thread
        # бронируем поток под пользователя
        self.user_threads[action][input_data['user_id']] = current_thread_index

        logger.log(f"For user {input_data['user_id']} thread {current_thread_index} is chosen")

        self._ensure_sender_alive(action, current_thread_index)

        self.threads[action][current_thread_index].resume()
        self.queues[action][current_thread_index].put(input_data)

    def _ensure_sender_alive(self, action, current_thread_index):
        if self.threads[action][current_thread_index].is_alive():
            return

        logger.log(f"Thread {action}:{current_thread_index} is dead, restarting")
        self.threads[action][current_thread_index] = RecordSender(
            self.queues[action][current_thread_index],
            f"{action}_{current_thread_index}")
        self.threads[action][current_thread_index].start()
        logger.log(
            f"Thread {action}:{current_thread_index} is started, current is alive is "
            f"{self.threads[action][current_thread_index].is_alive()}")

    def less_loaded_thread_index(self, action):
        minimum = -1
        minimum_index = int()
        for i in range(len(self.queues[action])):
            pending_queue = self.queues[action][i]
            qsize = pending_queue.qsize()
            if qsize < minimum or minimum == -1:
                minimum = qsize
                minimum_index = i
        return minimum_index

    # user_threads: {'rec': {1: []}} -> {'rec': {}} after thread taken in the job
    def cancel_threads_booking(self):
        for action in self.actions:
            for user_id in list(self.user_threads[action].keys()):
                if self.queues[action][self.user_threads[action][user_id]].empty():
                    self.user_threads[action].pop(user_id)


class RecordSender(threading.Thread):

    def __init__(self, thread_queue, thread_num, args=(), kwargs=None):

        threading.Thread.__init__(self, args=(), kwargs=None)
        self.daemon = True
        self.name = thread_num
        self.paused = True
        self.state = threading.Condition()

        self.thread_queue = thread_queue
        self.thread_num = thread_num

    def pause(self):
        with self.state:
            self.paused = True

    def resume(self):
        with self.state:
            self.paused = False
            self.state.notify()

    def run(self):

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        thonbot = None
        logger.log(f"{self.thread_num} waiting for send jobs")

        while True:
            try:
                input_data = self.thread_queue.get()
            except Exception as e:
                logger.err(f"{self.thread_num} failed to read queue:", e)
                continue

            try:
                logger.log(f"Sending in thread #{self.thread_num}")
                if thonbot is None:
                    thonbot = self._connect_telethon(loop)
                if thonbot is None:
                    logger.warn(
                        f"{self.thread_num} Telethon unavailable, "
                        f"cannot {input_data.get('action')}")
                else:
                    self.process_input(input_data, thonbot)
            except Exception as e:
                logger.err(f"{self.thread_num} failed sending, continuing:", e)
            finally:
                self.thread_queue.task_done()
                if self.thread_queue.empty():
                    self.pause()

    def _connect_telethon(self, loop):
        if not bot_telethon.telethon_available or not bot_telethon.thobot_session_handler:
            logger.log(f"{self.thread_num} running without Telethon")
            return None
        try:
            client = TelegramClient(
                StringSession(bot_telethon.thobot_session_handler),
                app_api_id, app_api_hash, loop=loop
            ).start(bot_token=token)
            client.disconnect()
            return client
        except Exception as e:
            logger.err(f"{self.thread_num} Telethon connect failed:", e)
            return None

    def process_input(self, input_data, thonbot):

        if input_data['action'] == 'rec':

            recsModule.send_record_thread(input_data, thonbot)

        elif input_data['action'] == 'update':

            podcastsUpdater.update_feed_thread(input_data, thonbot)
