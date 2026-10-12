# -*- coding: utf-8 -*-
"""One episode takes one notification per recipient, and a channel is billed
to its owner: the owner and their channels draw from one budget.

Reuses the temp DB, local feed and enqueue capture of test_updater_not_modified.
Needs the bot's requirements.
Run from the repo root: python app/jobs/test_notify_budget.py
"""
import os
import sys
import threading
from http.server import HTTPServer

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs import test_updater_not_modified as base  # noqa: E402

updater, config, FEED, SENT = base.updater, base.config, base.FEED, base.SENT
OWNER, CHANNEL_A, CHANNEL_B = base.PAYER_A, -1007001, -1007002


def _connections(notify_count):
    db = base.SQLighter(config.db_path)
    try:
        channel = db.get_channel(base.CHANNEL_ID)
        mine = [dict(c) for c in db.get_uccs_by_channel(
            base.CHANNEL_ID, have_subscription=True, notifications_enabled=True)
            if c['user_telegram_id'] == OWNER]
    finally:
        db.close()
    own = dict(mine[0], notify_count=notify_count)
    channels = [dict(own, user_telegram_id=chat_id, user_type='channel', owner_id=OWNER)
                for chat_id in (CHANNEL_A, CHANNEL_B)]
    return channel, [own], channels


def _episode_recipients(notify_count):
    channel, own, channels = _connections(notify_count)
    SENT.clear()
    updater.send_new_records_by_channel(channel, own, tg_channel_connections=channels)
    return [chat for _title, chat_ids in SENT for chat in chat_ids]


def main():
    server = HTTPServer(("127.0.0.1", 0), base._Feed)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    feed_url = "http://127.0.0.1:%d/feed.xml" % server.server_port
    updater.outbox.enqueue = lambda job, **_kwargs: SENT.append((
        job['func_params']['podcastInfo']['title'],
        sorted(job['func_params']['chat_ids'])))
    try:
        for notify_count, expected, label in (
                (1, 1, "1 left: one recipient of three gets Tuesday"),
                (2, 2, "2 left: two of three"),
                (-1, 3, "unlimited: all three"),
                (0, 0, "none left: nobody")):
            FEED["version"] = 1
            base._setup(feed_url)
            base._circle()  # first parse, everyone current
            FEED["version"] = 2
            got = _episode_recipients(notify_count)
            base._assert_eq(len(got), expected, label)
    finally:
        server.shutdown()
    print("all notify budget checks passed")


if __name__ == "__main__":
    main()
