# -*- coding: utf-8 -*-
"""Amplitude events that are not taps.

Taps reach Amplitude from the bot role (default_middleware.analytics_serving,
one event per route). What the bot does on its own did not: a digest sent,
a plan that ended, a payment, a summary made. Without them a digest's
click-through or the trial-to-paid funnel cannot be counted there.

`track` takes a Telegram chat id and may run in any role (jobs, the payment
scripts): the Analytics singleton is started here when the role has none.
The Amplitude user is `users.id`, as for taps. A user the bot does not know
is not tracked (never a row created for them), and tracking never fails the
caller.

Events: digest_sent {episodes}, plan_off {level, paid_before},
payment {method, amount_cents, level}, summary_ready {cached, seconds}.
"""
from db.connection import connect_sqlite
from lib.tools.logger import logger

DIGEST_SOURCE = 'd'  # the `s` key of a digest's Listen button
SOURCES = {DIGEST_SOURCE: 'digest'}


def _analytics():
    from lib.analytics.analytics import Analytics, AmplitudeAnalytics
    try:
        return Analytics()
    except AttributeError:  # this role has not started it (only the bot role does)
        import config
        return Analytics(AmplitudeAnalytics(config.amplitude_analytics_api_key), test_mode=not config.server)


def _user(telegram_id, database=None):
    if database is None:
        from config import db_path as database
    connection = connect_sqlite(database)
    try:
        return connection.execute(
            "SELECT id, lang FROM users WHERE telegramId = ?", (int(telegram_id),)).fetchone()
    finally:
        connection.close()


def track(telegram_id, event, properties=None, database=None, analytics=None, sync=False) -> bool:
    """sync: send before returning (a script that exits next would drop the queue)."""
    try:
        user = _user(telegram_id, database)
        if user is None:
            return False
        analytics = analytics or _analytics()
        args = {'user_id': user[0], 'command': event,
                'user_properties': {'lang': user[1], 'telegram_id': int(telegram_id)},
                'event_properties': dict(properties or {})}
        if sync:
            analytics.event(args)
        else:
            analytics.queue.put((analytics.event, args))
        return True
    except Exception as e:
        logger.warn("analytics event", event, "not tracked:", type(e).__name__, e)
        return False


def plan_off(telegram_id, level, database=None) -> bool:
    """A plan ended (the tick did not renew it); paid_before False is a trial that did not convert."""
    try:
        from db.tariff_rows import ever_paid
        paid_before = ever_paid(telegram_id, database)
    except Exception as e:
        logger.warn("analytics plan_off:", type(e).__name__, e)
        paid_before = None
    return track(telegram_id, 'plan_off', {'level': level, 'paid_before': paid_before}, database)


def tap_properties(button_data) -> dict:
    """Extra properties of a tap: where its button was (a digest's Listen)."""
    source = SOURCES.get(button_data.get('s')) if isinstance(button_data, dict) else None
    return {'source': source} if source else {}
