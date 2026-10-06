# -*- coding: utf-8 -*-
"""Where the updater picks up its circle after a start, and whether to alarm.

A deploy (SIGTERM, "Shutdown complete") stops the updater mid-circle every
time. That is not a problem: the channel it was on is processed again (the
cursor and the outbox make that safe) and nobody is alerted. Only a crash
(the supervisor saw the role die) or a circle cut short any other way (an
error caught in the loop, kill -9, OOM of the whole group, power loss) skips that channel, in case it is what killed
the process, and tells the creator.
"""
from db import runtime_kv

CLEAN_STOP_KEY = "updater_clean_stop"


def mark_clean_stop(database=None):
    """Called from the SIGTERM handler of the updater role."""
    runtime_kv.set_kv(CLEAN_STOP_KEY, "1", database=database)


def consume_clean_stop(database=None):
    stopped = runtime_kv.get_kv(CLEAN_STOP_KEY, database=database) == "1"
    runtime_kv.delete_kv(CLEAN_STOP_KEY, database=database)
    return stopped


def resume_point(last_channel_id, crashed, clean_stop):
    """(channel id to start the circle from, alert text or None)."""
    if crashed:
        return last_channel_id + 1, (
            "#restarted\nUpdater упал на канале %d, пропускаю его" % last_channel_id)
    if last_channel_id == 1:
        return 1, None
    if clean_stop:
        return last_channel_id, None
    return last_channel_id + 1, (
        "#restarted\nКруг прерван не штатно на канале %d (ошибка круга, kill, "
        "OOM, перезагрузка сервера), пропускаю его" % last_channel_id)
