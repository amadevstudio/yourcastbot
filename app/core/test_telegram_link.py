# -*- coding: utf-8 -*-
"""After an outage the creator hears how long Telegram was gone and how often the
roles exited meanwhile: the "#problem" lines sent during it were lost.

Run from the repo root: python app/core/test_telegram_link.py
"""
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core import telegram_link  # noqa: E402

DAY = time.mktime((2026, 10, 30, 14, 0, 0, 0, 0, -1))


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class Run:
    """A watch driven by a list of probe answers, one per minute."""

    def __init__(self, sends_ok=True):
        self.answers = []
        self.clock = DAY
        self.sent = []
        self.sends_ok = sends_ok
        self.watch = telegram_link.LinkWatch(probe=self._probe, send=self._send, now=lambda: self.clock)

    def _probe(self):
        return self.answers.pop(0)

    def _send(self, text, level):
        self.sent.append((text, level))
        return self.sends_ok

    def ticks(self, *answers):
        for answer in answers:
            self.answers.append(answer)
            self.watch.tick()
            self.clock += 60


def main():
    run = Run()
    run.ticks(True, False, True, True)
    _assert(run.sent == [], "a blip (one failed probe, no exit) says nothing")

    run = Run()
    run.watch.child_exited("bot", 1)
    run.ticks(True, False, False)
    run.watch.child_exited("bot", 1)
    run.watch.child_exited("bot", 1)
    run.watch.child_exited("updater", 1)
    run.ticks(False, True, True)
    _assert(len(run.sent) == 1, "an outage is one message, once")
    text, level = run.sent[0]
    _assert(level == 'warning', "as a problem")
    _assert(text.startswith("Не было связи с Telegram с 14:01 до 14:04 (3 мин)."), "since and until: " + text)
    _assert("bot 2, updater 1" in text, "the exits during it, not the one before")

    run = Run()
    run.ticks(False)
    run.watch.child_exited("bot", 1)
    run.ticks(True)
    _assert(len(run.sent) == 1 and "bot 1" in run.sent[0][0], "one failed probe with a role exit is an outage")

    run = Run(sends_ok=False)
    run.ticks(False, False, True)
    _assert(len(run.sent) == 1, "the line is tried when the link is back")
    run.sends_ok = True
    run.ticks(True, True)
    _assert(len(run.sent) == 2 and run.sent[1] == run.sent[0], "a line that did not go goes with the next probe")
    _assert(run.watch.pending is None, "and then never again")
    _assert("Роли не перезапускались" in run.sent[0][0], "an outage without exits says so")

    run = Run()
    run.watch.child_exited(None, None)
    run.watch.exits = None  # a broken state must not reach the supervisor's loop
    run.watch.down_since = DAY
    run.watch.child_exited("bot", 1)
    _assert(True, "an exit the watch cannot count never raises")

    _assert(telegram_link.outage_text(DAY - 3600 * 15, DAY, {}).startswith(
        "Не было связи с Telegram с 29.10 23:00 до 14:00 (900 мин)."), "another day carries its date")

    import requests
    saved = requests.get
    try:
        def refuse(url, timeout):
            raise requests.ConnectionError("Max retries exceeded with url: " + url)
        requests.get = refuse
        _assert(telegram_link.bot_api_answers(token="0:test") is False, "no connection: no link")
        for status, answered in ((200, True), (401, True), (502, False)):
            requests.get = lambda url, timeout, status=status: type("Reply", (), {"status_code": status})()
            _assert(telegram_link.bot_api_answers(token="0:test") is answered, "getMe answered %d" % status)
    finally:
        requests.get = saved
    print("all telegram link checks passed")


if __name__ == "__main__":
    main()
