# -*- coding: utf-8 -*-
"""A free limit sells every plan: the subscription limit and the manual update
limit carry each plan's invoice, Relay first (any plan lifts them), the free
Bronze for channels while it is on, and change-plan. The channel page carries
Relay's (only Relay posts to channels), a button that bills Relay without
naming a tariff id.

Needs the bot's requirements (the builders import telebot and Telethon).
Run from the repo root: python app/service/payment/test_paywall.py
"""
import json
import os
import sys
import types
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.controller.builders.test_open_recs import import_builder  # noqa: E402

TARIFFS = [{'id': 1, 'level': 1, 'price': 50, 'notify_count': 30, 'compression': 0, 'channel_control': 0},
           {'id': 3, 'level': 3, 'price': 500, 'notify_count': -1, 'compression': 1, 'channel_control': 1}]


def _assert(cond, label):
    if not cond:
        raise AssertionError(label)
    print("ok  %s" % label)


def _assert_eq(got, expected, label):
    if got != expected:
        raise AssertionError("%s: expected %r, got %r" % (label, expected, got))
    print("ok  %s = %r" % (label, got))


def _first_cta(markup):
    return [row[0].get('callback_data') for row in markup][:2]


PAYWALL = [{'tp': 'bs_stars_pay'}, {'tp': 'bs_trfs'}]
EVERY_PLAN = [{'tp': 'bs_stars_pay', 'v': 3}, {'tp': 'bs_stars_pay', 'v': 1}, {'tp': 'bs_trfs'}]
FREE_BRONZE = [{'tp': 'bs_stars_pay', 'v': 3}, {'tp': 'bs_stars_pay', 'v': 1}, {'tp': 'bs_chan'}, {'tp': 'bs_trfs'}]


def _ctas(markup):
    return [row[0].get('callback_data') for row in markup]


def _plans(promo=False):
    """plans_offer's database, Stars rate and the free Bronze switch."""
    from contextlib import ExitStack
    import db.sqliteAdapter
    from app.service.payment import starsPaymentModule
    from app.service.plan import channels
    stack = ExitStack()
    stack.enter_context(patch.object(db.sqliteAdapter, 'SQLighter', _FreeUserDB))
    stack.enter_context(patch.object(starsPaymentModule, 'get_stars_withdraw_rate_x1000', lambda **kw: 1300))
    stack.enter_context(patch.object(channels, 'entry_row', lambda *a, **kw: [[
        {'text': 'free', 'callback_data': {'tp': 'bs_chan'}}]] if promo else []))
    return stack


class _FreeUserDB:
    """A free user over the 15-podcast limit."""

    def __init__(self, _path):
        pass

    def get_uccs_count_by_tg(self, _chat_id):
        return 16

    def getUserSubscriptionByTg(self, _chat_id):
        return None

    def get_user_related_podcast_info(self, _chat_id, _podcast_id):
        return {'subscribed': False}

    def is_user_have_bot_subscription(self, _chat_id):
        return False

    def getTariffs(self, channel_control=None):
        return [t for t in TARIFFS if not channel_control or t['level'] == 3]

    def close(self):
        pass


def _call(data):
    return types.SimpleNamespace(data=json.dumps(data))


def subscription_limit(podcast, promo=False):
    sent, toasts, subscribed = [], [], []
    data = {'chat_id': 501, 'language_code': 'en', 'message': None,
            'callback': _call({'tp': 'subscription'}),
            'united_data': {'id': 7, 'service_id': '77', 'service_name': 'itunes'}}
    with patch.object(podcast, 'SQLighter', _FreeUserDB), \
            patch.object(podcast, 'notify', lambda _c, _m, text, **kw: toasts.append((text, kw))), \
            patch.object(podcast, 'outer_sender', lambda chat, msgs, **kw: sent.append((chat, msgs))), \
            patch.object(podcast.app.service.podcast.subscription, 'add_sub',
                         lambda *a: subscribed.append(a)), _plans(promo):
        _assert_eq(podcast.switch_subscription(data), False, "the 16th free podcast is refused")
    _assert_eq(subscribed, [], "and not subscribed")
    _assert_eq(toasts[0][1].get('alert', False), False, "a toast, not a blocking alert")
    _assert_eq(_ctas(sent[0][1][0]['reply_markup']), FREE_BRONZE if promo else EVERY_PLAN,
               "the limit message: every plan's invoice, Relay first, %schange-plan"
               % ("the free Bronze, " if promo else ""))
    _assert('Relay' not in sent[0][1][0]['text'].split('\n')[0], "and does not say only Relay lifts it")


