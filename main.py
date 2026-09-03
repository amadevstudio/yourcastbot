# -*- coding: utf-8 -*-
"""Yourcast bot.

Start with one command:

    python main.py

That process is a supervisor. It runs three children (bot, updater, jobs)
and restarts a crashed role without taking the others down.

Production deploy is still one command: supervisorctl restart yourcast

Debug a single role: python main.py --role bot|updater|jobs
"""

import argparse
import os
import queue
import signal
import sys
import threading
import time

from app.core.process_supervisor import (
    ROLES, consume_updater_crash_flag, run_supervisor)
from lib.tools.logger import logger


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Yourcast bot (one command starts everything)")
    parser.add_argument(
        "--role", choices=ROLES, default=None,
        help="Run a single role. Default: supervise all roles.")
    return parser.parse_args(argv)


def _close_open_storage():
    from app.repository.storage import storage as storage_module
    from app.repository.storage import telegram_cache
    storage_module.close_storage()
    telegram_cache.close_storage()


def _install_shutdown():
    def shutdown(signum, _frame):
        logger.log(f"Received signal {signum}, shutting down...")
        _close_open_storage()
        logger.log("Shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)


def _announce_restart_if_needed():
    role = os.environ.get("YOURCAST_ROLE")
    try:
        count = int(os.environ.get("YOURCAST_RESTART_COUNT") or "0")
    except ValueError:
        count = 0
    if not role or count <= 0:
        return
    try:
        from app.controller.builders.adminModule import send_message_to_creator
        send_message_to_creator(
            f"Процесс {role} перезапущен (#{count})", level="warning")
    except Exception as e:
        logger.err("Could not announce role restart:", e)


def run_bot():
    _install_shutdown()
    _announce_restart_if_needed()

    import config
    import app.jobs.payment_watcher
    from lib.analytics import analytics
    from agent.bot_telethon import thonbot
    from app.controller.builders import recsModule
    from app.core.balancers import telebotAnswerer
    from app.routes.initialize_routes import initialize_routes

    amplitude_analytics = analytics.AmplitudeAnalytics(
        config.amplitude_analytics_api_key)
    analytics.Analytics(
        amplitude_analytics, test_mode=(not config.server))

    threads_to_watch = []
    recsModule.start_record_balancer()
    threads_to_watch.append(recsModule.t_podcast_sender)

    t_patreon_watcher = threading.Thread(
        target=app.jobs.payment_watcher.patreon_watcher,
        args=(config.payment_service_watcher_period,))
    t_patreon_watcher.daemon = True
    t_patreon_watcher.name = "Patreon payment watcher"
    t_patreon_watcher.start()
    threads_to_watch.append(t_patreon_watcher)

    answer_sender_queue: queue.Queue = queue.Queue()
    t_answer_sender = telebotAnswerer.TelebotBalancer(
        answer_sender_queue, threads_to_watch)
    t_answer_sender.start()

    initialize_routes(t_answer_sender, answer_sender_queue, threads_to_watch)
    thonbot.run_until_disconnected()


def run_updater():
    _install_shutdown()
    _announce_restart_if_needed()

    from app.repository.storage import storage as storage_module
    if consume_updater_crash_flag():
        storage_module.set_last_channel_restarted(True)

    from app.jobs import podcastsUpdater
    podcastsUpdater.main(10)


def run_jobs():
    _install_shutdown()
    _announce_restart_if_needed()

    import app.jobs.balance_watcher
    import config
    from app.jobs import backup_db, clean_old_data

    t_rec_cleaner = threading.Thread(
        target=clean_old_data.main, args=(1440,))
    t_rec_cleaner.daemon = True
    t_rec_cleaner.name = "Rec cleaner"
    t_rec_cleaner.start()

    watched: list[threading.Thread] = []

    if config.server:
        t_db_backuper = threading.Thread(target=backup_db.main)
        t_db_backuper.daemon = True
        t_db_backuper.name = "Db backup"
        t_db_backuper.start()
        watched.append(t_db_backuper)

    t_balance_watcher = threading.Thread(
        target=app.jobs.balance_watcher.balance_watcher,
        args=(config.balance_watcher_period,))
    t_balance_watcher.daemon = True
    t_balance_watcher.name = "Balance watcher"
    t_balance_watcher.start()
    watched.append(t_balance_watcher)

    while True:
        time.sleep(2)
        for t in watched:
            if not t.is_alive():
                logger.err("Job thread died:", t.name)
                _close_open_storage()
                sys.exit(1)


def main(argv=None):
    args = _parse_args(argv)
    if args.role is None:
        logger.log("Supervisor starting", '---\n\n')
        # gdbm is still exclusive; copy the updater cursor before any child
        # opens shelve or sqlite WAL.
        try:
            from db.runtime_kv import migrate_updater_state_from_shelve
            migrate_updater_state_from_shelve()
        except Exception as e:
            logger.err("Updater cursor migrate skipped:", e)
        run_supervisor()
        return
    os.environ.setdefault("YOURCAST_ROLE", args.role)
    logger.log("The bot is starting", args.role, '---\n\n')
    if args.role == "bot":
        run_bot()
    elif args.role == "updater":
        run_updater()
    elif args.role == "jobs":
        run_jobs()
    else:
        raise SystemExit("unknown role %s" % args.role)


if __name__ == "__main__":
    main()
