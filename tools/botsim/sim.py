# -*- coding: utf-8 -*-
"""botsim: the bot, run in this process against a fake Telegram (README.md).

boot() must run before anything else of the bot is imported: the bot reads
config.db_path at import time. It points the bot at a database (a fresh one
from schema.sql, or a copy of a real one you pass), puts FakeBotApi in place
of telebot's request function, a fake Telethon client in place of the
agent, records Amplitude events instead of sending them, and registers the
real handlers (app/routes/initialize_routes). Then BotSim is a user:

    sim = BotSim(user_id=1001, lang='ru')
    step = sim.send('/start')        # a message
    step = sim.tap('Пересказ')       # a button of the bot's latest message that has it
    step = sim.send_file('subs.opml', data)
    step = sim.deliver()             # the episodes the taps queued, as the send workers would
    step = sim.run_ai()              # the summaries queued (fake model unless ai='real')
    print(step)                      # what the user saw change, handlers, toasts, warnings

Every incoming update runs synchronously through the real dispatcher
(TheSender._serve_locked): middlewares, routes, state store, database.
"""
import asyncio
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import types
from dataclasses import dataclass, field
from typing import Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tools.botsim import fake_telegram  # noqa: E402
from tools.botsim.fake_telegram import Sent  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
FAKE_TRANSCRIPT = '[0:00] The host opens the episode. [0:30] The guest explains the main idea. [1:00] Advice.'
FAKE_SUMMARY = 'The episode in one sentence (botsim).\n0:00 – the opening\n0:30 – the main idea'
FAKE_ANSWER = 'At 0:30 the guest explains it (botsim).'
# a question about a whole show: it cites the newest episodes by their labels (show_ask.cite)
FAKE_SHOW_ANSWER = 'The host mostly talks about the latest topics [E1], and once went deeper on it [E2, E1].'
# threads that live as long as the process: never waited for
_LONG_LIVED = ('__thread_processor', 'Telebot Balancer', 'heartbeat')

_state: dict = {}


class SimNetworkBlocked(ConnectionError):
    pass


def boot(database: Optional[str] = None, network: bool = True, ai: str = 'fake', quiet: bool = True) -> dict:
    """Start the bot against a fake Telegram. `database`: a file to use as is (a copy of a real
    one: the bot writes to it), None for a fresh one from schema.sql. `network`: False blocks
    HTTP (catalog, feeds). `ai`: 'fake' (no model calls, a canned summary), 'real' (constants'
    OpenRouter key, costs money) or 'off'. Once per process."""
    if _state:
        return _state
    if any(name in sys.modules for name in ('db.sqliteAdapter', 'app.routes.initialize_routes')):
        raise RuntimeError('boot() must run before the bot is imported: it reads config.db_path at import')
    if database is None:
        directory = tempfile.mkdtemp(prefix='botsim_')
        database = os.path.join(directory, 'sim.db')
        import sqlite3
        connection = sqlite3.connect(database)
        connection.executescript(open(SCHEMA, encoding='utf-8').read())
        connection.close()
        _state['tmp'] = directory

    import config
    config.db_path = database
    config.maintenance = False
    # feed copies and episode downloads go under work_dir: a scratch one, not the checkout
    scratch = tempfile.mkdtemp(prefix='botsim_work_')
    os.makedirs(os.path.join(scratch, 'records'))
    config.work_dir = scratch
    _state['work'] = scratch

    client = fake_telegram.FakeClient()
    agent = types.ModuleType('agent.bot_telethon')
    agent.thobot_session_handler, agent.thonbot = '', client
    agent.send_uploaded = agent.upload = _no_agent
    sys.modules['agent.bot_telethon'] = agent
    import agent as agent_package
    agent_package.bot_telethon = agent

    api = fake_telegram.FakeBotApi()
    from telebot import apihelper
    apihelper._make_request = api

    analytics: list = []
    from lib.analytics import analytics as analytics_module
    analytics_module.AmplitudeAnalytics.event = (
        lambda self, user_id, event_type, platform=None, user_properties=None, event_properties=None:
        analytics.append((event_type, user_id, dict(event_properties or {}))))
    # the bot role makes the singleton at start (main.run_bot); here its queue runs each event at once
    tracker = analytics_module.Analytics(analytics_module.AmplitudeAnalytics('botsim'), test_mode=False)
    tracker.queue = types.SimpleNamespace(put=lambda item: item[0](item[1]))

    log: list = []
    from lib.tools import logger as logger_module

    def out_log(self, *args, level='log'):
        line = ' '.join(str(arg) for arg in args)
        log.append((level, line))
        if not quiet or level == 'err':
            print('[%s] %s' % (level.upper(), line), flush=True)
    logger_module.Logger._Logger__out_log = out_log

    if not network:
        import requests

        def blocked(self, method, url, *args, **kwargs):
            raise SimNetworkBlocked('botsim: network is off (%s %s)' % (method, url))
        requests.sessions.Session.request = blocked

    from app.service.ai import summary
    if ai == 'fake':
        summary.enabled = lambda: True
        summary.summarize = lambda *args, **kwargs: (FAKE_SUMMARY, 0.0)
        summary.answer = lambda *args, **kwargs: (FAKE_ANSWER, 0.0)
        from app.service.ai import show_ask
        show_ask.answer = lambda *args, **kwargs: (FAKE_SHOW_ANSWER, 0.0)
    elif ai == 'off':
        summary.enabled = lambda: False

    from db.tariff_rows import ensure_tariff_rows
    ensure_tariff_rows()  # as the supervisor does at start: every user has a tariff row

    from app.core.balancers import telebotAnswerer
    worker = telebotAnswerer.TheSender.__new__(telebotAnswerer.TheSender)
    worker.threads_to_watch = []

    class Balancer(threading.Thread):
        """handle_event_in_thread's target: serves the update now, in this thread."""
        main_queue = types.SimpleNamespace(put=lambda params: worker._serve_locked(params))

        def is_alive(self):
            return True

    from app.routes import initialize_routes
    initialize_routes.initialize_routes(Balancer(), None, [])
    initialize_routes.t_answer_sender = Balancer()

    _state.update(database=database, client=client, api=api, analytics=analytics, log=log, ai=ai)
    return _state


