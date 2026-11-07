# -*- coding: utf-8 -*-
"""Bronze for free while the chat is subscribed to `need` of the owner's channels: the grant
features.CHANNELS (db/plan_grants.py), its profile features.grant_key(CHANNELS) (no AI).

The owner lists the channels and `need` in the admin (bot_runtime_kv SETTINGS_KEY; the bot must be an
admin of each, else Telegram does not say who is subscribed). /subscription shows the button while a
list is set; the screen (route SCREEN) lists the channels and "Check" (CHECK_ACTION): subscribed to
`need` of them and no other plan running, the grant starts. The jobs role checks the holders every hour
(app/jobs/plan_grants.py): still subscribed, held; fewer, ended, with a message and Relay's invoice.
A check Telegram does not answer (the bot is no admin there, no network) keeps the plan and tells the
creator: a user never loses a plan for the bot's fault. Whether a chat is subscribed is
getChatMember, the raw request (no Telegram import at module level: the admin and the jobs read it).
Lock: python app/service/plan/test_channels.py
"""
import json
import re
import time

from app.i18n.messages import get_message
from app.service.analytics_events import GRANT_SOURCE
from app.service.payment.storefront import relay_nudge_markup
from app.service.plan import entitlements, features
from db import plan_grants, runtime_kv
from lib.tools.logger import logger

KIND = features.CHANNELS
LEVEL = features.GRANT_LEVELS[KIND]
SETTINGS_KEY = 'plan_grant_channels'  # JSON {channels: [{id, title, url, ref}], need}
SCREEN = 'bs_chan'
CHECK_ACTION = 'bs_chan_ok'
IN = {'creator', 'administrator', 'member'}
# answers that mean "not in this channel", not "could not tell"
NOT_MEMBER_ERRORS = ('user not found', 'participant_id_invalid', 'user_not_participant')


class CheckFailed(Exception):
    """Telegram did not say whether the chat is subscribed: the bot is not an admin there, no network."""


def settings(database=None) -> dict:
    """{'channels': [{id, title, url}], 'need': n}, need within 0..len(channels)."""
    try:
        data = json.loads(runtime_kv.get_kv(SETTINGS_KEY, database=database) or '{}')
    except (TypeError, ValueError):
        data = {}
    channels = [c for c in (data.get('channels') or []) if isinstance(c, dict) and c.get('id')]
    try:
        need = int(data.get('need') or 0)
    except (TypeError, ValueError):
        need = 0
    return {'channels': channels, 'need': max(0, min(need, len(channels)))}


def save_settings(channels, need, database=None) -> dict:
    runtime_kv.set_kv(SETTINGS_KEY, json.dumps({'channels': list(channels), 'need': int(need)}), database=database)
    return settings(database)


def available(conf) -> bool:
    return bool(conf['channels']) and conf['need'] > 0


_LINK = re.compile(r'^(?:https?://)?(?:t(?:elegram)?\.me/)([A-Za-z0-9_]{4,})/?$')


def chat_ref(text):
    """What getChat takes from what the admin typed: '@name', 'name', 't.me/name', '-100...'."""
    text = str(text or '').strip()
    if re.fullmatch(r'-?\d+', text):
        return int(text)
    link = _LINK.match(text)
    name = link.group(1) if link else text.lstrip('@')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{3,}', name):
        raise ValueError('not a channel: %r (an @name, a t.me link or the -100 id)' % text)
    return '@' + name


def resolve(text, request=None) -> dict:
    """{id, title, url, ref} of a channel the bot can check (ref: how the admin shows it again): it is an admin there (else Telegram does not say
    who is subscribed). ValueError says what is wrong."""
    request = request or bot_request
    try:
        chat = request('getChat', {'chat_id': chat_ref(text)})
        me = request('getMe', {})
        member = request('getChatMember', {'chat_id': chat['id'], 'user_id': me['id']})
    except ValueError:
        raise
    except Exception as e:
        raise ValueError('%s: %s' % (text, e)) from e
    if member.get('status') not in ('administrator', 'creator'):
        raise ValueError('%s: the bot is not an admin of this channel' % text)
    url = 'https://t.me/' + chat['username'] if chat.get('username') else chat.get('invite_link')
    if not url:
        try:
            url = request('exportChatInviteLink', {'chat_id': chat['id']})
        except Exception as e:
            raise ValueError('%s: a private channel without an invite link the bot may make: %s' % (text, e)) from e
    ref = '@' + chat['username'] if chat.get('username') else str(chat['id'])
    return {'id': int(chat['id']), 'title': chat.get('title') or text, 'url': url, 'ref': ref}


def bot_request(method, params):
    """A Bot API call by the bot's token (pyTelegramBotAPI's raw request)."""
    from telebot import apihelper
    from agent.bot_telebot import bot
    return apihelper._make_request(bot.token, method, method='post', params=params)


