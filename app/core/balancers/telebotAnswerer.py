import datetime
import threading
import time
import typing

import config
from app.controller.builders import welcomeModule
from app.repository.storage import storage
from app.routes.middleware.default_middleware import analytics_serving, \
    check_threads, get_user, analytics_serving_inline
from app.core.balancers.sticky import UserGate, incoming_user_id
from app.routes.ptypes import HandleInThreadParams, ControllerParams
from config import threads_config

from lib.tools.logger import logger
from lib.tools.loggers.incoming import log_incoming_data, log_incoming_inline


incoming_gate = UserGate()


class TelebotBalancer(threading.Thread):

    def __init__(self, main_queue, threads_to_watch, args=(), kwargs=None):
        threading.Thread.__init__(self, args=(), kwargs=None)
        self.daemon = True
        self.name = 'Telebot Balancer'

        self.main_queue = main_queue
        self.count_send_threads = threads_config['send']
        self.send_threads: list[TheSender] = []

        threads_to_watch.append(self)
        self.threads_to_watch = threads_to_watch

        for i in range(0, self.count_send_threads):
            self.send_threads.append(
                TheSender(
                    self.main_queue, self.threads_to_watch, f"send_{i}"))
            self.send_threads[i].start()

    def run(self):
        # Workers consume main_queue directly. This thread only restarts
        # a dead worker; it must not get() or it would steal jobs.
        while True:
            time.sleep(2)
            for i, sender in enumerate(self.send_threads):
                if sender.is_alive():
                    continue
                logger.warn(
                    f"THREAD IS DEAD: send_{i}, restarting on the shared queue")
                self.send_threads[i] = TheSender(
                    self.main_queue, self.threads_to_watch, f"send_{i}")
                self.send_threads[i].start()


def process_input(input_data) -> bool | None:
    logger.log('Processing...')

    return input_data['action'](input_data['data'])


class TheSender(threading.Thread):

    def __init__(
            self, thread_queue, threads_to_watch, thread_num, args=(), kwargs=None
    ):

        threading.Thread.__init__(self, args=(), kwargs=None)
        self.daemon = True
        self.name = thread_num

        self.threads_to_watch = threads_to_watch

        self.thread_queue = thread_queue
        self.thread_num = thread_num

    def run(self):

        while True:
            try:
                input_data: HandleInThreadParams = self.thread_queue.get()
            except Exception as e:
                logger.err(f"{self.thread_num} failed to read queue:", e)
                continue

            try:
                self._serve(input_data)
            except Exception as e:
                logger.err(f"{self.thread_num} failed serving a request, continuing:", e)

    def _serve(self, input_data: HandleInThreadParams):
        logger.log(
            'Incoming task...' + str(datetime.datetime.now()),
            f"{self.thread_num} user {incoming_user_id(input_data)}")

        if input_data['data'] is None:  # The action is filtered
            return

        with incoming_gate.hold(incoming_user_id(input_data)):
            self._serve_locked(input_data)

        logger.log("Served\n\n")

    def _serve_locked(self, input_data: HandleInThreadParams):
        check_threads(self.threads_to_watch)

        if 'message' in input_data['data'] and 'callback' in input_data['data']:
            controller_params: ControllerParams = typing.cast(
                ControllerParams, input_data['data'])
            log_incoming_data(
                controller_params['callback'], controller_params['message'])

            input_data['data']['user'] = get_user(input_data['data']['chat_id'])

            start_related_params = self._action(input_data)
            analytics_serving(
                controller_params, input_data['data']['user'],
                start_related_params['is_new_user'],
                start_related_params['is_by_refer'],
                start_related_params['action'])

        elif 'inline' in input_data['data']:
            log_incoming_inline(input_data['data']['inline'])

            input_data['data']['user'] = get_user(
                input_data['data']['inline'].user_id)

            process_input(input_data)
            analytics_serving_inline(
                input_data['data'], input_data['data']['user'])

    def _action(self, input_data):
        if not config.server:  # Inline don't have chat_id
            logger.log("Routes before:", storage.get_user_states(input_data['data']['chat_id']))

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