def _no_agent(*args, **kwargs):
    raise RuntimeError('botsim: no Telethon agent (an upload over 50 MB)')


def shutdown():
    """Remove what boot() made: the fresh database and the scratch work_dir (a database you passed stays)."""
    for key in ('tmp', 'work'):
        if _state.get(key):
            shutil.rmtree(_state[key], ignore_errors=True)


@dataclass
class Step:
    """What one action of the user changed."""
    action: str
    new: list = field(default_factory=list)  # Sent
    edited: list = field(default_factory=list)  # Sent, as it is now
    deleted: list = field(default_factory=list)  # message ids
    toasts: list = field(default_factory=list)  # (text, alert)
    handlers: list = field(default_factory=list)
    analytics: list = field(default_factory=list)  # (event, user id, properties)
    warnings: list = field(default_factory=list)  # WARN / ERR log lines
    other_chats: list = field(default_factory=list)  # Sent to someone else (the creator's notices)
    seconds: float = 0.0

    @property
    def texts(self) -> list:
        return [m.text for m in self.new + self.edited]

    @property
    def errors(self) -> list:
        return [line for level, line in self.warnings if level == 'err']

    def __str__(self):
        lines = ['>>> %s  (%.1f s)' % (self.action, self.seconds)]
        if self.handlers:
            lines.append('    handlers: ' + ', '.join(self.handlers))
        for label, messages in (('new', self.new), ('edited', self.edited)):
            for message in messages:
                lines.append(render(message, label))
        for message_id in self.deleted:
            lines.append('  [deleted #%s]' % message_id)
        for text, alert in self.toasts:
            if text:  # a tap answered without a word only stops the spinner
                lines.append('  [%s] %s' % ('alert' if alert else 'toast', text))
        for message in self.other_chats:
            lines.append(render(message, 'to chat %s' % message.chat_id))
        for event, _, properties in self.analytics:
            lines.append('  amplitude: %s %s' % (event, properties or ''))
        for level, line in self.warnings:
            lines.append('  %s: %s' % (level.upper(), line[:300]))
        return '\n'.join(lines)


