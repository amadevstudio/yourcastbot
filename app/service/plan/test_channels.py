# -*- coding: utf-8 -*-
"""Free Bronze for subscribing to the owner's channels (app/service/plan/channels.py, app/jobs/plan_grants.py).

- "Check": no list, unavailable; another plan running, busy; fewer than `need`, missing; Telegram not
  saying (the bot no admin there), failed and the creator hears; else the grant starts (again: held).
- Subscribed is creator, administrator, member, or restricted and still a member; "user not found"
  is not subscribed, any other error is "could not tell".
- The hourly pass: still subscribed, held; fewer, ended with the plan it replaced back and a message
  with the channels and Relay's invoice; could not tell, kept; an empty list, every plan kept.
- The admin's list: an @name, a t.me link or the id; the bot must be an admin; a private channel
  gets the bot's invite link.

Run from the repo root: python app/service/plan/test_channels.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs import plan_grants as grant_job  # noqa: E402
from app.service.analytics_events import GRANT_SOURCE  # noqa: E402
from app.service.payment.storefront import RELAY_INVOICE_CALLBACK  # noqa: E402
from app.service.plan import channels  # noqa: E402
from db import plan_grants  # noqa: E402
from db.test_plan_grants import _db, _row, _user, BRONZE, RELAY  # noqa: E402

A, B, C = -1001, -1002, -1003
NOW = 1_800_000_000.0
WARNED = []  # what the creator would hear: never a real message from a test


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


class Telegram:
    """getChatMember answered from {(channel, user): status}; `broken` channels raise."""

    def __init__(self, members=None, broken=()):
        self.members, self.broken, self.calls = dict(members or {}), set(broken), []

    def __call__(self, method, params):
        self.calls.append(method)
        if method == 'getChatMember':
            if params['chat_id'] in self.broken:
                raise RuntimeError('Bad Request: member list is inaccessible')
            status = self.members.get((params['chat_id'], params['user_id']))
            if status is None:
                raise RuntimeError('A request to the Telegram API was unsuccessful. Error code: 400. '
                                   'Description: Bad Request: user not found')
            return {'status': status, 'is_member': status == 'restricted+'}
        raise AssertionError(method)


def _conf(path, need, *ids):
    return channels.save_settings([{'id': i, 'title': 'Channel %d' % i, 'url': 'https://t.me/c%d' % -i}
                                   for i in ids], need, path)


def test_membership():
    tg = Telegram({(A, 1): 'member', (B, 1): 'left', (C, 1): 'administrator', (A, 2): 'restricted',
                   (B, 2): 'kicked', (C, 2): 'creator'})
    _assert(channels.is_member(A, 1, tg) and channels.is_member(C, 1, tg) and channels.is_member(C, 2, tg),
            "member, administrator, creator: subscribed")
    _assert(not channels.is_member(B, 1, tg) and not channels.is_member(B, 2, tg) and not channels.is_member(A, 2, tg),
            "left, kicked, restricted and out: not")
    _assert(not channels.is_member(A, 9, tg), "user not found: not subscribed")
    try:
        channels.is_member(A, 1, Telegram(broken={A}))
        _assert(False, "a broken channel raises")
    except channels.CheckFailed:
        _assert(True, "the bot no admin there: could not tell")


def test_check(path):
    who, busy, few = 6001, 6002, 6003
    _user(path, who, tariff_id=RELAY, balance=20)
    _user(path, busy, tariff_id=RELAY, time_left=50, notify=-1)
    _user(path, few)
    _assert(channels.start(who, channels.settings(path), Telegram(), path)[0] == 'unavailable', "no list: unavailable")
    conf = _conf(path, 2, A, B, C)
    tg = Telegram({(A, who): 'member', (C, who): 'member', (A, busy): 'member', (B, busy): 'member',
                   (A, few): 'member'})
    _assert(channels.start(busy, conf, tg, path)[0] == plan_grants.BUSY, "another plan running: busy")
    _assert(channels.start(few, conf, tg, path) == ('missing', 1), "1 of 2: missing, with the count")
    _assert(channels.start(who, conf, Telegram(broken={A}), path)[0] == 'failed', "Telegram not saying: failed")
    _assert(channels.start(who, conf, tg, path) == (plan_grants.STARTED, 2), "2 of 3: started")
    _assert(_row(path, who)[:2] == (BRONZE, plan_grants.HOLD_HOURS), "Bronze on")
    _assert(channels.start(who, conf, tg, path)[0] == plan_grants.HELD, "again: held")
    _assert(channels.status_line(who, 'en', path) and not channels.status_line(busy, 'en', path),
            "/subscription says it is on, to the holder only")
    _assert(channels.pay_note(who, 'en', path) and not channels.pay_note(few, 'en', path), "the pages that sell say what replaces it")
    _assert(channels.entry_row(few, 'en', path)[0][0]['callback_data'] == {'tp': channels.SCREEN},
            "/subscription has the button while a list is set")
    return who


def test_hourly(path, who):
    stays, leaves = who, 6010
    _user(path, leaves, tariff_id=RELAY)
    conf = channels.settings(path)
    tg = Telegram({(A, stays): 'member', (C, stays): 'member', (A, leaves): 'member', (B, leaves): 'member'})
    channels.start(leaves, conf, tg, path)
    tg.members[(B, leaves)] = 'left'
    sent = []
    done = grant_job.check_holders(path, NOW, tg, lambda chat, messages: sent.append((chat, messages)), pause=0)
    _assert(done == {'held': 1, 'ended': 1, 'failed': 0}, "one held, one ended")
    _assert(_row(path, leaves)[:2] == (RELAY, 0) and plan_grants.active_kind(leaves, path) is None,
            "ended: the plan it replaced back, no days")
    _assert(_row(path, stays)[:2] == (BRONZE, plan_grants.HOLD_HOURS), "held")
    _assert(len(sent) == 1 and sent[0][0] == leaves, "the one who left hears it")
    rows = sent[0][1][0]['reply_markup']
    _assert(rows[0][0]['callback_data'] == {'tp': channels.SCREEN}
            and rows[1][0]['callback_data'] == dict(RELAY_INVOICE_CALLBACK, s=GRANT_SOURCE),
            "with the channels first, then Relay's invoice")
    del WARNED[:]
    done = grant_job.check_holders(path, NOW, Telegram(broken={A}), lambda *a: sent.append(a), pause=0)
    _assert(done == {'held': 0, 'ended': 0, 'failed': 1} and _row(path, stays)[:2] == (BRONZE, plan_grants.HOLD_HOURS)
            and WARNED and len(sent) == 1, "could not tell: kept, the creator hears, the user does not")
    _conf(path, 0)
    done = grant_job.check_holders(path, NOW, Telegram(), lambda *a: sent.append(a), pause=0)
    _assert(done['held'] == 1 and plan_grants.active_kind(stays, path) == 'channels', "an empty list keeps every plan")


def test_admin_list():
    _assert(channels.chat_ref('https://t.me/somechannel') == '@somechannel' and channels.chat_ref('-1001') == -1001,
            "a link and an id")

    def tg(method, params):
        return {'getChat': {'id': -1005, 'title': 'Private', 'invite_link': None},
                'getMe': {'id': 77}, 'getChatMember': {'status': 'administrator'},
                'exportChatInviteLink': 'https://t.me/+abc'}[method]
    _assert(channels.resolve('-1005', tg) == {'id': -1005, 'title': 'Private', 'url': 'https://t.me/+abc', 'ref': '-1005'},
            "a private channel: the bot's invite link")

    def not_admin(method, params):
        return {'getChat': {'id': -1006, 'title': 'Public', 'username': 'pubchannel'}, 'getMe': {'id': 77},
                'getChatMember': {'status': 'left'}}[method]
    try:
        channels.resolve('@pubchannel', not_admin)
        _assert(False, "not an admin is refused")
    except ValueError as e:
        _assert('not an admin' in str(e), "the bot not an admin: refused, saying so")


def test_ai_offer():
    """A holder asking for AI hears that this Bronze has none, then every plan's invoice (it replaces the grant)."""
    from app.i18n.messages import get_message
    from app.service.ai.offer import offer_message
    from app.service.ai.quota import Quota
    from app.service.record import free_limit
    saved, free_limit.plans_offer = free_limit.plans_offer, lambda language_code, source=None: ('plans', [['row']])
    try:
        message = offer_message('en', Quota(False, 0, 0, 3600, 1, grant=channels.KIND))
        plain = offer_message('en', Quota(False, 0, 0, 3600, 0))
    finally:
        free_limit.plans_offer = saved
    _assert(message['text'].startswith(get_message('aiGrantNoAi', 'en')) and message['reply_markup'] == [['row']],
            "AI asked on a grant: it has none, and every plan")
    _assert(not plain['text'].startswith(get_message('aiGrantNoAi', 'en')), "no plan: the plans, no word of a grant")


def main():
    saved, channels.warn_creator = channels.warn_creator, lambda text, now=None, database=None: WARNED.append(text)
    test_membership()
    path = _db()
    try:
        who = test_check(path)
        test_hourly(path, who)
    finally:
        os.unlink(path)
        channels.warn_creator = saved
    test_admin_list()
    test_ai_offer()
    print("all free Bronze for channels tests passed")


if __name__ == '__main__':
    main()