def is_member(channel_id, telegram_id, request=None) -> bool:
    try:
        member = (request or bot_request)('getChatMember', {'chat_id': channel_id, 'user_id': int(telegram_id)})
    except Exception as e:
        if any(error in str(e).lower() for error in NOT_MEMBER_ERRORS):
            return False
        raise CheckFailed('%s: %s' % (channel_id, e)) from e
    status = (member or {}).get('status')
    return status in IN or (status == 'restricted' and bool((member or {}).get('is_member')))


def subscribed(telegram_id, conf, request=None) -> int:
    """How many of the listed channels the chat is subscribed to; CheckFailed when Telegram did not say."""
    return sum(1 for channel in conf['channels'] if is_member(channel['id'], telegram_id, request))


def body(language_code, conf) -> str:
    total = len(conf['channels'])
    if conf['need'] >= total:
        return get_message('chanPlanBodyAll', language_code)
    return get_message('chanPlanBodySome', language_code).format(need=conf['need'], total=total)


def screen_message(chat_id, language_code, database=None) -> dict:
    """The channels, "Check" and Back; a line that the plan is on while the grant holds it."""
    from app.routes.message_tools import go_back_inline_button  # Telegram's types: the bot role only
    conf = settings(database)
    if not available(conf):
        return {'type': 'text', 'text': get_message('chanPlanUnavailable', language_code),
                'reply_markup': [[go_back_inline_button(language_code)]]}
    text = body(language_code, conf)
    if entitlements.of(chat_id, database).grant == KIND:
        text += '\n\n' + get_message('chanPlanActive', language_code).format(need=conf['need'])
    rows = [[{'text': channel.get('title') or channel['url'], 'url': channel['url']}]
            for channel in conf['channels'] if channel.get('url')]
    rows.append([{'text': get_message('chanPlanCheck', language_code), 'callback_data': {'tp': CHECK_ACTION}}])
    rows.append([go_back_inline_button(language_code)])
    return {'type': 'text', 'text': text, 'reply_markup': rows, 'disable_web_page_preview': True}


def entry_row(chat_id, language_code, database=None) -> list:
    """The /subscription row to the screen, while a list is set: [] without one."""
    if not available(settings(database)):
        return []
    return [[{'text': get_message('chanPlanButton', language_code), 'callback_data': {'tp': SCREEN}}]]


def status_line(chat_id, language_code, database=None) -> str:
    """'' unless the chat's plan is this grant: then what it is and while it stays."""
    if entitlements.of(chat_id, database).grant != KIND:
        return ''
    return get_message('chanPlanActive', language_code).format(need=settings(database)['need'])


def pay_note(chat_id, language_code, database=None) -> str:
    """Under the pages that sell a plan, for a holder: what is bought replaces it."""
    if entitlements.of(chat_id, database).grant != KIND:
        return ''
    return '\n\n' + get_message('chanPlanPayNote', language_code)


def off_message(language_code, count, need) -> dict:
    """The plan ended at a check: the channels' screen, Relay's invoice, change-plan."""
    rows = [[{'text': get_message('chanPlanScreenButton', language_code), 'callback_data': {'tp': SCREEN}}]]
    return {'type': 'text', 'disable_web_page_preview': True,
            'text': get_message('chanPlanOff', language_code).format(count=count, need=need),
            'reply_markup': rows + relay_nudge_markup(language_code, invoice=True, source=GRANT_SOURCE)}


def warn_creator(text, now=None, database=None) -> None:
    """Once a day at most: the creator hears that checks failed (the bot is no admin of a channel...)."""
    now = time.time() if now is None else now
    key = 'plan_grant_warned_at'
    try:
        if now - float(runtime_kv.get_kv(key, 0, database=database) or 0) < 86400:
            return
        runtime_kv.set_kv(key, str(now), database=database)
        from app.controller.builders.adminModule import send_message_to_creator
        send_message_to_creator("#problem #warning free Bronze for channels: " + text)
    except Exception as e:
        logger.warn("free Bronze warning:", type(e).__name__, e)


def start(chat_id, conf, request=None, database=None) -> tuple:
    """(outcome, count): the check behind "Check". Outcomes: plan_grants.STARTED / HELD / BUSY /
    UNKNOWN, 'missing' (fewer than `need`), 'failed' (Telegram did not say), 'unavailable' (no list)."""
    if not available(conf):
        return 'unavailable', 0
    rights = entitlements.of(chat_id, database)
    if rights.running and not rights.grant:
        return plan_grants.BUSY, 0
    try:
        count = subscribed(chat_id, conf, request)
    except CheckFailed as e:
        logger.warn("free Bronze check:", e)
        warn_creator(str(e), database=database)
        return 'failed', 0
    if count < conf['need']:
        return 'missing', count
    return plan_grants.start(chat_id, KIND, LEVEL, database=database), count
