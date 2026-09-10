# -*- coding: utf-8 -*-
"""Updater circle health in runtime_kv. Telegram at most once per day.

Every pass still logs. #new_circle Telegram is noise (always luci 1).
#circle_finished is one daily heartbeat: duration of this pass plus
yesterday's full count (today is always 1 on that first ping).
Live numbers belong on /usersCount, not a fourth admin command.
"""
import datetime

from db import runtime_kv

KEY_STARTED_AT = 'updater_circle_started_at'
KEY_FINISHED_AT = 'updater_circle_finished_at'
KEY_DURATION_SEC = 'updater_circle_duration_sec'
KEY_CIRCLES_TODAY = 'updater_circles_today'
KEY_CIRCLES_YESTERDAY = 'updater_circles_yesterday'
KEY_TODAY = 'updater_circles_today_date'
KEY_NOTIFIED_ON = 'updater_circle_notified_on'


def _int_kv(key, database=None, default=0):
    raw = runtime_kv.get_kv(key, default=str(default), database=database)
    try:
        return int(raw or default)
    except (TypeError, ValueError):
        return default


def _today(now=None):
    when = now or datetime.datetime.now()
    return when.strftime('%Y-%m-%d')


def _iso(now=None):
    when = now or datetime.datetime.now()
    return when.strftime('%Y-%m-%dT%H:%M:%S')


def mark_circle_started(now=None, database=None):
    runtime_kv.set_kv(KEY_STARTED_AT, _iso(now), database=database)


def mark_circle_finished(now=None, database=None):
    """Record duration and today's count. notify=True only on the first finish today."""
    when = now or datetime.datetime.now()
    today = _today(when)
    finished_iso = _iso(when)
    started = runtime_kv.get_kv(KEY_STARTED_AT, default='', database=database)
    duration_sec = 0
    if started:
        try:
            started_dt = datetime.datetime.strptime(started, '%Y-%m-%dT%H:%M:%S')
            duration_sec = max(int((when - started_dt).total_seconds()), 0)
        except ValueError:
            duration_sec = 0

    stored_day = runtime_kv.get_kv(KEY_TODAY, default='', database=database)
    if stored_day != today:
        if stored_day:
            runtime_kv.set_kv(
                KEY_CIRCLES_YESTERDAY,
                runtime_kv.get_kv(
                    KEY_CIRCLES_TODAY, default='0', database=database) or '0',
                database=database)
        runtime_kv.set_kv(KEY_TODAY, today, database=database)
        runtime_kv.set_kv(KEY_CIRCLES_TODAY, '0', database=database)
    circles_today = runtime_kv.incr_kv(KEY_CIRCLES_TODAY, database=database)
    runtime_kv.set_kv(KEY_FINISHED_AT, finished_iso, database=database)
    runtime_kv.set_kv(KEY_DURATION_SEC, str(duration_sec), database=database)
    circles_yesterday = _int_kv(
        KEY_CIRCLES_YESTERDAY, database=database, default=0)

    notified_on = runtime_kv.get_kv(KEY_NOTIFIED_ON, default='', database=database)
    notify = notified_on != today
    if notify:
        runtime_kv.set_kv(KEY_NOTIFIED_ON, today, database=database)

    minutes = duration_sec // 60
    summary = (
        "duration: %s min; today: %s; yesterday: %s"
        % (minutes, circles_today, circles_yesterday))
    return {
        'notify': notify,
        'summary': summary,
        'duration_sec': duration_sec,
        'circles_today': circles_today,
        'circles_yesterday': circles_yesterday,
        'finished_at': finished_iso,
    }


def format_status_lines(database=None):
    """Extra /usersCount lines. Empty if the updater has not finished a circle."""
    finished = runtime_kv.get_kv(KEY_FINISHED_AT, default='', database=database)
    if not finished:
        return ''
    try:
        duration_sec = int(
            runtime_kv.get_kv(KEY_DURATION_SEC, default='0', database=database)
            or 0)
    except ValueError:
        duration_sec = 0
    circles = runtime_kv.get_kv(KEY_CIRCLES_TODAY, default='0', database=database)
    yesterday = runtime_kv.get_kv(
        KEY_CIRCLES_YESTERDAY, default='0', database=database)
    clock = finished[11:16] if len(finished) >= 16 else finished
    return (
        "Последний круг: %s мин (%s)\n"
        "Кругов сегодня: %s\n"
        "Кругов вчера: %s"
        % (duration_sec // 60, clock, circles or '0', yesterday or '0')
    )
