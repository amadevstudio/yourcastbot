# -*- coding: utf-8 -*-
"""Free Bronze for subscribing to the owner's channels (app/service/plan/channels.py, app/jobs/plan_grants.py).

- "Check": off, unavailable; another plan running, busy; a channel missing, missing with its name;
  Telegram not saying (the bot no admin there), failed and the creator hears; else the grant starts
  (again: held). No channel listed: off, whatever the switch says.
- Subscribed is creator, administrator, member, or restricted and still a member; "user not found"
  is not subscribed, any other error is "could not tell".
- The hourly pass: subscribed to all, held; a channel missing (left, or a channel added), warned once
  with that channel and kept for the grace; subscribed again, the mark goes; still missing after it,
  ended with the plan it replaced back and a message with the channels' screen and every plan; could
  not tell, kept; turned off, every grant ended with a message and every plan.
- The admin's list: an @name, a t.me link or the id; the bot must be an admin; a private channel
  gets the bot's invite link.
- The hourly refresh by id: a renamed channel gets its new title, link and ref; a private one keeps its
  link (no new invite link); one Telegram does not answer for stays; an admin's save meanwhile is kept.

Run from the repo root: python app/service/plan/test_channels.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.jobs import plan_grants as grant_job  # noqa: E402
from app.service.analytics_events import GRANT_SOURCE  # noqa: E402
from app.service.plan import channels  # noqa: E402
from app.service.record import free_limit  # noqa: E402
from db import plan_grants  # noqa: E402
from db.test_plan_grants import _db, _row, _user, BRONZE, RELAY  # noqa: E402

A, B, C = -1001, -1002, -1003
NOW = 1_800_000_000.0
WARNED = []  # what the creator would hear: never a real message from a test
PLANS = [[{'text': 'Bronze', 'callback_data': {'tp': 'bs_stars_pay', 'v': BRONZE}}],
         [{'text': 'Relay', 'callback_data': {'tp': 'bs_stars_pay', 'v': RELAY}}]]
GRACE = channels.GRACE_HOURS * 3600


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


def _conf(path, *ids, enabled=True):
    return channels.save_settings(enabled, [{'id': i, 'title': 'Channel %d' % -i, 'url': 'https://t.me/c%d' % -i}
                                            for i in ids], path)


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


def test_settings(path):
    _assert(not channels.available(channels.settings(path)), "nothing saved: off")
    _assert(not channels.available(_conf(path, enabled=True)), "on with no channel: off")
    _assert(not channels.available(_conf(path, A, enabled=False)), "turned off with channels: off")
    _assert(channels.available(_conf(path, A)), "on with a channel: on")


def test_check(path):
    who, busy, few = 6001, 6002, 6003
    _user(path, who, tariff_id=RELAY, balance=20)
    _user(path, busy, tariff_id=RELAY, time_left=50, notify=-1)
    _user(path, few)
    _conf(path, A, B, enabled=False)
    _assert(channels.start(who, channels.settings(path), Telegram(), path)[0] == 'unavailable', "off: unavailable")
    _assert(channels.entry_row(few, 'en', path) == [], "off: no button on /subscription")
    conf = _conf(path, A, B)
    tg = Telegram({(A, who): 'member', (B, who): 'member', (A, busy): 'member', (B, busy): 'member',
                   (A, few): 'member'})
    _assert(channels.start(busy, conf, tg, path)[0] == plan_grants.BUSY, "another plan running: busy")
    outcome, absent = channels.start(few, conf, tg, path)
    _assert(outcome == 'missing' and channels.names(absent) == 'Channel 1002', "one missing: said by name")
    _assert(channels.start(who, conf, Telegram(broken={A}), path)[0] == 'failed', "Telegram not saying: failed")
    _assert(channels.start(who, conf, tg, path) == (plan_grants.STARTED, []), "subscribed to all: started")
    _assert(_row(path, who)[:2] == (BRONZE, plan_grants.HOLD_HOURS), "Bronze on")
    _assert(channels.start(who, conf, tg, path)[0] == plan_grants.HELD, "again: held")
    _assert(channels.status_line(who, 'en', path) and not channels.status_line(busy, 'en', path),
            "/subscription says it is on, to the holder only")
    _assert(channels.pay_note(who, 'en', path) and not channels.pay_note(few, 'en', path), "the pages that sell say what replaces it")
    _assert(channels.entry_row(few, 'en', path)[0][0]['callback_data'] == {'tp': channels.SCREEN},
            "/subscription has the button while it is on")
    return who


def _pass(path, now, tg, sent):
    return grant_job.check_holders(path, now, tg, lambda chat, messages: sent.append((chat, messages[0])), pause=0)


def test_hourly(path, who):
    stays, leaves = who, 6010
    _user(path, leaves, tariff_id=RELAY)
    tg = Telegram({(A, stays): 'member', (B, stays): 'member', (A, leaves): 'member', (B, leaves): 'member'})
    channels.start(leaves, channels.settings(path), tg, path)
    tg.members[(B, leaves)] = 'left'
    sent = []
    _assert(_pass(path, NOW, tg, sent) == {'held': 1, 'warned': 1, 'ended': 0, 'failed': 0},
            "one held, the one who left warned")
    _assert(len(sent) == 1 and sent[0][0] == leaves and 'Channel 1002' in sent[0][1]['text']
            and {'tp': channels.CHECK_ACTION} in [b.get('callback_data') for row in sent[0][1]['reply_markup'] for b in row],
            "the warning names the channel, with its link and Check")
    _assert(_row(path, leaves)[:2] == (BRONZE, plan_grants.HOLD_HOURS), "the plan stays meanwhile")
    _assert(_pass(path, NOW + 3600, tg, sent)['warned'] == 1 and len(sent) == 1, "an hour later: no second warning")
    tg.members[(B, leaves)] = 'member'
    _assert(_pass(path, NOW + 7200, tg, sent)['held'] == 2, "subscribed again: held")
    tg.members[(B, leaves)] = 'left'
    _pass(path, NOW + 3 * 3600, tg, sent)
    _assert(len(sent) == 2, "left again: the mark had gone, so a new warning")
    _assert(_pass(path, NOW + 3 * 3600 + GRACE - 1, tg, sent)['ended'] == 0, "within the grace: kept")
    done = _pass(path, NOW + 3 * 3600 + GRACE, tg, sent)
    _assert(done['ended'] == 1 and _row(path, leaves)[:2] == (RELAY, 0) and plan_grants.active_kind(leaves, path) is None,
            "the grace over: ended, the plan it replaced back, no days")
    message = sent[-1][1]
    _assert(sent[-1][0] == leaves and message['reply_markup'][0][0]['callback_data'] == {'tp': channels.SCREEN}
            and message['reply_markup'][1:] == PLANS, "with the channels' screen first, then every plan")
    del WARNED[:]
    count = len(sent)
    done = _pass(path, NOW + 4 * GRACE, Telegram(broken={A}), sent)
    _assert(done == {'held': 0, 'warned': 0, 'ended': 0, 'failed': 1} and _row(path, stays)[:2] == (BRONZE, plan_grants.HOLD_HOURS)
            and WARNED and len(sent) == count, "could not tell: kept, the creator hears, the user does not")
    _conf(path, A, B, C)
    _pass(path, NOW + 5 * GRACE, tg, sent)
    _assert(len(sent) == count + 1 and sent[-1][0] == stays and 'Channel 1003' in sent[-1][1]['text']
            and plan_grants.active_kind(stays, path) == 'channels', "a channel added: the holder is warned, kept")
    _conf(path, A, B)
    _pass(path, NOW + 5 * GRACE + 3600, tg, sent)
    _pass(path, NOW + 7 * GRACE, tg, sent)
    _assert(plan_grants.active_kind(stays, path) == 'channels' and len(sent) == count + 1,
            "the channel removed again: the mark goes, nothing ends")
    _conf(path, A, B, enabled=False)
    done = _pass(path, NOW + 8 * GRACE, tg, sent)
    _assert(done['ended'] == 1 and plan_grants.active_kind(stays, path) is None and _row(path, stays)[2] == 0,
            "turned off: every grant ends")
    _assert(sent[-1][0] == stays and sent[-1][1]['reply_markup'] == PLANS
            and sent[-1][1]['text'] == channels.stopped_message('en')['text'], "with a message and every plan")
    _conf(path, A, B)
    _assert(channels.start(stays, channels.settings(path), tg, path)[0] == plan_grants.STARTED,
            "on again: it can be taken again")


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


def test_refresh(path):
    channels.save_settings(True, [
        {'id': A, 'title': 'Old', 'url': 'https://t.me/oldname', 'ref': '@oldname'},
        {'id': B, 'title': 'Private', 'url': 'https://t.me/+abc', 'ref': str(B)},
        {'id': C, 'title': 'Lost', 'url': 'https://t.me/lost', 'ref': '@lost'}], path)
    calls = []

    def tg(method, params):
        calls.append(method)
        if params['chat_id'] == C:
            raise RuntimeError('Bad Request: chat not found')
        return {A: {'id': A, 'title': 'New', 'username': 'newname'},
                B: {'id': B, 'title': 'Private 2', 'invite_link': None}}[params['chat_id']]
    _assert(channels.refresh(tg, path) == 2, "two channels changed")
    got = {c['id']: c for c in channels.settings(path)['channels']}
    _assert(got[A] == {'id': A, 'title': 'New', 'url': 'https://t.me/newname', 'ref': '@newname'},
            "renamed: new title, link and ref")
    _assert(got[B]['url'] == 'https://t.me/+abc' and got[B]['title'] == 'Private 2'
            and 'exportChatInviteLink' not in calls, "private: title follows, the invite link is kept")
    _assert(got[C]['url'] == 'https://t.me/lost' and channels.settings(path)['enabled'], "not answered: kept, still on")
    _assert(channels.refresh(tg, path) == 0, "nothing new: nothing written")

    def admin_saves(method, params):
        channels.save_settings(False, [{'id': A, 'title': 'New', 'url': 'https://t.me/newname', 'ref': '@newname'},
                                       {'id': -1009, 'title': 'Added', 'url': 'https://t.me/added', 'ref': '@added'}], path)
        return {'id': params['chat_id'], 'title': 'Newer', 'username': 'newername'}
    channels.refresh(admin_saves, path)
    conf = channels.settings(path)
    _assert(not conf['enabled'] and [c['id'] for c in conf['channels']] == [A, -1009]
            and conf['channels'][0]['ref'] == '@newername', "an admin's save meanwhile is kept, the refresh applied on it")


def test_ai_offer():
    """A holder asking for AI hears that this Bronze has none, then every plan's invoice (it replaces the grant)."""
    from app.i18n.messages import get_message
    from app.service.ai.offer import offer_message
    from app.service.ai.quota import Quota
    message = offer_message('en', Quota(False, 0, 0, 3600, 1, grant=channels.KIND))
    plain = offer_message('en', Quota(False, 0, 0, 3600, 0))
    _assert(message['text'].startswith(get_message('aiGrantNoAi', 'en')) and message['reply_markup'] == PLANS,
            "AI asked on a grant: it has none, and every plan")
    _assert(not plain['text'].startswith(get_message('aiGrantNoAi', 'en')), "no plan: the plans, no word of a grant")


def test_click_limit():
    """A holder's day of clicks used up: every plan's invoice (a plan bought replaces the grant)."""
    message = free_limit.trial_limit_message('en', 3600, 1, 100, grant=True)
    _assert(message['reply_markup'] == PLANS, "the clicks of a grant: every plan")


def main():
    saved = channels.warn_creator, free_limit.plans_offer
    channels.warn_creator = lambda text, now=None, database=None: WARNED.append(text)
    free_limit.plans_offer = lambda language_code, source=None: ('plans', PLANS)
    test_membership()
    path = _db()
    try:
        test_settings(path)
        who = test_check(path)
        test_hourly(path, who)
        test_admin_list()
        test_refresh(path)
        test_ai_offer()
        test_click_limit()
    finally:
        os.unlink(path)
        channels.warn_creator, free_limit.plans_offer = saved
    print("all free Bronze for channels tests passed")


if __name__ == '__main__':
    main()
