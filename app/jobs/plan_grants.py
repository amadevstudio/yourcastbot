# -*- coding: utf-8 -*-
"""Every hour, each holder of free Bronze for channels (db/plan_grants.py) is checked:
- subscribed to every listed channel: the plan is held (HOLD_HOURS ahead);
- one missing (the chat left, or the owner added a channel): the chat is warned once, with the
  channels, and keeps the plan channels.GRACE_HOURS; still missing then, it ends (the plan it replaced
  back, no days) with a message, the channels' screen and every plan;
- turned off in the admin (or no channel left): every grant ends with a message and every plan;
- a check Telegram does not answer keeps the plan and tells the creator once a day.
A holder the hour misses is held by the next one: the hold is a week.
Lock: python app/service/plan/test_channels.py
"""
import time

from app.service import analytics_events
from app.service.plan import channels
from db import plan_grants
from lib.tools.logger import logger

CHECK_SECONDS = 3600
PAUSE_SECONDS = 0.05  # between holders: getChatMember for each channel, well under the Bot API's limits


def _ended(holder, reason, absent, database):
    analytics_events.track(holder['telegram_id'], 'plan_grant_ended',
                           {'kind': channels.KIND, 'reason': reason, 'missing': len(absent)}, database=database)


def _check(holder, conf, now, request, send, database, failures) -> str:
    """What became of one holder: 'held', 'warned', 'ended', 'failed' (kept), 'gone' (none held)."""
    if not channels.available(conf):
        if not plan_grants.end_now(holder['user_id'], 'stopped', now=now, database=database):
            return 'gone'
        _ended(holder, 'stopped', [], database)
        send(holder['telegram_id'], [channels.stopped_message(holder['lang'])])
        return 'ended'
    try:
        absent = channels.missing(holder['telegram_id'], conf, request)
    except channels.CheckFailed as e:
        failures.append(str(e))
        return 'failed' if plan_grants.hold(holder['user_id'], now, database) else 'gone'
    if not absent:
        return 'held' if plan_grants.hold(holder['user_id'], now, database) else 'gone'
    since = plan_grants.mark_missing(holder['user_id'], now, database)
    if since is None:
        return 'gone'
    if since == now:
        send(holder['telegram_id'], [channels.warn_message(holder['lang'], absent)])
        return 'warned'
    if now - since < channels.GRACE_HOURS * 3600:
        return 'warned'
    if not plan_grants.end_now(holder['user_id'], 'unsubscribed', now=now, database=database):
        return 'gone'
    _ended(holder, 'unsubscribed', absent, database)
    send(holder['telegram_id'], [channels.off_message(holder['lang'], absent)])
    return 'ended'


def check_holders(database=None, now=None, request=None, send=None, pause=PAUSE_SECONDS) -> dict:
    """{'held', 'warned', 'ended', 'failed'}: one pass over the holders ('warned': within the grace)."""
    if send is None:
        from lib.telegram.general.message_master import outer_sender as send
    now = time.time() if now is None else now
    conf = channels.settings(database)
    done = {'held': 0, 'warned': 0, 'ended': 0, 'failed': 0}
    failures = []
    for holder in plan_grants.holders(channels.KIND, database):
        try:
            outcome = _check(holder, conf, now, request, send, database, failures)
            if outcome in done:
                done[outcome] += 1
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
