# -*- coding: utf-8 -*-
"""Episode delivery: what Sender does with a file of a given size.

Real Sender, fake network: Telegram, the agent, HTTP and the disk are
stand-ins. telebot/telethon/pydub/mutagen are replaced before import so the
check runs without prod secrets or those packages.

Run from the repo root: python app/core/sender/test_record_delivery.py
"""
import importlib.util
import os
import sys
import tempfile
import time
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MB = 1024 * 1024


class _InertModule(types.ModuleType):
    """Unknown attributes are inert classes: import-time names resolve, nothing runs."""

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        value = type(name, (), {
            '__init__': lambda self, *a, **k: None,
            '__getattr__': lambda self, attr: (lambda *a, **k: None),
        })
        setattr(self, name, value)
        return value


def _install_fake(name):
    parts = name.split('.')
    for i in range(1, len(parts) + 1):
        module_name = '.'.join(parts[:i])
        module = sys.modules.get(module_name)
        if not isinstance(module, _InertModule):
            module = _InertModule(module_name)
            sys.modules[module_name] = module
        if i > 1:
            setattr(sys.modules['.'.join(parts[:i - 1])], parts[i - 1], module)


class ApiException(Exception):
    pass


class ApiTelegramException(ApiException):
    pass


# Network and media clients are always fakes here; plain libraries only when absent.
for _name in ('telebot.apihelper', 'telebot.types', 'telethon.sessions', 'telethon.tl.types',
              'pydub', 'mutagen'):
    _install_fake(_name)
sys.modules['telebot.apihelper'].ApiException = ApiException
sys.modules['telebot.apihelper'].ApiTelegramException = ApiTelegramException
_OPTIONAL = ('requests.adapters', 'urllib3.exceptions', 'urllib3.util.retry')
_absent = {name.split('.')[0] for name in _OPTIONAL if importlib.util.find_spec(name.split('.')[0]) is None}
for _name in _OPTIONAL:
    if _name.split('.')[0] in _absent:
        _install_fake(_name)

from app.core.sender import outbox as real_outbox  # noqa: E402
from app.core.sender import send_record_helper as srh  # noqa: E402
from lib.net.enclosure import host_from_error  # noqa: E402
from lib.system.disk_budget import DiskBudget, DiskBusy  # noqa: E402


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _ns(**kw):
    return types.SimpleNamespace(**kw)


class FakeLogger:
    def __init__(self):
        self.lines = []

    def _add(self, level, *args):
        self.lines.append((level, " ".join(str(a) for a in args)))

    def log(self, *args):
        self._add('log', *args)

    def warn(self, *args):
        self._add('warn', *args)

    def err(self, *args, **kwargs):
        self._add('err', *args)

    def debug(self, *args):
        pass


class FakeBot:
    """Bot API. Telegram refuses the URL when url_error is set."""

    def __init__(self, url_error=None, flood_chat=None, refuse_chat=None,
                 blocked_chat=None, flood_once_chat=None):
        self.url_error = url_error
        self.flood_chat = flood_chat
        self.refuse_chat = refuse_chat
        self.blocked_chat = blocked_chat
        self.flood_once_chat = flood_once_chat
        self.audio = []  # (chat_id, 'url' | 'upload' | 'file_id')

    def send_audio(self, chat_id, audio, **kwargs):
        if chat_id == self.blocked_chat:
            self.audio.append((chat_id, 'blocked'))
            raise ApiTelegramException("Forbidden: bot was blocked by the user")
        if chat_id == self.flood_once_chat:
            self.flood_once_chat = None
            self.audio.append((chat_id, 'flood'))
            raise ApiTelegramException("Too Many Requests: retry after 1")
        if isinstance(audio, str) and audio.startswith('http'):
            self.audio.append((chat_id, 'url'))
            if self.url_error:
                raise ApiTelegramException(self.url_error)
            return _ns(audio=_ns(file_id='URL_FID'))
        kind = 'upload' if hasattr(audio, 'read') else 'file_id'
        self.audio.append((chat_id, kind))
        if chat_id == self.flood_chat:
            raise ApiTelegramException("Too Many Requests: retry after 5")
        if chat_id == self.refuse_chat:
            raise ApiTelegramException("Bad Request: not enough rights to send audio")
        return _ns(audio=_ns(file_id='BOT_FID'))

    def send_message(self, *args, **kwargs):
        pass

    def forward_message(self, chat_id, from_chat_id, message_id):
        return _ns(audio=_ns(file_id='AGENT_FID'), document=None, message_id=99)

    def delete_message(self, *args, **kwargs):
        pass


