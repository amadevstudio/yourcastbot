# -*- coding: utf-8 -*-
"""Every hour, each holder of free Bronze for channels (db/plan_grants.py) is checked: still subscribed
to `need` of the channels, the plan is held (HOLD_HOURS ahead); fewer, it ends (the plan it replaced
back, no days) and the chat hears it with Relay's invoice. A check Telegram does not answer keeps the
plan and tells the creator once a day; an empty list in the admin keeps every plan (an owner's slip is
not the users' loss). A holder the hour misses is held by the next one: the hold is a week.
Lock: python app/service/plan/test_channels.py
"""
import time

from app.service import analytics_events
from app.service.plan import channels
from db import plan_grants
from lib.tools.logger import logger

CHECK_SECONDS = 3600
PAUSE_SECONDS = 0.05  # between holders: getChatMember for each channel, well under the Bot API's limits


def check_holders(database=None, now=None, request=None, send=None, pause=PAUSE_SECONDS) -> dict:
    """{'held', 'ended', 'failed'}: one pass over the holders."""
    if send is None:
        from lib.telegram.general.message_master import outer_sender as send
    conf = channels.settings(database)
    done = {'held': 0, 'ended': 0, 'failed': 0}
    failures = []
    for holder in plan_grants.holders(channels.KIND, database):
        failed = False
        try:
            count = channels.subscribed(holder['telegram_id'], conf, request) if channels.available(conf) else None
        except channels.CheckFailed as e:
            failures.append(str(e))
            count, failed = None, True
        try:
            if count is None or count >= conf['need']:
                plan_grants.hold(holder['user_id'], now, database)
                done['failed' if failed else 'held'] += 1
            elif plan_grants.end_now(holder['user_id'], 'unsubscribed', now=now, database=database):
                done['ended'] += 1
                analytics_events.track(holder['telegram_id'], 'plan_grant_ended',
                                       {'kind': channels.KIND, 'count': count, 'need': conf['need']},
                                       database=database)
                send(holder['telegram_id'], [channels.off_message(holder['lang'], count, conf['need'])])
        except Exception as e:
            logger.warn("free Bronze holder", holder['telegram_id'], type(e).__name__, e)
        if pause:
            time.sleep(pause)
    if failures:
        channels.warn_creator("%d checks failed, plans kept. %s" % (len(failures), failures[0]), now, database)
    return done


def grant_watcher():
    while True:
        try:
            done = check_holders()
            if any(done.values()):
                logger.log("free Bronze checks:", done)
        except Exception as e:
            logger.err("free Bronze checks:", e)
        time.sleep(CHECK_SECONDS)
