# -*- coding: utf-8 -*-
"""Send balancer: a worker stuck on a call that never returns loses its slot.

No Telegram: Telethon, recsModule and podcastsUpdater are stubbed, the
outbox uses a temp DB. Runs in the CD gate.
Run from the repo root: python app/core/balancers/test_record_balancer.py
"""
import os
import queue
import sys
import tempfile
import threading
import time
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config  # noqa: E402

_PROD_DB = config.db_path
config.db_path = os.path.join(tempfile.mkdtemp(prefix="yourcast_balancer_"), "t.db")
if os.path.abspath(config.db_path) == os.path.abspath(_PROD_DB):
    raise AssertionError("refusing to use production yourcast.db")


class _Client:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self, **_kwargs):
        return self

    def disconnect(self):
        pass


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


_stub("telethon", TelegramClient=_Client)
_stub("telethon.sessions", StringSession=lambda *_args: None)
_stub("agent.bot_telethon", thobot_session_handler="")
_stub("app.controller.builders.recsModule")
_stub("app.jobs.podcastsUpdater")

from app.core.sender import outbox  # noqa: E402
from app.core.balancers import recordSender  # noqa: E402

if os.path.abspath(outbox.db_path) != os.path.abspath(config.db_path):
    raise AssertionError("outbox must use the temp DB")


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _rec_job(chat_id):
    return {
        'action': 'rec',
        'user_id': chat_id,
        'func_params': {
            'link': 'https://example.com/ep.mp3',
            'chat_ids': {chat_id: {}},
            'utglangs': {chat_id: 'en'},
            'bitratestg': {chat_id: 64},
            'podcastInfo': {
                'id': 7, 'title': 'Episode', 'chName': 'Show',
                'recordUniqId': 'ep-%s' % chat_id,
            },
        },
    }


def _balancer():
    balancer = recordSender.RecordBalancer(queue.Queue())
    fills = []
    balancer._fill_idle = lambda: fills.append(1)
    return balancer, fills


def test_sender_reports_its_job():
    balancer, _fills = _balancer()
    sender = balancer.threads['update'][0]
    running, release = threading.Event(), threading.Event()
    seen = []

    def process_input(input_data, _thonbot):
        seen.append(sender.current_outbox_id)
        running.set()
        release.wait(2)

    sender.process_input = process_input
    sender.resume()
    balancer.queues['update'][0].put({'action': 'update', 'outbox_id': 41})
    running.wait(2)
    _assert_eq(seen, [41], "a worker names the outbox row it is on")
    release.set()
    deadline = time.time() + 2
    while sender.current_outbox_id is not None and time.time() < deadline:
        time.sleep(0.01)
    _assert_eq(sender.current_outbox_id, None, "and forgets it when the job ends")


def test_heartbeat_reports_stalled_jobs():
    balancer, _fills = _balancer()
    while not balancer.main_queue.empty():
        balancer.main_queue.get_nowait()
    outbox_id = outbox.enqueue(_rec_job(5101), dispatch=False)
    job = outbox.claim(action='rec')
    _assert_eq(job['outbox_id'], outbox_id, "claimed")
    balancer._heartbeat_once()
    _assert_eq(balancer.main_queue.empty(), True, "a live job is not reported")
    balancer._heartbeat_once(now=time.monotonic() + outbox.STALL_SECONDS + 1)
    _assert_eq(balancer.main_queue.get_nowait(),
               {'action': 'stalled', 'ids': [outbox_id]},
               "a job silent for STALL_SECONDS goes to the balancer thread")


def test_stuck_slot_gets_a_fresh_thread():
    balancer, fills = _balancer()
    stuck = balancer.threads['rec'][1]
    old_queue = balancer.queues['rec'][1]
    stuck.current_outbox_id = 77
    stuck.paused = False  # inside a call that never returns
    other = balancer.threads['rec'][0]
    other.current_outbox_id = 78
    other.paused = False
    _assert_eq(balancer._slot_idle('rec', 1), False, "a stuck slot is never idle")
    del fills[:]
    balancer._dispatch({'action': 'stalled', 'ids': [77]})
    fresh = balancer.threads['rec'][1]
    _assert_eq(fresh is stuck, False, "the stuck slot gets a fresh thread")
    _assert_eq(balancer.queues['rec'][1] is old_queue, False, "and a fresh queue")
    _assert_eq(stuck.thread_queue is old_queue, True,
               "the stuck thread keeps the old queue: it never takes new work")
    _assert_eq(fresh.is_alive(), True, "the fresh thread runs")
    _assert_eq(balancer._slot_idle('rec', 1), True, "the slot is idle again")
    _assert_eq(balancer.threads['rec'][0] is other, True, "a busy live slot is left alone")
    _assert_eq(fills, [1], "and the balancer claims into the freed slot")
    other.current_outbox_id = None
    other.paused = True


def main():
    for case in (
            test_sender_reports_its_job,
            test_heartbeat_reports_stalled_jobs,
            test_stuck_slot_gets_a_fresh_thread):
        print("-- %s" % case.__name__)
        case()
    print("all record balancer checks passed")


if __name__ == "__main__":
    main()