class FakeAgent:
    def __init__(self, unreachable_chat=None):
        self.uploads = 0
        self.sent_to = []
        self.unreachable_chat = unreachable_chat

    def upload(self, thonbot, fname, callback=None):
        self.uploads += 1
        return 'INPUT_FILE'

    def send_uploaded(self, thonbot, data, file):
        if data['chat_id'] == self.unreachable_chat:
            raise ValueError("Could not find the input entity for PeerUser")
        self.sent_to.append(data['chat_id'])
        return {'message_id': 1, 'chat_id': data['chat_id']}


class FakeRequester:
    def __init__(self, size_bytes, download_error=None, size_known=True):
        self.size = size_bytes
        self.download_error = download_error
        self.size_known = size_known
        self.downloads = 0

    def get_headers(self, link, **kwargs):
        if not self.size_known:
            return {'Content-Type': 'audio/mpeg'}
        return {'Content-Type': 'audio/mpeg', 'Content-Length': str(self.size)}

    get_headers_with_pre_download = get_headers

    def download_chunked(self, url, destination, callback=None, **kwargs):
        self.downloads += 1
        if self.download_error:
            raise RuntimeError(self.download_error)
        with open(destination, 'wb') as f:
            f.truncate(self.size)  # sparse: the size without the bytes
        if callback is not None:
            callback(self.size, self.size)


class FakeOutbox:
    OutboxRetryableError = real_outbox.OutboxRetryableError
    MAX_ATTEMPTS = real_outbox.MAX_ATTEMPTS
    TOUCH_MIN_INTERVAL_SECONDS = 30

    def __init__(self):
        self.done = False

    def touch(self, *args, **kwargs):
        pass

    def mark_done(self, *args, **kwargs):
        self.done = True

    def update_rec_recipients(self, *args, **kwargs):
        return 1


class World:
    """Everything Sender talks to, recorded."""

    def __init__(self, size_mb, url_error=None, download_error=None,
                 disk_free_mb=10_000, reserved_mb=0, with_outbox=False, flood_chat=None,
                 agent_unreachable_chat=None, bot_refuse_chat=None,
                 blocked_chat=None, flood_once_chat=None, size_known=True, trust_rss=False):
        self.tmp = tempfile.mkdtemp(prefix="yourcast_delivery_")
        os.makedirs(os.path.join(self.tmp, "records"))
        self.bot = FakeBot(url_error, flood_chat, bot_refuse_chat, blocked_chat, flood_once_chat)
        self.blocked_marked = []
        self.slept = []
        self.agent = FakeAgent(agent_unreachable_chat)
        self.requester = FakeRequester(int(size_mb * MB), download_error, size_known)
        self.budget = DiskBudget(self.tmp, min_free_bytes=0, disk_free=lambda: disk_free_mb * MB)
        if reserved_mb:
            self.budget.reserve(reserved_mb * MB)
        self.logger = FakeLogger()
        self.outbox = FakeOutbox() if with_outbox else real_outbox
        self.notices = []  # (chat_id, text) for too big / unavailable
        self.cooled = []  # (link, error) passed to the enclosure cooldown

        def notice(chat_id, structures, *args, **kwargs):
            self.notices.append((chat_id, structures[0]['text']))
            return []

        patches = {
            'bot': self.bot, 'bot_telethon': self.agent, 'requester': self.requester,
            'disk_budget': self.budget, 'logger': self.logger, 'work_dir': self.tmp,
            'outbox': self.outbox, 'storageChatId': 42,
            'storage': _ns(enclosure_host_is_cool=lambda link: False,
                           mark_enclosure_host_cool=self._cool_host,
                           set_user_resend_flag=lambda chat_id: None),
            'telegram_cache': _ns(get_file_id=lambda link, kind: None,
                                  add_file_id=lambda *a, **k: None),
            'space': _ns(memory_stat=lambda: b'', top=lambda: b'', storage_stat=lambda: b''),
            'outer_sender': notice, 'render_messages': notice,
            'message_editor': lambda *a, **k: None, 'message_deleter': lambda *a, **k: None,
            'trust_rss_podcasts': trust_rss,
            'bot_blocked_reaction': self._blocked_reaction,
            'bot_removed_from_channel_reaction': lambda error, chat_id: False,
            'time': _ns(sleep=self.slept.append, time=time.time, time_ns=time.time_ns),
        }
        for name, value in patches.items():
            setattr(srh, name, value)

    def _cool_host(self, link, error=None, **kwargs):
        self.cooled.append((link, error))

    def _blocked_reaction(self, error, chat_id):
        if "bot was blocked" in str(error):
            self.blocked_marked.append(chat_id)
            return True
        return False

    def sender(self, chats=(1, 2, 3), itunes_listed=True):
        podcast_info = {
            'id': 28, 'title': 'Record Club #1', 'descr': 'Mix.', 'itunesLink': '',
            'channelLink': 'https://radiorecord.ru', 'chName': 'Radio Record',
            'pubDate': '2026-09-13T00:00:00', 'duration_sec': 3600,
            'service_name': 'rss', 'service_id': 'https://radiorecord.ru/rss',
            'with_next_ep_button': False, 'recNum': 0, 'recordUniqId': 'rr-1',
        }
        if itunes_listed is not None:
            podcast_info['itunes_listed'] = itunes_listed
        return srh.Sender(
            None, 'https://itunes.radiorecord.ru/tmp_audio/ep.mp3',
            {chat_id: {} for chat_id in chats},
            {chat_id: 'en' for chat_id in chats},
            {chat_id: None for chat_id in chats},
            podcast_info, with_status_message=False, consume_notify=False,
            outbox_id=7 if isinstance(self.outbox, FakeOutbox) else None, outbox_attempts=1)

    def records_left(self):
        return [name for name in os.listdir(os.path.join(self.tmp, "records"))]