def render(message: Sent, label: str = '') -> str:
    head = '  [%s #%d %s%s]' % (label, message.message_id, message.kind,
                                ' reply to #%d' % message.reply_to if message.reply_to else '')
    text = re.sub(r'\n{3,}', '\n\n', message.text or '')
    lines = [head] + ['    ' + line for line in text.splitlines()]
    if message.kind not in ('text', 'rich') and message.extra.get('source'):
        lines.append('    (%s: %s)' % (message.kind, str(message.extra['source'])[:120]))
    for row in message.buttons:
        lines.append('    ' + '  '.join('[%s%s]' % (button.get('text'), ' -> ' + button['url'] if button.get('url')
                                                       else '') for button in row))
    return '\n'.join(lines)


class BotSim:
    """One user of the bot. Every action returns a Step."""

    def __init__(self, user_id: int = 1001, lang: str = 'en', settle_seconds: float = 180):
        if not _state:
            raise RuntimeError('call botsim.boot() first')
        self.user_id, self.lang, self.settle_seconds = int(user_id), lang, settle_seconds
        self.api, self.client = _state['api'], _state['client']

    # --- what the user sees ----------------------------------------------------
    def chat(self) -> list:
        return self.api.chat(self.user_id)

    def last(self, with_buttons: bool = False) -> Optional[Sent]:
        for message in reversed(self.chat()):
            if message.from_bot and (message.buttons or not with_buttons):
                return message
        return None

    def screen(self, count: int = 3) -> str:
        return '\n'.join(render(m, 'bot' if m.from_bot else 'you') for m in self.chat()[-count:])

    # --- what the user does ------------------------------------------------------
    def send(self, text: str) -> Step:
        message = self._user_message(text)
        event = fake_telegram.NewMessageEvent(self.user_id, message, self.lang)
        return self._run('send %r' % text, event)

    def send_file(self, name: str, data: bytes, mime_type: str = 'application/octet-stream') -> Step:
        message = self._user_message('', document=object(), file=fake_telegram.FakeFile(name, mime_type, len(data)),
                                     data=data)
        event = fake_telegram.NewMessageEvent(self.user_id, message, self.lang)
        return self._run('file %s (%d bytes)' % (name, len(data)), event)

    def tap(self, button, message: Optional[Sent] = None) -> Step:
        """`button`: its text (or part of it), or (row, column). The message: the bot's latest
        one that has that button, unless given."""
        target, chosen = self._find_button(button, message)
        data = chosen.get('callback_data')
        if data is None:
            raise ValueError('%r is not a callback button: %r' % (button, chosen))
        bot_message = fake_telegram.FakeMessage(target.message_id, self.user_id, target.text, sender_lang=None)
        event = fake_telegram.CallbackEvent(self.user_id, str(data).encode('utf-8'), bot_message, self.lang)
        return self._run('tap %r on #%d' % (chosen.get('text'), target.message_id), event)

    def tap_data(self, data: str, message: Optional[Sent] = None) -> Step:
        """A tap with this callback data (an old button, a crafted one) on `message` or the latest."""
        target = message or self.last() or Sent(0, self.user_id, 'text')
        bot_message = fake_telegram.FakeMessage(target.message_id, self.user_id, target.text)
        event = fake_telegram.CallbackEvent(self.user_id, data.encode('utf-8'), bot_message, self.lang)
        return self._run('tap data %s' % data, event)

    def deliver(self, by_url: bool = True) -> Step:
        """The episodes queued, sent now as the send workers would. `by_url`: every file goes as
        its URL (Telegram would fetch it; nothing is downloaded); False runs the real size rules:
        a download, a Bot API upload up to 50 MB, and no agent for bigger ones."""
        def work():
            from app.controller.builders import recsModule
            from app.core.sender import outbox, send_record_helper
            if by_url:
                send_record_helper.fetch_by_url_first = lambda size_mb: True
            else:
                from app.service.record import delivery
                send_record_helper.fetch_by_url_first = delivery.fetch_by_url_first
            for action in ('rec', 'circle'):
                while True:
                    job = outbox.claim(action=action)
                    if job is None:
                        break
                    try:
                        recsModule.send_record_thread(job, None)
                        outbox.mark_done(job['outbox_id'], attempts=job.get('outbox_attempts'))
                    except Exception as e:
                        outbox.fail_or_retry(job['outbox_id'], error=e, attempts=job.get('outbox_attempts'))
                        raise
        return self._observe('deliver', work)

    def run_ai(self) -> Step:
        """The summaries queued, made now as the jobs process would (ai='fake': a canned one)."""
        def work():
            import requests
            from app.jobs import ai_watcher
            from app.service.ai import transcript
            from db import ai
            if _state['ai'] == 'fake':
                def fake_transcript(episode, session, progress=None):
                    cached = ai.transcript(episode['ref'])
                    if cached is None:  # cached as the real one is: questions read it
                        ai.save_transcript(episode['ref'], FAKE_TRANSCRIPT, 'feed', 0.0, 600)
                    return transcript.Transcript(FAKE_TRANSCRIPT, 'feed', 0.0, 600)
                ai_watcher.episode_transcript = fake_transcript
            session = requests.Session()
            while True:
                request = ai.claim()
                if request is None:
                    break
                try:
                    ai.finish(request['id'], 'done', seconds=ai_watcher.process(request, session))
                except Exception as e:
                    ai.retry_or_fail(request)
                    _state['log'].append(('err', 'botsim run_ai: %s %s' % (type(e).__name__, e)))
        return self._observe('run_ai', work)

    # --- plumbing -------------------------------------------------------------------
    def _user_message(self, text, **kwargs) -> fake_telegram.FakeMessage:
        message_id = self.api.next_id()
        self.api.add(Sent(message_id, self.user_id, 'file' if kwargs.get('file') else 'text', text, from_bot=False))
        return fake_telegram.FakeMessage(message_id, self.user_id, text, sender_lang=self.lang, **kwargs)

    def _find_button(self, button, message):
        candidates = [message] if message is not None else [m for m in reversed(self.chat())
                                                            if m.from_bot and m.buttons]
        for candidate in candidates:
            if isinstance(button, tuple):
                row, column = button
                try:
                    return candidate, candidate.buttons[row][column]
                except IndexError:
                    continue
            for row in candidate.buttons:
                for chosen in row:
                    if chosen.get('text') == button:
                        return candidate, chosen
            for row in candidate.buttons:
                for chosen in row:
                    if str(button).lower() in str(chosen.get('text', '')).lower():
                        return candidate, chosen
        raise LookupError('no button %r in the chat; latest: %s' % (
            button, candidates[0].button_texts() if candidates else []))

    def _run(self, label, event) -> Step:
        handlers = []

        def work():
            handlers.extend(asyncio.run(fake_telegram.dispatch(self.client, event)))
        step = self._observe(label, work)
        step.handlers = handlers
        return step

    def _observe(self, label, work) -> Step:
        api, started = self.api, time.time()
        before = {m.message_id: (m.text, m.buttons, m.kind) for m in self.api.chat(self.user_id)}
        seen = set(api.messages)
        toasts, analytics, log = len(api.toasts), len(_state['analytics']), len(_state['log'])
        threads = set(threading.enumerate())
        work()
        self._settle(threads)
        step = Step(label, seconds=time.time() - started)
        for message in self.api.chat(self.user_id):
            if message.message_id not in before:
                if message.from_bot:
                    step.new.append(message)
            elif before[message.message_id] != (message.text, message.buttons, message.kind):
                step.edited.append(message)
        step.deleted = [message_id for message_id in before
                        if api.messages.get((self.user_id, message_id)) is None
                        or api.messages[(self.user_id, message_id)].deleted]
        step.other_chats = [m for key, m in api.messages.items() if key not in seen and m.chat_id != self.user_id]
        step.toasts = api.toasts[toasts:]
        step.analytics = _state['analytics'][analytics:]
        step.warnings = [(level, line) for level, line in _state['log'][log:] if level in ('warn', 'err')]
        return step

    def _settle(self, before):
        """Wait for the threads the action started (an OPML import, a catalog search)."""
        deadline = time.time() + self.settle_seconds
        while time.time() < deadline:
            pending = [t for t in threading.enumerate() if t not in before and t.is_alive()
                       and not any(name in t.name for name in _LONG_LIVED)]
            if not pending:
                return
            time.sleep(0.1)
