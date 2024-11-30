# -*- coding: utf-8 -*-

import threading
import queue
# import tracemalloc

import app.jobs.balance_watcher
import app.jobs.payment_watcher
import config
from app.jobs import podcastsUpdater, clean_old_data, backup_db
from app.routes.initialize_routes import initialize_routes

from lib.analytics import analytics
from app.core.balancers import recordSender, telebotAnswerer

from agent.bot_telethon import thonbot
from lib.tools.logger import logger

logger.log("The bot is starting", '---\n\n')

# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# SETUP
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

# tracemalloc.start(10)

answer_sender_queue: queue.Queue = queue.Queue()

# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# Initialize classes
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

amplitudeAnalytics = analytics.AmplitudeAnalytics(
    config.amplitude_analytics_api_key)
analytics.Analytics(
    amplitudeAnalytics, test_mode=(not config.server))


# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# INITIALIZING
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!


threads_to_watch = []

t_podcast_sender = recordSender.RecordBalancer(None)  # already initialized in builders/recsModule


def setup_threads():
    t = threading.Thread(target=podcastsUpdater.main, args=(10,))
    t.daemon = True
    t.name = 'Podcast Updater'
    t.start()
    threads_to_watch.append(t)

    t_podcast_sender.start()
    threads_to_watch.append(t_podcast_sender)

    t_rec_cleaner = threading.Thread(
        target=clean_old_data.main, args=(1440,))
    t_rec_cleaner.daemon = True
    t_rec_cleaner.name = 'Rec cleaner'
    t_rec_cleaner.start()

    if config.server:
        t_db_backuper = threading.Thread(
            target=backup_db.main, args=(1440,))
        t_db_backuper.daemon = True
        t_db_backuper.name = 'Db backup'
        t_db_backuper.start()
        threads_to_watch.append(t_db_backuper)

    t_balance_watcher = threading.Thread(
        target=app.jobs.balance_watcher.balance_watcher,
        args=(config.balance_watcher_period,))
    t_balance_watcher.daemon = True
    t_balance_watcher.name = 'Balance watcher'
    t_balance_watcher.start()
    threads_to_watch.append(t_balance_watcher)

    t_patreon_watcher = threading.Thread(
        target=app.jobs.payment_watcher.patreon_watcher,
        args=(config.payment_service_watcher_period,))
    t_patreon_watcher.daemon = True
    t_balance_watcher.name = 'Patreon payment watcher'
    t_patreon_watcher.start()
    threads_to_watch.append(t_patreon_watcher)


if __name__ == '__main__':
    setup_threads()

    t_answer_sender = telebotAnswerer.TelebotBalancer(
        answer_sender_queue, threads_to_watch)
    t_answer_sender.start()

    initialize_routes(t_answer_sender, answer_sender_queue, threads_to_watch)

    thonbot.run_until_disconnected()