def main():
    # Huberman, 14.09: iTunes-listed, fetched by rss_link (service_name 'rss'
    # since 9e97b92). 389 MB from circle used to be "too big" without a try.
    world = World(size_mb=389)
    sent = world.sender().send_record()
    _assert(sorted(sent) == [1, 2, 3], "389 MB iTunes-listed episode reaches every recipient")
    _assert(('url' not in {kind for _, kind in world.bot.audio}), "over 20 MB: no URL attempt")
    _assert(world.requester.downloads == 1 and world.agent.uploads == 1, "downloaded once, uploaded once")
    _assert(world.agent.sent_to == [1], "agent sends to the first chat only")
    _assert([kind for _, kind in world.bot.audio] == ['file_id', 'file_id'], "the rest reuse the file_id")
    _assert(world.notices == [], "no too-big or unavailable notice")
    _assert(world.records_left() == [] and world.budget._live == [], "file deleted, disk released")

    # Circle fan-out: the agent cannot reach the first chat; its file_id still can.
    world = World(size_mb=389, agent_unreachable_chat=1)
    sent = world.sender().send_record()
    _assert(sorted(sent) == [1, 2, 3], "chat the agent missed gets the file_id via Bot API")
    _assert(world.agent.uploads == 1 and world.notices == [], "still one upload, no notice")

    # One recipient cannot take it at all: only that chat hears about it.
    world = World(size_mb=389, agent_unreachable_chat=1, bot_refuse_chat=1)
    sent = world.sender().send_record()
    _assert(sorted(sent) == [2, 3], "the others are delivered")
    _assert([chat_id for chat_id, _ in world.notices] == [1], "notice goes only to the undelivered chat")

    # Radio Record, 11.09: 12 MB, Telegram cannot fetch the host, our server can.
    world = World(size_mb=12, url_error="Bad Request: failed to get HTTP URL content")
    sent = world.sender().send_record()
    _assert(sorted(sent) == [1, 2, 3], "URL refused by Telegram: delivered via download")
    kinds = [kind for _, kind in world.bot.audio]
    _assert(kinds.count('url') == 1, "one URL refusal stops URL attempts for everyone")
    _assert(kinds[1:] == ['upload', 'file_id', 'file_id'], "Bot API upload once, then file_id")
    _assert(world.agent.uploads == 0, "under 50 MB stays on the Bot API")
    _assert(world.notices == [], "no unavailable notice after a successful download")

    # Same, but chat 3 hits a 429 after the download: that is a retry, not a dead file.
    world = World(size_mb=12, url_error="Bad Request: failed to get HTTP URL content",
                  with_outbox=True, flood_chat=3)
    try:
        world.sender().send_record()
        raise AssertionError("429 after a URL refusal must go back to the outbox")
    except real_outbox.OutboxRetryableError:
        _assert(True, "429 after a URL refusal: job goes back to the outbox")
    _assert(not world.outbox.done and world.notices == [],
            "429 after a URL refusal: not done, nobody told 'unavailable'")

    # Same per-chat rules on every transport: blocked is marked once, a 429 retries once.
    world = World(size_mb=12, blocked_chat=2, flood_once_chat=3)
    sent = world.sender().send_record()
    _assert(sorted(sent) == [1, 3], "blocked chat skipped, flooded chat retried and delivered")
    _assert(world.blocked_marked == [2] and [k for c, k in world.bot.audio if c == 2] == ['blocked'],
            "blocked chat marked, not retried, no download for it")
    _assert(world.slept == [2] and world.requester.downloads == 0, "429 slept retry-after, then URL again")
    _assert(world.notices == [], "no notice to a blocked chat")

    world = World(size_mb=12)
    sent = world.sender().send_record()
    _assert(sorted(sent) == [1, 2, 3] and world.requester.downloads == 0,
            "small file Telegram can fetch: URL only, nothing downloaded")

    world = World(size_mb=2100)
    sent = world.sender().send_record()
    _assert(sent == [] and world.requester.downloads == 0, "over 2 GB: not downloaded")
    _assert(len(world.notices) == 3 and all('too big' in text for _, text in world.notices),
            "over 2 GB: too-big notice with links")

    world = World(size_mb=389, disk_free_mb=300)
    sent = world.sender().send_record()
    _assert(sent == [] and world.requester.downloads == 0, "cannot fit even alone: nothing written")
    _assert(len(world.notices) == 3 and all('too big' in text for _, text in world.notices),
            "cannot fit even alone: too-big notice")

    world = World(size_mb=389, disk_free_mb=1000, reserved_mb=900, with_outbox=True)
    try:
        world.sender().send_record()
        raise AssertionError("disk busy must hand the job back to the outbox")
    except real_outbox.OutboxRetryableError as e:
        _assert(isinstance(e.cause, DiskBusy), "disk busy: job goes back to the outbox")
        _assert(real_outbox.flood_wait_seconds(e) == e.cause.retry_after_seconds,
                "disk busy: outbox waits retry_after_seconds")
    _assert(world.requester.downloads == 0 and world.notices == [], "disk busy: no download, no notice")
    _assert(not world.outbox.done, "disk busy: job is not marked done")
    _assert(len(world.budget._live) == 1, "disk busy: only the other download's reservation remains")

    world = World(size_mb=389, download_error="404 Client Error: Not Found for url", with_outbox=True)
    sent = world.sender().send_record()
    _assert(sent == [] and world.outbox.done, "dead file: terminal, no retry")
    _assert(len(world.notices) == 3 and all('unavailable' in text.lower() or 'unavaliable' in text.lower()
                                            for _, text in world.notices),
            "dead file: unavailable notice")
    _assert(world.records_left() == [] and world.budget._live == [], "dead file: partial file and reservation cleaned")

    # A hung download cools a host for 30 minutes, so it must be the host that
    # hung: the link itself is often a redirector (podtrac, pdst.fm) carrying
    # unrelated podcasts. urllib3 names the real one in the message.
    hung_cdn = ("HTTPSConnectionPool(host='nbcnews.simplecastaudio.com', port=443): "
                "Max retries exceeded with url: /audio/ep.mp3 "
                "(Caused by ReadTimeoutError(Read timed out. (read timeout=15)))")
    world = World(size_mb=389, download_error=hung_cdn)
    world.sender().send_record()
    _assert([host_from_error(error) for _, error in world.cooled]
            == ['nbcnews.simplecastaudio.com'],
            "hung CDN: the cooldown is told the error, not just the link")

    # Podcasts added by a bare RSS link: never downloaded unless trusted.
    world = World(size_mb=389)
    sent = world.sender(itunes_listed=False).send_record()
    _assert(sent == [] and world.requester.downloads == 0 and world.agent.uploads == 0,
            "RSS-only 389 MB: nothing downloaded or uploaded")
    _assert('url' not in {kind for _, kind in world.bot.audio}, "RSS-only over 20 MB: no URL attempt")
    _assert(len(world.notices) == 3 and all('added by RSS link' in text and 'ep.mp3' in text
                                            for _, text in world.notices),
            "RSS-only over 20 MB: too-big-for-RSS notice with the file link")

    world = World(size_mb=12)
    sent = world.sender(itunes_listed=False).send_record()
    _assert(sorted(sent) == [1, 2, 3] and world.requester.downloads == 0, "RSS-only 12 MB: by URL as media")

    world = World(size_mb=12, url_error="Bad Request: failed to get HTTP URL content")
    sent = world.sender(itunes_listed=False).send_record()
    _assert(sent == [] and world.requester.downloads == 0, "RSS-only, URL refused: still not downloaded")
    _assert(len(world.notices) == 3 and all('unavaliable' in t.lower() or 'unavailable' in t.lower()
                                            for _, t in world.notices),
            "RSS-only, URL refused: unavailable notice with links")

    world = World(size_mb=12, size_known=False)
    sent = world.sender(itunes_listed=False).send_record()
    _assert(sorted(sent) == [1, 2, 3] and world.requester.downloads == 0,
            "RSS-only, unknown size: URL is tried, not a blind too-big")

    world = World(size_mb=389, trust_rss=True)
    sent = world.sender(itunes_listed=False).send_record()
    _assert(sorted(sent) == [1, 2, 3] and world.agent.uploads == 1, "trustRssPodcasts on: RSS-only is downloaded")

    world = World(size_mb=389)
    sent = world.sender(itunes_listed=None).send_record()
    _assert(sent == [] and world.requester.downloads == 0,
            "job queued without itunes_listed (before deploy): treated as RSS-only")

    print("all record delivery checks passed")


if __name__ == "__main__":
    main()