def update_limit():
    stub = types.ModuleType("agent.bot_telethon")
    stub.thobot_session_handler = ""
    sys.modules["agent.bot_telethon"] = stub
    import app.jobs.podcastsUpdater as updater
    renders = []
    data = {'chat_id': 502, 'language_code': 'en', 'message': None, 'callback': None}
    with patch.object(updater, 'SQLighter', _FreeUserDB), \
            patch.object(updater, 'outer_sender', lambda *a, **kw: True), \
            patch.object(updater, 'render_messages', lambda chat, msgs, **kw: renders.append(msgs)), \
            patch.object(updater.outbox, 'enqueue', lambda *a, **kw: None), \
            patch.object(updater.storage, 'del_user_state', lambda *a: None), \
            patch.object(updater.storage, 'add_user_state', lambda *a: None), _plans(True):
        updater.update_feed(data)
    markup = renders[0][0]['reply_markup']
    _assert_eq(_ctas(markup)[:-1], FREE_BRONZE, "the manual update limit: every plan's invoice, the free Bronze")
    _assert_eq(markup[-1][0]['callback_data']['tp'], 'bck', "and keeps the back button")
    _assert('Without Relay' not in renders[0][0]['text'], "it does not say only Relay lifts it")


def channel_limit(channel):
    page = channel.get_connecting_channel_message(
        'en', {'id': 0, 'level': 0, 'price': 0}, [TARIFFS[1]])
    _assert_eq(_first_cta(page['markup']), PAYWALL, "the channel page carries the invoice")
    page = channel.get_connecting_channel_message(
        'en', {'id': 1, 'level': 1, 'price': 50}, [TARIFFS[1]], plan_running=True)
    _assert_eq(_first_cta(page['markup']), [{'tp': 'bs_stars'}, {'tp': 'bs_trfs'}],
               "a running Bronze is not billed Relay (it would be a top-up): Stars page, change-plan")


def invoice_defaults_to_relay(stars):
    invoices = []
    data = {'chat_id': 503, 'language_code': 'en', 'message': None,
            'callback': _call({'tp': 'bs_stars_pay'}), 'united_data': {}}
    with patch.object(stars, 'SQLighter', _FreeUserDB), \
            patch.object(stars, 'get_invoice_stars_withdraw_rate_x1000', lambda: 1300), \
            patch.object(stars.bot, 'send_invoice', lambda *a, **kw: invoices.append(a)):
        stars.send_invoice(data)
        stars.send_invoice(dict(data, united_data={'v': 1}))
    _assert_eq((json.loads(invoices[0][3])['b'], json.loads(invoices[0][3])['v']), (500, 3),
               "a button without an id bills Relay's price, for Relay")
    _assert_eq(json.loads(invoices[1][3])['b'], 50, "a button with an id bills that plan")


def main():
    podcast = import_builder("podcastModule")
    if podcast is None:
        return
    channel = import_builder("channelModule")
    from app.service.payment import starsPaymentModule
    subscription_limit(podcast)
    subscription_limit(podcast, promo=True)
    update_limit()
    channel_limit(channel)
    invoice_defaults_to_relay(starsPaymentModule)
    print("all paywall checks passed")


if __name__ == "__main__":
    main()
