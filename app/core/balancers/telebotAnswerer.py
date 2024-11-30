import datetime
import queue
import threading
import typing

import config
from app.controller.builders import welcomeModule
from app.repository.storage import storage
from app.routes.middleware.default_middleware import analytics_serving, \
    check_threads, get_user, analytics_serving_inline
from app.routes.ptypes import HandleInThreadParams, ControllerParams
from config import threads_config

from lib.tools.logger import logger
from lib.tools.loggers.incoming import log_incoming_data, log_incoming_inline


# main idea is to have several threads

class TelebotBalancer(threading.Thread):

    def __init__(self, main_queue, threads_to_watch, args=(), kwargs=None):
        threading.Thread.__init__(self, args=(), kwargs=None)
        self.daemon = True
        self.name = 'Telebot Balancer'

        self.main_queue = main_queue
        self.current_send_thread = 0
        self.count_send_threads = threads_config['send']
        self.send_queues: list[queue.Queue] = []
        self.send_threads: list[TheSender] = []

        threads_to_watch.append(self)
        self.threads_to_watch = threads_to_watch

        for i in range(0, self.count_send_threads):
            self.send_queues.append(queue.Queue())
            self.send_threads.append(
                TheSender(
                    self.send_queues[i], self.threads_to_watch, f"send_{i}"))
            self.send_threads[i].start()

    def run(self):

        while True:
            input_data = self.main_queue.get()

            logger.log('Incoming task...' + str(datetime.datetime.now()))

            if not self.send_threads[self.current_send_thread].is_alive():
                logger.warn(f"THREAD IS DEAD: send_{self.current_send_thread}")
                self.send_queues[self.current_send_thread] = queue.Queue()
                self.send_threads[self.current_send_thread] = TheSender(
                    self.send_queues[self.current_send_thread],
                    self.threads_to_watch,
                    f"send_{self.current_send_thread}")
                self.send_threads[self.current_send_thread].start()
                print(
                    self.send_queues[self.current_send_thread],
                    self.send_threads[self.current_send_thread])

            logger.log(f"Using thread {self.current_send_thread}")
            self.send_threads[self.current_send_thread].thread_queue.put(input_data)
            self.current_send_thread = (self.current_send_thread + 1) \
                                       % self.count_send_threads


def process_input(input_data) -> bool | None:
    logger.log('Processing...')

    return input_data['action'](input_data['data'])


class TheSender(threading.Thread):

    def __init__(
            self, thread_queue, threads_to_watch, thread_num, args=(), kwargs=None
    ):

        threading.Thread.__init__(self, args=(), kwargs=None)
        self.daemon = True

        self.threads_to_watch = threads_to_watch

        self.thread_queue = thread_queue
        self.thread_num = thread_num

    def run(self):

        while True:
            input_data: HandleInThreadParams = self.thread_queue.get()
            logger.log(f"Hello from {self.thread_num}")

            if input_data['data'] is None:  # The action is filtered
                continue

            # Check threads
            check_threads(self.threads_to_watch)

            # Actions in the bot
            if 'message' in input_data['data'] and 'callback' in input_data['data']:
                controller_params: ControllerParams = typing.cast(ControllerParams, input_data['data'])
                log_incoming_data(controller_params['callback'], controller_params['message'])

                # Set user
                input_data['data']['user'] = get_user(input_data['data']['chat_id'])

                start_related_params = self._action(input_data)
                analytics_serving(
                    controller_params, input_data['data']['user'],
                    start_related_params['is_new_user'], start_related_params['is_by_refer'],
                    start_related_params['action'])

            # Inline query
            elif 'inline' in input_data['data']:
                log_incoming_inline(input_data['data']['inline'])

                # Set user
                input_data['data']['user'] = get_user(input_data['data']['inline'].user_id)

                process_input(input_data)
                analytics_serving_inline(input_data['data'], input_data['data']['user'])

            logger.log("Served\n\n")

    def _action(self, input_data):
        if not config.server:  # Inline don't have chat_id
            logger.log("Routes before:", storage.get_user_states(input_data['data']['chat_id']))

        # TODO! Check that all stuff below is working properly

        # Start – is a special message
        # Start-related processing
        start_related_params = welcomeModule.start_related_options(input_data['data'])

        # The processing!
        if start_related_params['action'] is None:  # Process only if the action is None
            try:
                change_state = process_input(input_data)
            except Exception as e:
                logger.err(e)
                change_state = False

            # Set new state for user
            if (input_data['data']['route_name'] is not None  # action is set
                    and change_state is not False  # returns None by default, False means that not processed
                    and input_data['data']['action_name'] is None):  # not action (actions may change state manually)
                storage.add_user_state(input_data['data']['chat_id'], input_data['data']['route_name'])

        if not config.server:
            logger.log("Routes after:", storage.get_user_states(input_data['data']['chat_id']))

        return start_related_params
