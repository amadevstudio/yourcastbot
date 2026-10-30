# -*- coding: utf-8 -*-
"""The creator hears that the server lost Telegram, once it is back.

On 2026-10-30 the server's network was gone for 25 minutes: the bot role
exited 14 times (Telethon gives up after 5 reconnects) and every "#problem"
about it was sent into the outage and lost, so the creator heard nothing.
The supervisor (one process, it outlives the roles) asks the Bot API's getMe
every minute; when it answers again after an outage, the creator gets one
line: since when, until when, how many times each role exited meanwhile. A
blip (one failed probe, no role exit) says nothing. A line that cannot go
stays and goes with the next probe that answers. In memory: a restart of the
supervisor forgets an outage (start_notice says whether that stop was clean).
On the server only, in a thread of its own: it never delays or fails a start.
Lock: python app/core/test_telegram_link.py
"""
import threading
import time

from lib.tools.logger import logger

PROBE_SECONDS = 60
PROBE_TIMEOUT = 10
MIN_FAILED = 2  # probes in a row: one timeout is a slow answer, not an outage


def bot_api_answers(token=None) -> bool:
    """getMe answered: any reply below 500 (a refused token is still a link)."""
    import requests
    if token is None:
        import config
        token = config.token
    try:
        reply = requests.get("https://api.telegram.org/bot%s/getMe" % token, timeout=PROBE_TIMEOUT)
    except requests.RequestException:
        return False  # the error names the URL, and the URL holds the token: never logged
    return reply.status_code < 500


def _clock(stamp, ref) -> str:
    """'14:21', or '29.10 23:50' when it is not ref's day."""
    moment, day = time.localtime(stamp), time.localtime(ref)
    if (moment.tm_year, moment.tm_yday) == (day.tm_year, day.tm_yday):
        return time.strftime("%H:%M", moment)
    return time.strftime("%d.%m %H:%M", moment)


def outage_text(since, until, exits) -> str:
    minutes = max(1, int(round((until - since) / 60.0)))
    text = "Не было связи с Telegram с %s до %s (%d мин)." % (
        _clock(since, until), _clock(until, until), minutes)
    if exits:
        return text + "\nПерезапуски ролей за это время: " + ", ".join(
            "%s %d" % (role, n) for role, n in sorted(exits.items()))
    return text + "\nРоли не перезапускались."


class LinkWatch:
    def __init__(self, probe=bot_api_answers, send=None, now=time.time):
        self.probe = probe
        self.send = send
        self.now = now
        self.down_since = None
        self.failed = 0
        self.exits = {}
        self.pending = None  # an outage's line not delivered yet
        self._lock = threading.Lock()

    def child_exited(self, role, code):
        """The supervisor's on_child_exit: an exit while the link is down is counted.
        Never raises into the supervisor's loop."""
        try:
            with self._lock:
                if self.down_since is not None:
                    self.exits[role] = self.exits.get(role, 0) + 1
        except Exception as e:
            logger.err("Telegram link watch, child exit:", type(e).__name__, e)

    def tick(self):
        answered = self.probe()
        now = self.now()
        with self._lock:
            if not answered:
                if self.down_since is None:
                    self.down_since = now
                    logger.warn("Telegram link: the Bot API does not answer")
                self.failed += 1
                return
            if self.down_since is not None:
                if self.failed >= MIN_FAILED or self.exits:
                    text = outage_text(self.down_since, now, self.exits)
                    self.pending = text if self.pending is None else self.pending + "\n\n" + text
                logger.log("Telegram link back after", self.failed, "failed probes, exits", self.exits)
                self.down_since, self.failed, self.exits = None, 0, {}
            text = self.pending
        if text is None:
            return
        send = self.send
        if send is None:
            from app.controller.builders.adminModule import send_message_to_creator as send
        if send(text, level='warning'):
            with self._lock:
                if self.pending == text:
                    self.pending = None


def _loop(watch, interval):
    while True:
        try:
            watch.tick()
        except Exception as e:
            logger.err("Telegram link watch:", type(e).__name__, e)
        time.sleep(interval)


def start_watch():
    """The supervisor's on_child_exit with the watch running, or None off the server."""
    try:
        import config
        if not config.server:
            return None
        watch = LinkWatch()
        threading.Thread(target=_loop, args=(watch, PROBE_SECONDS), name="Telegram link", daemon=True).start()
        return watch.child_exited
    except Exception as e:
        logger.err("Telegram link watch not started:", type(e).__name__, e)
        return None
